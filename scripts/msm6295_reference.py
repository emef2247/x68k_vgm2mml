"""Optional independent MSM6295 oracle using pinned, unchanged libvgm C sources.

Explicit setup keeps the external source, wrapper and compiled library under
ignored .tools/. It reads authored test material only, never private fixtures.
Run with WSL Python: python scripts/msm6295_reference.py --setup --self-test.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "bad50c571db45b872304bdcd0603dd2214f0663e"
SOURCE_HASHES = {
    "emu/logging.c": "eb823352deeca537cf8a1e4324101c1353b4f0f1a3d5a65f0e48b36b755c9b46",
    "emu/cores/okim6295.c": "00778ea2bb630abf549ea25671e9d19df50d4ce4889be9e1fcfa6739b5ae6194",
    "emu/cores/okim6295.h": "23b61cc3f4974b64d30a3c8c95eca9422d146598eaef664b7d79ff6f50b74153",
    "emu/cores/okiadpcm.c": "95ad62ea67fb3f239873abf79200ce11d3d548c40022ec02da0dd4a3abaf5af1",
    "emu/cores/okiadpcm.h": "f850732fe0cdb032d2cedda758d4b74eb6562f701b80ec75d7a59d41cd243864",
}
TOOLS = ROOT / ".tools" / "msm6295-reference"
UPSTREAM = TOOLS / "upstream"
LIBRARY = TOOLS / "libmsm6295_reference.so"
WRAPPER = r"""
#include "upstream/emu/cores/okim6295.c"
#include "upstream/emu/cores/okiadpcm.c"
#include "upstream/emu/logging.c"
void* ref_create(unsigned clock, unsigned pin7, unsigned size) {
    DEV_GEN_CFG cfg = {0}; DEV_INFO out = {0};
    cfg.clock=clock; cfg.flags=pin7; cfg.srMode=DEVRI_SRMODE_NATIVE;
    if(device_start_okim6295(&cfg,&out)) return NULL;
    okim6295_state* chip=out.dataPtr->chipInf;
    device_reset_okim6295(chip); okim6295_alloc_rom(chip,size); return chip;
}
void ref_destroy(void* chip) { device_stop_okim6295(chip); }
void ref_rom(void* chip, unsigned start, unsigned size, const unsigned char* data) {
    okim6295_write_rom(chip,start,size,data);
}
void ref_write(void* chip, unsigned reg, unsigned value) { okim6295_w(chip,reg,value); }
void ref_frame(void* chip, int* left, int* right) {
    DEV_SMPL *outputs[2]={left,right}; okim6295_update(chip,1,outputs);
}
void ref_state(void* chip, unsigned channel, int* out) {
    okim6295_state* c=chip; okim_voice* v=&c->voice[channel];
    out[0]=v->playing; out[1]=v->sample; out[2]=v->count;
    out[3]=v->base_offset; out[4]=v->adpcm.signal; out[5]=v->adpcm.step;
    out[6]=v->volume; out[7]=c->command;
}
unsigned ref_rate(void* chip) { return okim6295_get_rate(chip); }
unsigned ref_status(void* chip) { return okim6295_r(chip,0); }
void ref_decode(const unsigned char* nibbles, unsigned count, int* signals, int* steps) {
    oki_adpcm_state state; oki_adpcm_init(&state,NULL,NULL);
    for(unsigned i=0;i<count;i++) {
        signals[i]=oki_adpcm_clock(&state,nibbles[i]); steps[i]=state.step;
    }
}
"""


def metadata():
    if not (UPSTREAM / ".git").exists():
        raise RuntimeError("MSM6295 oracle not installed; explicitly run --setup")
    revision = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    if revision != COMMIT:
        raise RuntimeError("Pinned MSM6295 reference revision differs")
    for name, expected in SOURCE_HASHES.items():
        if hashlib.sha256((UPSTREAM / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Pinned MSM6295 reference source hash differs: " + name)
    return dict(upstream="https://github.com/ValleyBell/libvgm", commit=revision,
                source_sha256=dict(SOURCE_HASHES), source_license="BSD-3-Clause",
                attribution="Mirko Buffoni, Aaron Giles; OKI ADPCM: Andrew Gardner, Aaron Giles",
                sample_grid="clock_hz // (132 if pin7 else 165)",
                comparison="exact authored native PCM, ADPCM state, voice availability and command scheduling")


def setup():
    TOOLS.mkdir(parents=True, exist_ok=True)
    if not (UPSTREAM / ".git").exists():
        local = ROOT / ".tools" / "c140-reference" / "upstream"
        if (local / ".git").exists():
            revision = subprocess.check_output(["git", "-C", str(local), "rev-parse", "HEAD"], text=True).strip()
        else:
            revision = None
        if revision == COMMIT:
            subprocess.run(["git", "clone", "--no-checkout", "--no-hardlinks", str(local), str(UPSTREAM)], check=True)
        else:
            subprocess.run(["git", "init", str(UPSTREAM)], check=True)
            subprocess.run(["git", "-C", str(UPSTREAM), "remote", "add", "origin",
                            "https://github.com/ValleyBell/libvgm.git"], check=True)
            subprocess.run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", COMMIT], check=True)
        subprocess.run(["git", "-C", str(UPSTREAM), "checkout", "--detach", COMMIT], check=True)
    if subprocess.run(["git", "-C", str(UPSTREAM), "diff", "--quiet", "HEAD", "--"]).returncode:
        raise RuntimeError("Pinned MSM6295 upstream worktree has modified dependencies")
    details = metadata()
    wrapper = TOOLS / "wrapper.c"
    wrapper.write_text(WRAPPER, encoding="utf-8")
    subprocess.run(["cc", "-std=c99", "-O2", "-fPIC", "-shared", str(wrapper), "-lm", "-o", str(LIBRARY)], check=True)
    details.update(wrapper_sha256=hashlib.sha256(wrapper.read_bytes()).hexdigest(),
                   library_sha256=hashlib.sha256(LIBRARY.read_bytes()).hexdigest())
    (TOOLS / "metadata.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    return details


class Reference:
    def __init__(self, rom: bytes, clock=1000000, pin7=1):
        metadata()
        record = json.loads((TOOLS / "metadata.json").read_text())
        if record.get("wrapper_sha256") != hashlib.sha256(WRAPPER.encode()).hexdigest():
            raise RuntimeError("MSM6295 wrapper differs; explicitly rebuild with --setup")
        if record.get("library_sha256") != hashlib.sha256(LIBRARY.read_bytes()).hexdigest():
            raise RuntimeError("MSM6295 oracle library hash differs; rebuild with --setup")
        self.lib = ctypes.CDLL(str(LIBRARY))
        self.lib.ref_create.argtypes = [ctypes.c_uint] * 3
        self.lib.ref_create.restype = ctypes.c_void_p
        self.lib.ref_destroy.argtypes = [ctypes.c_void_p]
        self.lib.ref_write.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        self.lib.ref_rom.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
        self.lib.ref_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        self.lib.ref_state.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]
        self.lib.ref_rate.argtypes = self.lib.ref_status.argtypes = [ctypes.c_void_p]
        self.lib.ref_rate.restype = self.lib.ref_status.restype = ctypes.c_uint
        self.lib.ref_decode.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                       ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        self.handle = self.lib.ref_create(clock, pin7, len(rom))
        if not self.handle:
            raise MemoryError("MSM6295 reference allocation failed")
        self.rom(0, rom)

    def close(self):
        if self.handle:
            self.lib.ref_destroy(self.handle)
            self.handle = None

    def rom(self, start, payload):
        self.lib.ref_rom(self.handle, start, len(payload), ctypes.create_string_buffer(payload))

    def write(self, register, value):
        self.lib.ref_write(self.handle, register, value)

    def frame(self):
        left, right = ctypes.c_int(), ctypes.c_int()
        self.lib.ref_frame(self.handle, ctypes.byref(left), ctypes.byref(right))
        return left.value, right.value

    def state(self, channel=0):
        state = (ctypes.c_int * 8)()
        self.lib.ref_state(self.handle, channel, state)
        return tuple(state)

    def rate(self):
        return self.lib.ref_rate(self.handle)

    def status(self):
        return self.lib.ref_status(self.handle)

    def decode_nibbles(self, nibbles):
        payload = bytes(nibbles)
        signals = (ctypes.c_int * len(payload))()
        steps = (ctypes.c_int * len(payload))()
        self.lib.ref_decode(ctypes.create_string_buffer(payload), len(payload), signals, steps)
        return list(signals), list(steps)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", action="store_true", help="Fetch/reuse pinned libvgm and compile only its MSM6295/OKI ADPCM cores")
    parser.add_argument("--self-test", action="store_true", help="Compare authored traces against native Python analysis")
    args = parser.parse_args()
    result = setup() if args.setup else metadata()
    if args.self_test:
        sys.path[:0] = [str(ROOT / "py"), str(ROOT / "tests/scripts")]
        from test_msm6295_reference import compare_authored_cases
        result["authored_cases"] = compare_authored_cases()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
