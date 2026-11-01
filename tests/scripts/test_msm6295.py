"""Authored MSM6295 command and ROM evidence, with no game-derived material."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import csv
import json
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from msm6295 import analyze


def write(register, value):
    return bytes((0xb8, register, value))


def wait(ticks):
    return bytes((0x61, ticks & 255, ticks >> 8))


def start(sample=1, channel=0, level=0):
    return write(0, 128 | sample) + write(0, (16 << channel) | level)


def stop(channel=0):
    return write(0, 8 << channel)


def make_rom(samples=None):
    samples = {1: bytes((index * 19 + 11) & 255 for index in range(64))} if samples is None else samples
    rom = bytearray(0x400 + sum(len(payload) for payload in samples.values()))
    at = 0x400
    for sample, payload in samples.items():
        rom[sample * 8:sample * 8 + 3] = at.to_bytes(3, 'big')
        rom[sample * 8 + 3:sample * 8 + 6] = (at + len(payload) - 1).to_bytes(3, 'big')
        rom[at:at + len(payload)] = payload
        at += len(payload)
    return bytes(rom)


def romblock(payload, *, total=None, start=0, instance=0):
    total = len(payload) if total is None else total
    data = struct.pack('<II', total, start) + payload
    return b'\x67\x66\x8b' + struct.pack('<I', len(data) | (instance << 31)) + data


def make_vgm(commands, *, rom=None, clock=1000000, pin7=True, loop_offset=None, total=None):
    prefix = romblock(make_rom() if rom is None else rom, total=total)
    raw = bytearray(0x100)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 0x34, 0x100 - 0x34)
    struct.pack_into('<I', raw, 0x98, clock | (0x80000000 if pin7 else 0))
    if loop_offset is not None:
        struct.pack_into('<I', raw, 0x1c, 0x100 + len(prefix) + loop_offset - 0x1c)
    raw.extend(prefix + commands + b'\x66')
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


class Msm6295SourceTests(unittest.TestCase):
    def test_header_command_latch_and_source_identifiers(self):
        raw = make_vgm(write(0, 0x81) + wait(3) + write(8, 0x40) + write(0, 0x83) + wait(30))
        trace = analyze(raw)
        self.assertEqual(trace.clock_hz, 1000000)
        self.assertTrue(trace.pin7_high)
        self.assertEqual(trace.rate_hz, 7575)
        self.assertEqual(trace.divider, 132)
        self.assertEqual([s.command_kind for s in trace.state_events], ['sample_select', 'extension_write', 'start_request'])
        self.assertEqual(trace.state_events[1].pending_sample, 1)
        self.assertIsNone(trace.state_events[2].pending_sample)
        self.assertEqual(trace.state_events[2].voice_mask, 8)
        self.assertEqual(trace.state_events[2].attenuation, 3)
        self.assertGreater(trace.writes[2].event_id, trace.writes[1].event_id)
        self.assertEqual(trace.source_end_vgmticks, 33)
        with self.assertRaises(FrozenInstanceError):
            trace.clock_hz = 2

    def test_loop_occurrences_keep_latch_and_original_command_ids(self):
        prefix = write(0, 0x81)
        raw = make_vgm(prefix + wait(100) + write(0, 0x10) + wait(100), loop_offset=len(prefix))
        trace = analyze(raw, loop_count=2)
        self.assertEqual([s.command_kind for s in trace.state_events], ['sample_select', 'start_request', 'stop_request'])
        self.assertEqual(trace.writes[1].source_event_id, trace.writes[2].source_event_id)
        self.assertEqual(trace.writes[2].loop_iteration, 1)
        self.assertEqual(trace.source_end_vgmticks, 400)

    def test_source_dumps_keep_observed_and_assumed_values_distinct(self):
        trace = analyze(make_vgm(start() + wait(100)))
        with tempfile.TemporaryDirectory() as temp:
            trace.dump(temp, 'AUTH')
            out = Path(temp)
            source = json.loads((out / 'AUTH.msm6295.source.json').read_text())
            self.assertFalse(source['initialization']['observed'])
            self.assertEqual(source['initialization']['decoder_signal'], -2)
            self.assertEqual(source['rom_blocks'][0]['payload_bytes'], len(make_rom()))
            with (out / 'AUTH.msm6295.states.csv').open() as stream:
                states = list(csv.DictReader(stream))
            self.assertEqual(states[-1]['command_kind'], 'start_request')
            self.assertTrue((out / 'AUTH.msm6295.segments.csv').is_file())

    def test_second_chip_evidence_is_retained(self):
        trace = analyze(make_vgm(write(0x80, 0x81) + wait(100)))
        self.assertEqual(trace.writes[0].chip_instance, 1)
        self.assertIn('second_msm6295_write_unsupported', trace.issues)

    def test_malformed_rom_range_is_not_silence(self):
        raw = bytearray(make_vgm(start() + wait(100)))
        struct.pack_into('<I', raw, 0x107, 2)
        with self.assertRaisesRegex(ValueError, 'declared range'):
            analyze(bytes(raw))


if __name__ == '__main__':
    unittest.main()
