"""Continuous AY-3-8910 source rendering, separate from target PCM packaging.

One emu2149 instance owns all three channels and the shared noise/envelope.
Raw ordered writes, including repeated shape writes, are never deduplicated.
"""
from array import array
import csv
import ctypes
from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import wave

from vgm_io import read_vgm_header
from vgm_timing import command_times

CORE_COMMIT = '441f3dc295a9b82db16921461f0678b483db8304'
RATE = 44100


@dataclass(frozen=True)
class PsgWrite:
    event_id: int
    source_event_id: int
    address: int
    vgmticks: int
    original_vgmticks: int
    loop_iteration: int
    register: int
    data: int


@dataclass(frozen=True)
class PlaybackGate:
    gate_id: int
    start_vgmticks: Fraction
    end_vgmticks: Fraction
    start_event_id: int
    end_event_id: int | None
    source_event_ids: tuple[int, ...]
    termination: str


@dataclass(frozen=True)
class PsgPlayback:
    sample_rate: Fraction
    source_end_vgmticks: int
    samples: array
    gates: tuple[PlaybackGate, ...]
    writes: tuple[PsgWrite, ...]
    metadata: dict

    @property
    def frame_count(self):
        return len(self.samples) // 2

    def dump(self, output_dir, stem):
        return dump(self, output_dir, stem)


