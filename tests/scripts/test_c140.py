"""Authored public C140 source evidence, headers, provenance and strict ROM."""
from pathlib import Path
import json
import math
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from c140 import analyze


def write(register, value):
    return bytes((0xd4, register >> 8, register & 255, value))


def wait(ticks):
    return b'\x61' + struct.pack('<H', ticks)


def voice(channel=0, *, frequency=32768, level=255, right=None, mode=0x80,
          start=0, end=64, loop=0):
    base = channel * 16
    registers = [(0, level if right is None else right), (1, level),
                 (2, frequency >> 8), (3, frequency & 255), (4, 0),
                 (6, start >> 8), (7, start & 255), (8, end >> 8), (9, end & 255),
                 (10, loop >> 8), (11, loop & 255), (5, mode)]
    return b''.join(write(base + register, value) for register, value in registers)


def make_vgm(commands, *, clock=12288000, chip_type=0, rom=None, loop_offset=None):
    header = bytearray(0x100)
    header[:4] = b'Vgm '
    struct.pack_into('<I', header, 8, 0x171)
    struct.pack_into('<I', header, 0x34, 0x100 - 0x34)
    struct.pack_into('<I', header, 0xa8, clock)
    header[0x96] = chip_type
    if rom is None:
        rom = bytes(round(100 * math.sin(i * math.tau / 16)) & 255 for i in range(64))
    block = b'\x67\x66\x8d' + struct.pack('<III', len(rom) + 8, len(rom), 0) + rom
    if loop_offset is not None:
        struct.pack_into('<I', header, 0x1c, 0x100 + len(block) + loop_offset - 0x1c)
    raw = header + block + commands + b'\x66'
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


class C140SourceTests(unittest.TestCase):
    def test_header_compatibility_and_shared_event_ids(self):
        raw = make_vgm(b'\x54\x20\xc7' + voice() + wait(1000), clock=21390)
        trace = analyze(raw)
        self.assertEqual(trace.clock_raw, 21390)
        self.assertEqual(trace.clock_hz, 12288000)
        self.assertEqual(trace.source_end_vgmticks, 1000)
        self.assertEqual(trace.writes[0].event_id, 2)
        self.assertEqual(trace.writes[0].source_event_id, 2)
        self.assertEqual(trace.rom_blocks[0].payload, raw[0x10f:0x14f])
        with tempfile.TemporaryDirectory() as temp:
            trace.dump(temp, 'authored')
            report = json.loads((Path(temp) / 'authored.c140.source.json').read_text())
            self.assertEqual(report['tick_clock_hz'], 44100)
            self.assertEqual(report['initialization']['origin'], 'reference_reset_assumption')
            self.assertFalse(report['initialization']['observed'])
            self.assertEqual(report['rom_blocks'][0]['payload_bytes'], 64)

    def test_header_fields_respect_version_and_command_data_boundary(self):
        old = bytearray(make_vgm(voice() + wait(10), chip_type=1))
        struct.pack_into('<I', old, 8, 0x160)
        trace = analyze(bytes(old))
        self.assertEqual((trace.clock_raw, trace.clock_hz, trace.chip_type), (0, 0, 0))
        self.assertIn('missing_c140_clock', trace.issues)
        short = bytearray(0x40)
        short[:4] = b'Vgm '
        struct.pack_into('<I', short, 8, 0x171)
        short.extend(voice() + wait(10) + b'\x66')
        struct.pack_into('<I', short, 4, len(short) - 4)
        trace = analyze(bytes(short))
        self.assertEqual((trace.clock_raw, trace.chip_type), (0, 0))
        self.assertEqual(trace.source_end_vgmticks, 10)

    def test_latched_addresses_and_write_observations_are_immutable(self):
        trace = analyze(make_vgm(voice() + wait(50) + write(7, 12) + wait(50)))
        self.assertEqual(trace.segments[-1].latched_start, 0)
        self.assertEqual(trace.segments[-1].registers[7], 12)
        self.assertEqual(trace.state_events[0].registers[7], 0)
        self.assertEqual(trace.state_events[-1].registers[7], 12)

    def test_unsupported_instances_remain_in_evidence(self):
        trace = analyze(make_vgm(write(0x8005, 0x80) + wait(10), clock=0x40000000 | 12288000, chip_type=2))
        self.assertEqual(trace.writes[0].chip_instance, 1)
        self.assertIn('dual_c140_header_unsupported', trace.issues)
        self.assertIn('unsupported_chip_type_2', trace.issues)
        self.assertIn('second_c140_write_unsupported', trace.issues)

    def test_malformed_rom_does_not_become_zero_filled(self):
        raw = bytearray(make_vgm(voice() + wait(10)))
        struct.pack_into('<I', raw, 0x10b, 64)
        with self.assertRaisesRegex(ValueError, 'range'):
            analyze(raw)

    def test_loop_traversals_keep_register_state_and_original_ids(self):
        commands = voice(mode=0x90) + wait(50) + write(1, 100) + wait(50)
        loop_offset = len(voice(mode=0x90))
        trace = analyze(make_vgm(commands, loop_offset=loop_offset), loop_count=2)
        self.assertEqual(trace.source_end_vgmticks, 200)
        self.assertEqual(trace.writes[-1].source_event_id, trace.writes[-2].source_event_id)
        self.assertEqual(trace.writes[-1].loop_iteration, 1)


if __name__ == '__main__':
    unittest.main()
