"""Authored finite Delta-T bank checks; native playback is user validation."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))

from opna_adpcm import analyze
from opna_pcm_bank import project
from pcm8_volume import project_pcm8_volume
from pcm_mdx import project as project_mdx
from test_opna_adpcm import source


class OpnaPcmBankTests(unittest.TestCase):
    def pair(self):
        raw, _ = source(tail=bytes.fromhex(
            '61 28 00 57 00 01 57 0b 80 57 01 81 57 00 a0 61 64 00 57 00 01'))
        return raw, analyze(raw)

    def test_complete_asset_shared_across_gate_level_pan(self):
        raw, native = self.pair()
        before = repr(native)
        bank = project(native, source_raw=raw)
        self.assertIsNotNone(bank)
        self.assertEqual(len(bank.samples), 1)
        self.assertEqual(len(bank.playbacks), 2)
        self.assertEqual([p.sample_id for p in bank.playbacks], [0, 0])
        self.assertEqual([(p.start_vgmticks, p.end_vgmticks) for p in bank.playbacks],
                         [(0, 40), (40, 140)])
        self.assertEqual([p.pan for p in bank.playbacks], [0, 1])
        self.assertEqual([p.target_volume for p in bank.playbacks],
            [project_pcm8_volume(v, source_scale=256).raw_volume for v in (255, 128)])
        self.assertFalse(bank.bank_assets[0]['level_baked'])
        self.assertEqual(repr(native), before)
        single = replace(native, segments=(replace(native.segments[1], level=255),))
        self.assertEqual(project(single, source_raw=raw).samples, bank.samples)
        self.assertGreater(bank.bank_assets[0]['full_sample_count'], 0)
        self.assertFalse(bank.playbacks[0].reset_observed)
        self.assertEqual(bank.playbacks[0].supplied_bytes, 0)

    def test_gate_length_does_not_trim_asset(self):
        raw, native = self.pair()
        bank = project(native, source_raw=raw)
        shorter = replace(native, segments=(replace(native.segments[0], end_vgmticks=1),))
        self.assertEqual(project(shorter, source_raw=raw).samples, bank.samples)

    def test_held_controls_fall_back(self):
        raw, _ = source(tail=bytes.fromhex('61 0a 00 57 0b 80'))
        self.assertIsNone(project(analyze(raw), source_raw=raw))
        raw, native = self.pair()
        for parameters in ({'repeat': True}, {'rate_num': 0}, {'independently_playable': False}):
            altered = replace(native, segments=(replace(native.segments[0], **parameters),))
            self.assertIsNone(project(altered, source_raw=raw))

    def test_hash_corruption_is_error_not_fallback(self):
        raw, native = self.pair()
        with self.assertRaisesRegex(ValueError, 'source bytes differ'):
            project(native, source_raw=bytes(raw) + b'x')
        malformed = replace(native, samples=(replace(native.samples[0], sha256='bad'),))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            project(malformed, source_raw=raw)

    def test_resource_bound_falls_back_and_profile_changes_only_target(self):
        raw, native = self.pair()
        with patch('opna_pcm_bank.MAX_TOTAL_SAMPLES', 0):
            self.assertIsNone(project(native, source_raw=raw))
        standard = project(native, source_raw=raw)
        low = project(native, source_raw=raw, pcm_profile='ultra_low')
        self.assertLessEqual(len(low.samples[0].encoded_bytes), len(standard.samples[0].encoded_bytes))
        self.assertEqual(low.playbacks[1].end_vgmticks, standard.playbacks[1].end_vgmticks)

    def test_dump_and_actual_target_volume_commands(self):
        raw, native = self.pair()
        bank = project(native, source_raw=raw)
        plan = project_mdx(bank, stem='bank', policy='best-effort', tick_mapper=lambda t: t)
        self.assertEqual(len(plan.bindings), 1)
        self.assertEqual([row['target_volume'] for row in plan.rows],
                         [p.target_volume for p in bank.playbacks])
        with tempfile.TemporaryDirectory() as temporary:
            bank.dump(temporary, 'bank')
            root = Path(temporary)
            data = json.loads((root / 'bank.opna_pcm_bridge.json').read_text())
            self.assertEqual(data['target_sample_count'], 1)
            self.assertEqual(len(data['target_mapping']), 2)
            self.assertTrue((root / 'bank.opna_pcm_bank.assets.csv').is_file())
            self.assertIn('native_segment_id', (root / 'bank.opna_pcm_bank.events.csv').read_text())

    def test_facade_uses_bank_without_eager_per_gate_transcoding(self):
        from opna_opm import convert
        raw, _ = self.pair()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            src = root / 'case.vgm'
            src.write_bytes(raw)
            out = root / 'out'
            with patch('opm_conversion.convert', return_value=(out / 'case.mdx.mml', None, None)) as downstream, \
                    patch('opna_adpcm.project_msm6258', side_effect=AssertionError('legacy path executed')):
                _, settings = convert(src, out, song_loop=False, pcm_policy='best-effort')
            bank = downstream.call_args.kwargs['pcm_analysis_override']
            self.assertEqual(len(bank.samples), 1)
            self.assertEqual(len(bank.playbacks), 2)
            self.assertTrue(settings['pcm_ir']['finite_sample_bank'])


if __name__ == '__main__':
    unittest.main()
