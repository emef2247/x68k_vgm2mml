"""Native command semantics and reusable MSM6295 -> MSM6258 bank assets."""
from pathlib import Path
import json
import csv
from fractions import Fraction
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
from msm6295 import analyze
from msm6295_bank import interpret, project, decode_adpcm, Decoder
from segapcm_bank import BankUnsupported
from test_msm6295 import make_vgm, make_rom, write, start, stop, wait, romblock


class Msm6295BankTests(unittest.TestCase):
    def test_busy_request_is_ignored_without_retrigger_and_latch_is_consumed(self):
        raw = make_vgm(start() + wait(10) + start() + wait(10) + stop() + wait(5) + start() + wait(1000))
        native = interpret(analyze(raw))
        self.assertEqual(len(native.playbacks), 2)
        self.assertEqual(native.playbacks[0].termination, 'explicit_stop')
        self.assertEqual(native.playbacks[1].termination, 'natural_stop')
        ignored = [r for r in native.requests if r.get('reason') == 'voice_busy']
        self.assertEqual(len(ignored), 1)
        self.assertIsNone(native.states[-1]['pending_sample'])

    def test_full_assets_share_across_stop_length_gain_and_sample_aliases(self):
        payload = bytes((index * 29 + 7) & 255 for index in range(64))
        raw = make_vgm(start(1, level=0) + wait(100) + stop() + start(2, level=3) + wait(1000),
            rom=make_rom({1: payload, 2: payload}))
        with patch('msm6295_bank.decode_adpcm', wraps=decode_adpcm) as decode:
            result = project(analyze(raw), source_raw=raw)
        self.assertEqual(decode.call_count, 1)
        self.assertEqual(len(result.samples), 1)
        self.assertEqual(len(result.playbacks), 2)
        self.assertNotEqual(result.playbacks[0].target_volume, result.playbacks[1].target_volume)
        self.assertEqual(result.bank_assets[0]['source_nibbles'], 128)
        self.assertTrue(result.bank_assets[0]['complete_sample'])
        self.assertEqual(len(result.native_analysis.assets), 1)

    def test_natural_end_before_next_same_frame_request(self):
        # 44.1kHz native grid makes the exact last nibble boundary inspectable.
        raw = make_vgm(start() + wait(128) + start() + wait(128), clock=44100 * 132)
        native = interpret(analyze(raw))
        self.assertEqual(len(native.playbacks), 2)
        self.assertEqual([p.start_frame for p in native.playbacks], [0, 128])
        self.assertEqual([p.end_frame for p in native.playbacks], [128, 256])
        self.assertTrue(all(p.termination == 'natural_stop' for p in native.playbacks))
        self.assertEqual(native.playbacks[0].consumed_nibbles, 128)

    def test_multivoice_mask_stop_and_silent_busy_state(self):
        raw = make_vgm(write(0, 0x81) + write(0, 0x39) + wait(10) + start(channel=0) +
            wait(10) + write(0, 0x18) + wait(100))
        native = interpret(analyze(raw))
        self.assertEqual(len(native.playbacks), 2)
        self.assertEqual({p.source_channel for p in native.playbacks}, {0, 1})
        self.assertTrue(all(p.attenuation == 9 for p in native.playbacks))
        self.assertEqual(sum(r.get('reason') == 'voice_busy' for r in native.requests), 1)
        result = project(analyze(raw), source_raw=raw)
        self.assertEqual(len(result.playbacks), 0)
        self.assertEqual(len(result.samples), 0)
        self.assertEqual(result.bank_stats['silent_gate_count'], 2)

    def test_invalid_range_is_observed_ignore_not_missing_rom(self):
        raw = make_vgm(start(0) + start() + wait(1000))
        native = interpret(analyze(raw))
        self.assertEqual(len(native.playbacks), 1)
        self.assertTrue(any(r.get('reason') == 'reference_invalid_sample_range' for r in native.requests))
        with self.assertRaisesRegex(BankUnsupported, 'unavailable ROM'):
            interpret(analyze(make_vgm(start(), rom=b'', total=0x1000) + b''))

    def test_optional_unobserved_tail_is_distinct_from_missing_consumed_data(self):
        full = make_rom()
        prefix = full[:-32]
        raw = make_vgm(start() + wait(20) + stop(), rom=prefix, total=len(full))
        result = project(analyze(raw), source_raw=raw)
        self.assertFalse(result.bank_assets[0]['complete_sample'])
        self.assertEqual(result.bank_assets[0]['fallback'], 'optional_unavailable_tail')
        with self.assertRaisesRegex(BankUnsupported, 'consumes unavailable ROM'):
            interpret(analyze(make_vgm(start() + wait(1000), rom=prefix, total=len(full))))

    def test_no_commands_or_empty_rom_do_not_require_pcm(self):
        raw = make_vgm(wait(100), rom=b'', total=262144)
        result = project(analyze(raw), source_raw=raw)
        self.assertEqual(result.source_end_vgmticks, 100)
        self.assertEqual(result.samples, ())
        self.assertEqual(result.playbacks, ())

    def test_unsupported_mapping_and_resource_bounds_preserve_failure(self):
        raw = make_vgm(start() + write(15, 1) + wait(100))
        with self.assertRaisesRegex(BankUnsupported, 'unsupported clock/bank'):
            interpret(analyze(raw))
        raw = make_vgm(start() + wait(1000))
        with patch('msm6295_bank.MAX_NATIVE_SAMPLES', 10):
            with self.assertRaisesRegex(BankUnsupported, 'native decode budget'):
                project(analyze(raw), source_raw=raw)
        with patch('msm6295_bank.MAX_TARGET_SAMPLES', 10):
            with self.assertRaisesRegex(BankUnsupported, 'resampling budget'):
                project(analyze(raw), source_raw=raw)

    def test_loop_traversal_keeps_pending_latch_and_active_gate(self):
        raw = make_vgm(start() + wait(30) + start() + wait(30), loop_offset=len(start()))
        native = interpret(analyze(raw, loop_count=2))
        self.assertEqual(len(native.playbacks), 1)
        self.assertEqual(native.playbacks[0].termination, 'source_end')
        self.assertEqual(native.playbacks[0].end_vgmticks, 120)
        self.assertEqual(sum(r.get('reason') == 'voice_busy' for r in native.requests), 2)

    def test_completed_native_ir_survives_target_resource_failure(self):
        raw = make_vgm(start() + wait(1000))
        with tempfile.TemporaryDirectory() as temp:
            with patch('msm6295_bank.MAX_TARGET_SAMPLES', 10):
                with self.assertRaisesRegex(BankUnsupported, 'resampling budget'):
                    project(analyze(raw), source_raw=raw, outdir=temp, stem='AUTH')
            root = Path(temp)
            self.assertTrue((root / 'AUTH.msm6295.playbacks.csv').is_file())
            self.assertTrue((root / 'AUTH.msm6295.requests.csv').is_file())
            with (root / 'AUTH.msm6295.samples.csv').open() as stream:
                samples = list(csv.DictReader(stream))
            self.assertEqual(len(samples), 1)
            self.assertEqual(samples[0]['codec'], 'okim6295-adpcm4-high-first')
            self.assertTrue((root / samples[0]['file']).is_file())
            self.assertFalse((root / 'AUTH.msm6295_bank.assets.csv').exists())

    def test_native_grid_end_beyond_eof_is_bounded_only_in_target(self):
        raw = make_vgm(start() + wait(18), rom=make_rom({1: b'\x12\x34'}))
        trace = analyze(raw)
        result = project(trace, source_raw=raw)
        native = result.native_analysis.playbacks[0]
        self.assertEqual(native.end_frame, 4)
        self.assertEqual(native.end_vgmticks, Fraction(2352, 101))
        self.assertEqual(native.termination, 'natural_stop')
        self.assertEqual(result.playbacks[0].end_vgmticks, 18)
        event = result.bank_events[0]
        self.assertEqual(event['target_end_bound'], 'source_end')
        self.assertEqual(event['target_end_clipped_vgmticks'], 6)
        self.assertEqual(event['source_end_vgmticks'], str(native.end_vgmticks))

    def test_next_accepted_start_bounds_previous_target_without_extra_voice(self):
        raw = make_vgm(start() + wait(18) + start() + wait(100),
                       rom=make_rom({1: b'\x12\x34'}))
        result = project(analyze(raw), source_raw=raw)
        self.assertEqual(len(result.native_analysis.playbacks), 2)
        self.assertEqual(result.native_analysis.playbacks[0].end_vgmticks, Fraction(2352, 101))
        self.assertEqual(result.native_analysis.playbacks[1].start_frame, 4)
        self.assertEqual(result.playbacks[0].end_vgmticks, result.playbacks[1].start_vgmticks)
        self.assertEqual(result.playbacks[0].end_vgmticks, 18)
        self.assertEqual(result.bank_events[0]['target_end_bound'], 'next_accepted_start_same_channel')
        self.assertGreater(Fraction(result.bank_events[1]['native_start_grid_shift_vgmticks']), 1)
        self.assertLess(Fraction(result.bank_events[1]['native_start_grid_shift_vgmticks']), Fraction(44100, 7575))
        from pcm_mdx import project as target
        target_result = target(result, stem='AUTH')
        self.assertEqual(len({unit.track for unit in target_result.units if unit.kind == 'pcm_note'}), 1)

    def test_native_and_target_dumps_expose_separate_ids(self):
        raw = make_vgm(start() + wait(1000))
        result = project(analyze(raw), source_raw=raw)
        with tempfile.TemporaryDirectory() as temp:
            result.dump(temp, 'AUTH')
            root = Path(temp)
            self.assertTrue((root / 'AUTH.msm6295.playbacks.csv').is_file())
            self.assertTrue((root / 'AUTH.msm6295.requests.csv').is_file())
            self.assertTrue((root / 'AUTH.msm6295_bank.assets.csv').is_file())
            source = json.loads((root / 'AUTH.pcm_source.json').read_text())
            self.assertEqual(source['source_origin'], 'projected_msm6258_from_msm6295_bank')


if __name__ == '__main__':
    unittest.main()
