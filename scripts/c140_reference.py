"""Optional independent C140 oracle using an unchanged, pinned libvgm C core.

Run with WSL Python: python scripts/c140_reference.py --setup --self-test.
Only --setup downloads/builds dependencies, under ignored .tools/. No game data
is needed or read. This is a source-runtime comparison, not an MDX sound test.
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
SOURCE_SHA256 = "859e22f369ee8465e6d5dbd11eb2d2828fa85da62acc5a974301c3127ac8118e"
TOOLS = ROOT / ".tools" / "c140-reference"
UPSTREAM = TOOLS / "upstream"
LIBRARY = TOOLS / "libc140_reference.so"
WRAPPER = r"""
#include "upstream/emu/cores/c140.c"
void* ref_create(unsigned clock, unsigned type, unsigned size) {
    DEV_GEN_CFG cfg = {0}; DEV_INFO out = {0};
    cfg.clock=clock; cfg.flags=type; cfg.srMode=DEVRI_SRMODE_NATIVE;
    if(device_start_c140(&cfg,&out)) return NULL;
    c140_state* chip=out.dataPtr->chipInf;
    device_reset_c140(chip); c140_alloc_rom(chip,size); return chip;
}
void ref_destroy(void* chip) { device_stop_c140(chip); }
void ref_rom(void* chip, unsigned start, unsigned size, const unsigned char* data) {
    c140_write_rom(chip,start,size,data);
}
void ref_write(void* chip, unsigned reg, unsigned value) { c140_w(chip,reg,value); }
void ref_frame(void* chip, int* left, int* right) {
    DEV_SMPL *outputs[2]={left,right}; c140_update(chip,1,outputs);
}
void ref_state(void* chip, unsigned channel, int* out) {
    C140_VOICE* v=&((c140_state*)chip)->voi[channel];
    out[0]=v->key; out[1]=v->pos; out[2]=v->ptoffset;
    out[3]=v->lastdt; out[4]=v->prevdt; out[5]=v->dltdt;
}
"""


def metadata():
    source = UPSTREAM / "emu/cores/c140.c"
    if not source.exists():
        raise RuntimeError("C140 oracle not installed; explicitly run --setup")
    revision = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if revision != COMMIT or digest != SOURCE_SHA256:
        raise RuntimeError("Pinned C140 reference revision or source hash differs")
    return {"upstream": "https://github.com/ValleyBell/libvgm", "commit": revision,
            "source": "emu/cores/c140.c", "source_sha256": digest,
            "source_license": "BSD-3-Clause", "sample_grid": "clock_hz // 288",
            "comparison": "exact native stereo samples and voice cursor; authored ROMs only"}


def setup():
    TOOLS.mkdir(parents=True, exist_ok=True)
    if not (UPSTREAM / ".git").exists():
        subprocess.run(["git", "init", str(UPSTREAM)], check=True)
        subprocess.run(["git", "-C", str(UPSTREAM), "remote", "add", "origin",
                        "https://github.com/ValleyBell/libvgm.git"], check=True)
        subprocess.run(["git", "-C", str(UPSTREAM), "fetch", "--depth", "1", "origin", COMMIT], check=True)
        subprocess.run(["git", "-C", str(UPSTREAM), "checkout", "--detach", COMMIT], check=True)
    details = metadata()
    wrapper = TOOLS / "wrapper.c"
    wrapper.write_text(WRAPPER, encoding="utf-8")
    subprocess.run(["cc", "-std=c99", "-O2", "-fPIC", "-shared", str(wrapper), "-o", str(LIBRARY)], check=True)
    details["wrapper_sha256"] = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    (TOOLS / "metadata.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    return details


class Reference:
    def __init__(self, rom: bytes, clock=12288000, chip_type=0):
        metadata()
        self.lib = ctypes.CDLL(str(LIBRARY))
        self.lib.ref_create.argtypes = [ctypes.c_uint] * 3
        self.lib.ref_create.restype = ctypes.c_void_p
        self.lib.ref_destroy.argtypes = [ctypes.c_void_p]
        self.lib.ref_write.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        self.lib.ref_rom.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
        self.lib.ref_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        self.lib.ref_state.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int)]
        self.handle = self.lib.ref_create(clock, chip_type, len(rom))
        if not self.handle:
            raise MemoryError("C140 reference allocation failed")
        data = ctypes.create_string_buffer(rom)
        self.lib.ref_rom(self.handle, 0, len(rom), data)

    def close(self):
        if self.handle:
            self.lib.ref_destroy(self.handle)
            self.handle = None

    def write(self, register, value):
        self.lib.ref_write(self.handle, register, value)

    def frame(self):
        left, right = ctypes.c_int(), ctypes.c_int()
        self.lib.ref_frame(self.handle, ctypes.byref(left), ctypes.byref(right))
        return left.value, right.value

    def state(self, channel=0):
        state = (ctypes.c_int * 6)()
        self.lib.ref_state(self.handle, channel, state)
        return tuple(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", action="store_true", help="Fetch pinned libvgm and build only its C140 core")
    parser.add_argument("--self-test", action="store_true", help="Compare authored traces with the Python C140 runtime")
    args = parser.parse_args()
    result = setup() if args.setup else metadata()
    if args.self_test:
        sys.path[:0] = [str(ROOT / "py"), str(ROOT / "tests/scripts")]
        from test_c140_reference import compare_authored_cases
        result["authored_cases"] = compare_authored_cases()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
