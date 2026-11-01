"""Original arithmetic OKI ADPCM test data, unrelated to game ROMs."""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]


def write(value, register=0):
    return bytes((0xb8, register, value))


def wait(ticks):
    return b'\x61' + struct.pack('<H', ticks)


def start(sample=1, mask=1, attenuation=0):
    return write(0x80 | sample) + write((mask << 4) | attenuation)


def original_rom():
    rom = bytearray(1120)
    for number, begin, length in ((1, 1024, 32), (2, 1056, 64)):
        offset = number * 8
        rom[offset:offset+3] = begin.to_bytes(3, 'big')
        rom[offset+3:offset+6] = (begin + length - 1).to_bytes(3, 'big')
        rom[begin:begin+length] = bytes(((index * 29 + number * 13) & 255) for index in range(length))
    return bytes(rom)


def make_vgm(commands, *, include_fm=False, empty_rom=False, clock_raw=0x800f4240, loop_offset=None):
    header = bytearray(256)
    header[:4] = b'Vgm '
    struct.pack_into('<I', header, 8, 0x171)
    struct.pack_into('<I', header, 0x34, 256 - 0x34)
    struct.pack_into('<I', header, 0x98, clock_raw)
    if include_fm:
        struct.pack_into('<I', header, 0x30, 4000000)
    rom = b'' if empty_rom else original_rom()
    data = struct.pack('<II', 262144 if empty_rom else len(rom), 0) + rom
    block = b'\x67\x66\x8b' + struct.pack('<I', len(data)) + data
    if loop_offset is not None:
        struct.pack_into('<I', header, 0x1c, len(header) + len(block) + loop_offset - 0x1c)
    raw = header + block + commands + b'\x66'
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


def cases():
    yield 'sample_reuse', make_vgm(start() + wait(1000) + start(attenuation=3) + wait(1000)), dict(expected_assets=1, expected_playbacks=2)
    yield 'four_voice_stops', make_vgm(start(2, mask=15, attenuation=2) + wait(200) + write(0x50) + wait(1000)), dict(expected_assets=1, expected_playbacks=4)
    from test_opm_performed_runs import setup as fm_setup
    from test_opm_mdx import write as fm_write
    yield 'opm_inactive_rom', make_vgm(fm_setup() + fm_write(8,120) + wait(2000) + fm_write(8,0) + wait(1000), include_fm=True, empty_rom=True), dict(expected_assets=0, expected_playbacks=0)


def main():
    for name, raw, facts in cases():
        folder = ROOT / 'tests/fixtures/public/opm_msm6295' / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (name + '.vgm')).write_bytes(raw)
        (folder / 'source.json').write_text(json.dumps(dict(origin='Project-authored arithmetic ADPCM/register sequence; no game-derived content', sha256=hashlib.sha256(raw).hexdigest(), **facts), indent=2) + '\n')
        print(name, len(raw))


if __name__ == '__main__':
    main()
