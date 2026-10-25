"""Authored independent C140 voices and bank contracts; no game assets."""
from dataclasses import replace
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
from test_c140 import make_vgm, voice, write, wait
from c140 import analyze
from c140_bank import (project, render_gates, Voice, Rom, decode_mulaw,
                       sample_address, native_delta, BankUnsupported)


class C140BankTests(unittest.TestCase):
    def test_static_assets_share_across_volume_pan_and_gate_lengths(self):
        raw = make_vgm(voice(level=255, right=0) + wait(30) + write(5, 0) +
                       voice(channel=1, level=100, right=100) + wait(1000))
        result = project(analyze(raw), source_raw=raw)
        self.assertEqual(len(result.samples), 1)
        self.assertEqual(len(result.playbacks), 2)
        self.assertEqual([p.sample_id for p in result.playbacks], [0, 0])
        self.assertEqual([p.pan for p in result.playbacks], [2, 0])
        self.assertNotEqual(result.playbacks[0].target_volume, result.playbacks[1].target_volume)
        self.assertEqual(result.bank_events[0]['termination'], 'key_off')
        self.assertEqual(result.bank_events[1]['termination'], 'natural_stop')
        for event in result.bank_events:
            self.assertEqual(event['rom_generation'], 1)
            self.assertEqual(event['initial_bank'], 0)
            self.assertEqual(event['initial_frequency'], 32768)
            self.assertEqual((event['latched_start'], event['latched_end'], event['latched_loop']), (0, 64, 0))
            self.assertEqual(event['source_codec'], 'linear_signed8')
            self.assertEqual(event['chip_type'], 0)
        self.assertEqual(result.source_origin, 'projected_msm6258_from_c140_bank')
        with tempfile.TemporaryDirectory() as temp:
            result.dump(temp, 'authored')
            self.assertTrue((Path(temp) / 'authored.c140_bank.events.csv').is_file())
            self.assertFalse(list(Path(temp).glob('*segapcm*')))
            info = json.loads((Path(temp) / 'authored.pcm_source.json').read_text())
            self.assertEqual(info['source_origin'], result.source_origin)
        from pcm_mdx import project as target
        plan = target(result, stem='authored', policy='best-effort')
        self.assertEqual(len(plan.bindings), 1)

    def test_static_loop_captures_ignore_onset_volume_for_reuse(self):
        raw = make_vgm(voice(mode=0x90, level=200) + wait(100) + write(5, 0) +
                       voice(mode=0x90, level=80) + wait(100) + write(5, 0))
        result = project(analyze(raw), source_raw=raw)
        self.assertEqual(len(result.samples), 1)
        self.assertNotEqual(result.playbacks[0].target_volume, result.playbacks[1].target_volume)

    def test_pause_is_not_keyoff_and_retrigger_is_new_gate(self):
        raw = make_vgm(voice() + wait(20) + write(2, 0) + write(3, 0) + wait(100) +
                       write(2, 0x80) + wait(20) + write(5, 0x80) + wait(1000))
        gates, rate = render_gates(analyze(raw))
        self.assertEqual(len(gates), 2)
        self.assertEqual(gates[0]['termination'], 'retrigger')
        self.assertEqual(gates[1]['termination'], 'natural_stop')
        self.assertTrue(gates[0]['dynamic'])
        self.assertTrue(all(v == 0 for v in gates[0]['wave'][30:100]))
        self.assertGreater(gates[1]['end_vgmticks'] - gates[1]['start_vgmticks'], 100)

    def test_live_controls_and_latched_start_keep_one_gate(self):
        raw = make_vgm(voice(mode=0x98) + wait(30) + write(7, 20) +
                       write(1, 80) + write(4, 0) + wait(70) + write(5, 0))
        gates, _ = render_gates(analyze(raw))
        self.assertEqual(len(gates), 1)
        self.assertEqual(gates[0]['voice'].start, 0)
        self.assertTrue(gates[0]['dynamic'])
        result = project(analyze(raw), source_raw=raw)
        self.assertEqual(result.playbacks[0].target_volume, 128)
        self.assertTrue(result.bank_assets[0]['held_control_variant'])
        self.assertFalse(result.bank_assets[0]['complete_one_shot'])

    def test_loop_seam_carries_phase_without_invented_attack(self):
        prefix = voice(mode=0x90)
        raw = make_vgm(prefix + wait(50) + write(1, 180) + wait(50), loop_offset=len(prefix))
        trace = analyze(raw, loop_count=2)
        gates, _ = render_gates(trace)
        self.assertEqual(len(gates), 1)
        self.assertEqual(gates[0]['termination'], 'source_end')
        self.assertEqual(gates[0]['end_vgmticks'], 200)
        self.assertEqual(gates[0]['start_vgmticks'], 0)

    def test_unknown_rom_and_resource_limits_are_explicit(self):
        raw = bytearray(make_vgm(voice(end=128) + wait(1000)))
        struct.pack_into('<I', raw, 0x107, 128)
        raw = bytes(raw)
        with self.assertRaisesRegex(BankUnsupported, 'unavailable ROM'):
            project(analyze(raw), source_raw=raw)
        raw = make_vgm(voice(mode=0x90) + wait(1000))
        with patch('c140_bank.MAX_GATE_FRAMES', 10):
            with self.assertRaisesRegex(BankUnsupported, 'frame budget'):
                project(analyze(raw), source_raw=raw)
        with self.assertRaisesRegex(BankUnsupported, 'unsupported_chip_type'):
            project(analyze(make_vgm(voice(), chip_type=2)), source_raw=raw)

    def test_optional_missing_tail_preserves_observed_gate(self):
        raw = bytearray(make_vgm(voice(end=64) + wait(10) + write(5, 0),
                                 rom=bytes((i * 19) & 255 for i in range(16))))
        struct.pack_into('<I', raw, 0x107, 64)
        raw = bytes(raw)
        result = project(analyze(raw), source_raw=raw)
        self.assertEqual(len(result.playbacks), 1)
        self.assertEqual(result.playbacks[0].end_vgmticks, 10)
        self.assertFalse(result.bank_events[0]['complete_one_shot'])
        self.assertEqual(result.bank_events[0]['completion_fallback'], 'optional_tail_missing_rom')
        # Identical ROM evidence with an actually observed read of the missing
        # tail remains a hard source failure, not the optional fallback above.
        raw = bytearray(make_vgm(voice(end=64) + wait(1000),
                                 rom=bytes((i * 19) & 255 for i in range(16))))
        struct.pack_into('<I', raw, 0x107, 64)
        with self.assertRaisesRegex(BankUnsupported, 'unavailable ROM'):
            project(analyze(bytes(raw)), source_raw=bytes(raw))

    def test_optional_completion_is_cached_and_budgeted_independently(self):
        raw = make_vgm(voice(level=255) + wait(10) + write(5, 0) +
                       voice(level=80) + wait(10) + write(5, 0) +
                       voice(level=180) + wait(10) + write(5, 0))
        result = project(analyze(raw), source_raw=raw)
        self.assertEqual(len(result.playbacks), 3)
        self.assertEqual(result.bank_stats['completion_cached_views'], 1)
        self.assertLessEqual(result.bank_stats['completion_native_frames'], 129)
        self.assertTrue(all(event['complete_one_shot'] for event in result.bank_events))
        with patch('c140_bank.MAX_COMPLETION_FRAMES', 1):
            bounded = project(analyze(raw), source_raw=raw)
        self.assertEqual(len(bounded.playbacks), 3)
        self.assertEqual(bounded.bank_stats['completion_native_frames'], 0)
        self.assertEqual(bounded.bank_stats['completion_fallback_gates'], 3)
        self.assertTrue(all(event['completion_fallback'] == 'completion_resource_limit'
                            for event in bounded.bank_events))

    def test_custom_codec_and_address_lines(self):
        self.assertEqual(decode_mulaw(0), 0)
        self.assertEqual(decode_mulaw(0x80), -256)
        self.assertEqual(decode_mulaw(0x7f), 31744)
        self.assertEqual(sample_address(0x1234, 0x20, 0), 0x81234)
        self.assertEqual(sample_address(0x1234, 0x20, 1), 0x101234)
        self.assertEqual(native_delta(12288000, 32768), 32768)


if __name__ == '__main__':
    unittest.main()