def _library(root):
    core = root / '.tools/emu2149'
    paths = {name: core / name for name in ('emu2149.c', 'emu2149.h')}
    if not all(path.is_file() for path in paths.values()):
        raise RuntimeError('Missing external emu2149 core; run bash scripts/setup_psg_pcm.sh')
    wrapper = root / 'scripts/psg_pcm_probe.c'
    paths['psg_pcm_probe.c'] = wrapper
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    # A changed checkout must not be mislabeled as the pinned dependency.
    revision = subprocess.run(['git', '-C', str(core), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, timeout=10)
    if revision.returncode or revision.stdout.strip() != CORE_COMMIT:
        raise RuntimeError('External emu2149 checkout is not at the supported pinned commit')
    status = subprocess.run(['git', '-C', str(core), 'diff', '--exit-code', 'HEAD', '--',
                             'emu2149.c', 'emu2149.h'], capture_output=True, timeout=10)
    if status.returncode:
        raise RuntimeError('External emu2149 core/header differ from the pinned commit')
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:24]
    build = root / '.tools/psg-pcm'
    build.mkdir(parents=True, exist_ok=True)
    library = build / f'probe_{digest}.so'
    if not library.is_file():
        gcc = shutil.which('gcc')
        if not gcc:
            raise RuntimeError('PSG source rendering requires GCC; run in WSL')
        result = subprocess.run([gcc, '-shared', '-fPIC', '-O2', '-I', str(core),
                                 str(wrapper), str(core / 'emu2149.c'), '-o', str(library)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('Failed to build external emu2149 adapter: ' + result.stderr)
    handle = ctypes.CDLL(str(library))
    handle.psg_pcm_render.argtypes = [ctypes.c_uint32, ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint64, ctypes.POINTER(ctypes.c_int16)]
    handle.psg_pcm_render.restype = ctypes.c_int
    return handle, hashes


def _gates(writes, end):
    """Conservative union of possible output, including envelope and DAC states.

    Both mixer inputs disabled produce a constant DAC level, not silence.
    Envelope shape can reach zero, but its future output remains possible;
    only amplitude registers establish a provably muted interval here.
    """
    amplitudes = [0, 0, 0]
    start = None
    members = []
    gates = []
    for item in writes:
        was_active = any(amplitudes)
        if 8 <= item.register <= 10:
            amplitudes[item.register - 8] = item.data & 31
        active = any(amplitudes)
        if active and not was_active:
            start = item
            members = []
        if was_active or active:
            members.append(item.source_event_id)
        if was_active and not active:
            if item.vgmticks > start.vgmticks:
                gates.append(PlaybackGate(len(gates), Fraction(start.vgmticks),
                    Fraction(item.vgmticks), start.event_id, item.event_id,
                    tuple(dict.fromkeys(members)), 'amplitudes_muted'))
            start = None
            members = []
    if start is not None and end > start.vgmticks:
        gates.append(PlaybackGate(len(gates), Fraction(start.vgmticks), Fraction(end),
            start.event_id, None, tuple(dict.fromkeys(members)), 'source_end'))
    return tuple(gates)


def render(raw, *, loop_count=1, root=None):
    """Render AY writes at exact source samples; reset once before frame zero."""
    raw = bytes(raw)
    header = read_vgm_header(raw)
    clock_raw = header['ay_clock_raw']
    if clock_raw & 0xc0000000:
        raise ValueError('PSG PCM source supports one AY instance without clock variant flags')
    clock = clock_raw & 0x3fffffff
    if not clock or header['ay_type'] != 0:
        raise ValueError('PSG PCM source currently supports AY-3-8910 type 0 with a declared clock')
    if header['ay_flags'] & ~3:
        raise ValueError('PSG PCM source AY flags outside 0..3 are not supported')
    writes = []
    end = 0
    for event_id, event in enumerate(command_times(raw, loop_count=loop_count)):
        end = max(end, event.vgmticks + event.wait_samples)
        if event.command != 0xa0:
            continue
        register, data = raw[event.address + 1:event.address + 3]
        if register > 15:
            raise ValueError(f'PSG PCM unsupported AY variant/second-instance register {register:#x}')
        writes.append(PsgWrite(event_id, event.source_event_id, event.address,
                              event.vgmticks, event.original_vgmticks,
                              event.loop_iteration, register, data))
    root = Path(root or Path(__file__).resolve().parents[1])
    library, hashes = _library(root)
    count = len(writes)
    times = (ctypes.c_uint64 * count)(*(item.vgmticks for item in writes))
    registers = (ctypes.c_uint8 * count)(*(item.register for item in writes))
    values = (ctypes.c_uint8 * count)(*(item.data for item in writes))
    samples = array('h', [0]) * (end * 2)
    output = (ctypes.c_int16 * len(samples)).from_buffer(samples)
    status = library.psg_pcm_render(clock, end, times, registers, values, count, output)
    if status:
        raise RuntimeError(f'Continuous AY source renderer failed: {status}')
    metadata = dict(schema='psg-playback-v1', core='external emu2149',
        core_commit=CORE_COMMIT, source_sha256=hashes, clock_hz=clock,
        ay_type=header['ay_type'], ay_flags=header['ay_flags'],
        initialization=['PSG_new(clock,44100)', 'PSG_setVolumeMode(2): AY-3-8910',
                        'PSG_setQuality(1)', 'PSG_reset once before first write'],
        assumptions=['Three channels share one continuous noise and envelope state',
                     'All ordered 0xA0 writes applied once before the sample at their timestamp',
                     'Reader loop replay continues the same chip state',
                     'AY flags 0..3 accepted; header output wiring/legacy-output hints do not alter this mono chip mix',
                     'Registers 14 and 15 retained as I/O writes, without emulated external peripherals',
                     'External quality1 includes its own rateconverter and high-pitch suppression; no additional source filter',
                     'No target gain, DC filter, target resampling, peak normalization or channel panning'],
        source_write_count=count, loop_count=loop_count, frame_count=end,
        source_end_vgmticks=end, sample_rate_hz=RATE, channels=2,
        sample_format='s16le', source_state_modified=False,
        gate_policy='union of nonzero amplitude or envelope-selected channels; includes constant DAC states')
    return PsgPlayback(Fraction(RATE), end, samples, _gates(writes, end), tuple(writes), metadata)


def dump(playback, output_dir, stem='psg'):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    writes_path = directory / f'{stem}.psg.ordered_writes.csv'
    gates_path = directory / f'{stem}.psg.playback_gates.csv'
    wav_path = directory / f'{stem}.psg.native.wav'
    json_path = directory / f'{stem}.psg.playback.json'
    for path, items, record in ((writes_path, playback.writes, PsgWrite),
                                (gates_path, playback.gates, PlaybackGate)):
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(record.__dataclass_fields__),
                                    lineterminator='\n')
            writer.writeheader()
            for item in items:
                row = asdict(item)
                if 'source_event_ids' in row:
                    row['source_event_ids'] = json.dumps(row['source_event_ids'])
                writer.writerow(row)
    samples = array('h', playback.samples)
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(wav_path), 'wb') as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(samples.tobytes())
    metadata = dict(playback.metadata, gate_count=len(playback.gates),
                    waveform_path=str(wav_path), gates_csv_path=str(gates_path),
                    writes_csv_path=str(writes_path), analysis_json_path=str(json_path),
                    current_files=[str(path) for path in (writes_path, gates_path, wav_path, json_path)])
    json_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return metadata
