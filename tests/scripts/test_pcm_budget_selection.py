"""Resolved playback capacity must reach each sample selection path unchanged."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(Path(__file__).parent)]
from pcm_capacity import PDX_TABLE_BYTES, packed_pdx_bytes, resolve_pcm_capacity
from pcm_bank_budget import enforce_budget, _reserve_representative
from pcm_bank_reduce import reduce_bank
from pcm_force_capacity import select_capacity
from pcm_bank_target import prepare
from test_pcm_bank_budget import many_sounds
from test_pcm_bank_reduce import make_analysis, tone


class PlaybackBudgetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.capacity = resolve_pcm_capacity(buffer_kib=1, loader='direct', margin_bytes=0)
        self.assertEqual(self.capacity.pdx_byte_limit, 1024)

    def test_small_byte_budget_selects_existing_assets_without_omitting_events(self):
        source = many_sounds(4)
        snapshot = source.samples, source.playbacks
        result = enforce_budget(source, reduce_bank(source, mode='off'), capacity=self.capacity)
        self.assertEqual(len(result.analysis.samples), 2)
        self.assertEqual(packed_pdx_bytes(result.analysis.samples), 1024)
        self.assertEqual(len(result.analysis.playbacks), 4)
        self.assertEqual((source.samples, source.playbacks), snapshot)
        self.assertEqual(result.summary['budget_byte_limit'], 1024)
        self.assertTrue(result.summary['byte_budget_satisfied'])
        self.assertGreater(result.summary['forced_playback_count'], 0)
        self.assertFalse(any(row['explicit_omission'] for row in result.playback_rows))
        for before, after in zip(source.playbacks, result.analysis.playbacks):
            self.assertEqual((before.start_vgmticks, before.end_vgmticks, before.rate_hz),
                             (after.start_vgmticks, after.end_vgmticks, after.rate_hz))

    def test_public_dispatch_passes_the_same_budget_to_capacity_enforcement(self):
        source = many_sounds(4)
        result = reduce_bank(source, capacity=self.capacity)
        self.assertLessEqual(packed_pdx_bytes(result.analysis.samples), 1024)
        self.assertEqual(result.summary['budget_byte_limit'], 1024)
        self.assertEqual(len(result.analysis.playbacks), 4)

    def test_representative_repair_accounts_for_table_and_replacement_bytes(self):
        source = make_analysis([tone(length=192), tone(length=256), tone(length=320)])
        samples = {s.sample_id: s for s in source.samples}
        repaired = _reserve_representative([0, 1], 2, samples, capacity=self.capacity)
        self.assertEqual(repaired, [0, 2])
        self.assertEqual(packed_pdx_bytes(samples[sid] for sid in repaired), 1024)
        too_large = replace(samples[2], encoded_bytes=b'\x12' * 257)
        with self.assertRaisesRegex(ValueError, 'no representative'):
            _reserve_representative([0, 1], 2, samples | {2: too_large}, capacity=self.capacity)

    def test_force_selects_whole_assets_and_reuse_costs_no_extra_bytes(self):
        source = make_analysis([tone(length=256)] * 4, parallel=False)
        replay = replace(source.playbacks[0], playback_id=4,
            start_vgmticks=80000, end_vgmticks=81000, first_source_event_id=50)
        source = replace(source, playbacks=(*source.playbacks, replay), source_end_vgmticks=82000)
        before = source.samples, source.playbacks
        view = select_capacity(source, capacity=self.capacity)
        self.assertIs(view.capacity, self.capacity)
        self.assertEqual([s.sample_id for s in view.analysis.samples], [0, 1])
        self.assertEqual(view.omitted_playback_ids, {2, 3})
        self.assertEqual(view.analysis.playbacks[-1], replay)
        self.assertEqual(view.rows[2]['actual'], 1152)
        self.assertEqual(view.rows[2]['limit'], 1024)
        self.assertEqual(view.summary()['pdx_byte_limit'], 1024)
        self.assertTrue(view.summary()['pdx_byte_budget_satisfied'])
        self.assertEqual((source.samples, source.playbacks), before)

    def test_force_view_default_remains_independent_after_custom_selection(self):
        source = make_analysis([tone(length=256)] * 4, parallel=False)
        limited = select_capacity(source, capacity=self.capacity)
        default = select_capacity(source)
        self.assertEqual(len(limited.analysis.samples), 2)
        self.assertEqual(len(default.analysis.samples), 4)
        self.assertEqual(default.summary()['pdx_byte_limit'], 315122)

    def test_native_target_preflight_uses_resolved_candidate_limit(self):
        source = make_analysis([tone(length=600)], parallel=False)
        self.assertGreater(len(source.samples[0].encoded_bytes), 1024 - PDX_TABLE_BYTES)
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(prepare(source, outdir=temporary, stem='TOO_LARGE',
                policy='best-effort', capacity=self.capacity))
            report = json.loads((Path(temporary) / 'TOO_LARGE.pcm_bank.source_validation.json').read_text())
            self.assertEqual(report['sample_byte_limit'], 256)
            self.assertFalse(report['bank_available'])
            self.assertEqual(len(source.samples[0].encoded_bytes), 300)

    def test_all_omitted_force_view_does_not_claim_a_required_pdx_transfer(self):
        source = make_analysis([tone(length=600)], parallel=False)
        view = select_capacity(source, capacity=self.capacity)
        self.assertFalse(view.analysis.samples)
        self.assertEqual(view.summary()['capacity']['pcm_transfer_bytes'], 0)
        self.assertEqual(view.summary()['capacity']['pcm_buffer_capacity_check'], 'not_required')

    def test_capacity_replacement_remains_a_reported_loss_under_strict_policy(self):
        from pcm_assessment import ProjectionError
        from pcm_mdx import project
        source = many_sounds(4)
        result = reduce_bank(source, capacity=self.capacity)
        with self.assertRaises(ProjectionError):
            project(result.analysis, stem='STRICT', policy='strict', capacity=self.capacity)
        accepted = project(result.analysis, stem='BEST', policy='best-effort', capacity=self.capacity)
        self.assertEqual(len(accepted.bindings), 2)


if __name__ == '__main__':unittest.main()
