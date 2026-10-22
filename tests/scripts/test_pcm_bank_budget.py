"""Authored capacity-first target projection checks; no private fixtures."""
from collections import Counter
from dataclasses import replace
import math
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from pcm_bank_budget import enforce_budget, _select
from pcm_bank_reduce import reduce_bank, _decode, _gain
from test_pcm_bank_reduce import make_analysis, tone


def many_sounds(count=99):
    waves = []
    for sid in range(count):
        random = np.random.default_rng(sid)
        audio = random.integers(-12000, 12001, size=256)
        audio = np.rint(audio * np.exp(-np.arange(256) * (sid + 1) / 3000)).astype(int)
        waves.append(audio)
    return make_analysis(waves)


class PcmBankBudgetTests(unittest.TestCase):
    def test_default_dispatch_and_explicit_modes(self):
        source = make_analysis([tone(), tone(amplitude=9000)])
        budget = reduce_bank(source)
        self.assertEqual(budget.summary['mode'], 'budget96')
        self.assertEqual(budget.summary['budget_limit'], 96)
        self.assertEqual(budget.analysis.samples, reduce_bank(source, mode='similar').analysis.samples)
        self.assertEqual(len(reduce_bank(source, mode='off').analysis.samples), 2)

    def test_99_distinct_assets_fit_without_dropping_events_or_source(self):
        source = many_sounds()
        strict = reduce_bank(source, mode='off')
        result = enforce_budget(source, strict)
        self.assertEqual(len(result.analysis.samples), 96)
        self.assertEqual(len(result.analysis.playbacks), 99)
        self.assertEqual(len(source.samples), 99)
        self.assertEqual([p.sample_id for p in source.playbacks], list(range(99)))
        ids = {s.sample_id for s in result.analysis.samples}
        self.assertLessEqual({p.sample_id for p in result.analysis.playbacks}, ids)
        self.assertGreater(result.summary['forced_playback_count'], 0)
        self.assertFalse(result.summary['budget_similarity_bounds_enforced'])
        from pcm_mdx import project
        plan = project(result.analysis, stem='AUTHORED', policy='best-effort', force=False)
        self.assertEqual(len(plan.bindings), 96)
        self.assertEqual(len(plan.rows), 99)
        for a, b in zip(source.playbacks, result.analysis.playbacks):
            self.assertEqual((a.start_vgmticks, a.end_vgmticks, a.rate_num, a.rate_den, a.pan),
                             (b.start_vgmticks, b.end_vgmticks, b.rate_num, b.rate_den, b.pan))
        again = enforce_budget(source, strict)
        self.assertEqual(result.sample_rows, again.sample_rows)
        self.assertEqual(result.playback_rows, again.playback_rows)

    def test_coverage_keeps_rare_outlier_after_common_cluster_is_covered(self):
        # 97 nearly interchangeable high-use sounds and one rare remote sound.
        positions = np.concatenate((np.arange(97) * .00001, [10.0]))
        distances = abs(positions[:, None] - positions[None, :])
        indices = _select(distances, np.asarray([100] * 97 + [1]), 96, np)
        self.assertIn(97, indices)

    def test_original_gain_used_directly_when_intermediate_representative_is_removed(self):
        source = many_sounds()
        source = replace(source, playbacks=(*source.playbacks[:-1],
                          replace(source.playbacks[-1], target_volume=137)))
        strict = reduce_bank(source, mode='off')
        previous = list(strict.analysis.playbacks)
        previous[-1] = replace(previous[-1], sample_id=97, target_volume=160)
        strict = replace(strict, analysis=replace(strict.analysis, playbacks=tuple(previous)))
        with patch('pcm_bank_budget._select', return_value=list(range(96))):
            result = enforce_budget(source, strict)
        row = result.playback_rows[-1]
        self.assertEqual(row['original_volume'], 137)
        old = _decode(source.samples[98].encoded_bytes, np)
        rep = _decode(source.samples[row['target_sample_id']].encoded_bytes, np)
        count = row['checked_gate_frames']
        expected = _gain(137) * np.linalg.norm(old[:count]) / np.linalg.norm(rep[:count])
        self.assertAlmostEqual(row['desired_gain'], expected)
        self.assertTrue(all(math.isfinite(row[name]) for name in ('waveform_error', 'relative_gain_error')))

    def test_normalization_omitted_references_and_unreferenced_assets_cannot_break_cap(self):
        source = many_sounds()
        source = replace(source, playbacks=tuple(replace(p, end_vgmticks=p.start_vgmticks + 100)
                                                 for p in source.playbacks))
        omitted = tuple(p.playback_id for p in source.playbacks)
        strict = reduce_bank(source, mode='off', omit_playback_ids=omitted)
        result = enforce_budget(source, strict)
        self.assertLessEqual(len(result.analysis.samples), 96)
        self.assertTrue(all(r['explicit_omission'] for r in result.playback_rows))
        self.assertEqual(result.summary['forced_playback_count'], 0)
        self.assertLessEqual({p.sample_id for p in result.analysis.playbacks},
                             {s.sample_id for s in result.analysis.samples})
        empty = replace(source, playbacks=())
        empty_result = enforce_budget(empty, reduce_bank(empty, mode='off'))
        self.assertEqual(empty_result.analysis.samples, ())

    def test_different_rates_mute_and_headroom_are_reported_not_rejected(self):
        source = many_sounds()
        events = list(source.playbacks)
        events[97] = replace(events[97], target_volume=255, rate_num=78125, rate_den=8)
        source = replace(source, playbacks=tuple(events))
        strict = reduce_bank(source, mode='off')
        with patch('pcm_bank_budget._select', return_value=list(range(96))):
            result = enforce_budget(source, strict)
        self.assertEqual(result.analysis.playbacks[97].target_volume, 255)
        self.assertEqual(result.analysis.playbacks[97].rate_hz, source.playbacks[97].rate_hz)
        self.assertTrue(all(math.isfinite(v) for v in result.summary['forced_worst_errors'].values()))

    def test_under_96_assets_over_byte_limit_reuse_existing_samples(self):
        from pcm_capacity import PDX_BYTE_LIMIT, packed_pdx_bytes
        source = make_analysis([tone(length=256)] * 20)
        source = replace(source, samples=tuple(replace(sample,
            encoded_bytes=sample.encoded_bytes * 511 + sample.encoded_bytes[:127])
            for sample in source.samples))
        source = replace(source, samples=tuple(replace(sample,
            sha256=hashlib.sha256(sample.encoded_bytes).hexdigest()) for sample in source.samples))
        original_samples = source.samples
        strict = reduce_bank(source, mode='off')
        # Lengths are realistic maximum-sized assets; their short authored
        # attack suffices for this capacity-policy check without long FFTs.
        audio = _decode(original_samples[0].encoded_bytes[:128], np)
        with patch('pcm_bank_reduce._decode', return_value=audio):
            result = enforce_budget(source, strict)
        self.assertEqual(len(result.analysis.samples), 18)
        self.assertEqual(len(result.analysis.playbacks), 20)
        self.assertEqual(source.samples, original_samples)
        self.assertGreater(result.summary['budget_input_pdx_bytes'], PDX_BYTE_LIMIT)
        self.assertEqual(result.summary['budget_output_pdx_bytes'], packed_pdx_bytes(result.analysis.samples))
        self.assertLessEqual(packed_pdx_bytes(result.analysis.samples), PDX_BYTE_LIMIT)
        self.assertTrue(result.summary['byte_budget_satisfied'])
        ids = {sample.sample_id for sample in result.analysis.samples}
        self.assertLessEqual({p.sample_id for p in result.analysis.playbacks}, ids)
        self.assertGreater(result.summary['forced_playback_count'], 0)
        self.assertFalse(any(row['explicit_omission'] for row in result.playback_rows))
        for before, after in zip(source.playbacks, result.analysis.playbacks):
            self.assertEqual((before.start_vgmticks, before.end_vgmticks, before.rate_num,
                              before.rate_den, before.pan),
                             (after.start_vgmticks, after.end_vgmticks, after.rate_num,
                              after.rate_den, after.pan))

    def test_exact_byte_boundary_does_not_replace_samples(self):
        from pcm_capacity import PDX_BYTE_LIMIT, PDX_TABLE_BYTES
        source = make_analysis([tone(length=256)] * 19)
        remaining = PDX_BYTE_LIMIT - PDX_TABLE_BYTES - 18 * 65535
        source = replace(source, samples=tuple(replace(sample,
            encoded_bytes=(sample.encoded_bytes * 512)[:65535 if i < 18 else remaining])
            for i, sample in enumerate(source.samples)))
        source = replace(source, samples=tuple(replace(sample,
            sha256=hashlib.sha256(sample.encoded_bytes).hexdigest()) for sample in source.samples))
        result = enforce_budget(source, reduce_bank(source, mode='off'))
        self.assertEqual(result.analysis.samples, source.samples)
        self.assertEqual(result.summary['budget_output_pdx_bytes'], PDX_BYTE_LIMIT)
        self.assertEqual(result.summary['forced_playback_count'], 0)

    def test_byte_selector_skips_unaffordable_columns_and_is_deterministic(self):
        distances = np.asarray([[0., 1., 9.], [1., 0., 8.], [9., 8., 0.]])
        kwargs = dict(costs=[9, 4, 4], byte_budget=8)
        first = _select(distances, np.ones(3), 96, np, **kwargs)
        self.assertEqual(set(first), {1, 2})
        self.assertEqual(first, _select(distances, np.ones(3), 96, np, **kwargs))

    def test_onset_repair_frees_enough_payload_before_reserving_asset(self):
        from pcm_bank_budget import _reserve_representative
        source = make_analysis([tone(length=256)] * 20)
        samples = {sample.sample_id: replace(sample, encoded_bytes=b'x' *
                   (65535 if sample.sample_id == 19 else 63000)) for sample in source.samples}
        repaired = _reserve_representative(list(range(19)), 19, samples)
        self.assertIn(19, repaired)
        self.assertEqual(len(repaired), 18)
        from pcm_capacity import PDX_BYTE_LIMIT, packed_pdx_bytes
        self.assertLessEqual(packed_pdx_bytes(samples[sid] for sid in repaired), PDX_BYTE_LIMIT)

    def test_explicit_similar_and_off_do_not_impose_budget(self):
        source = many_sounds()
        self.assertEqual(len(reduce_bank(source, mode='off').analysis.samples), 99)
        # A one-sample strict-pass fixture exercises the unchanged explicit
        # policy without expensive duplicated analysis of 99 authored sounds.
        strict = reduce_bank(make_analysis([tone()]), mode='similar')
        self.assertNotIn('budget_limit', strict.summary)

    def test_short_attack_cannot_be_replaced_by_a_silent_prefix(self):
        delayed = np.concatenate((np.zeros(128, dtype=int), tone(length=128)))
        waves = [delayed] * 98 + [tone(length=256)]
        source = make_analysis(waves, gates={98: 60})
        strict = reduce_bank(source, mode='off')
        with patch('pcm_bank_budget._select', return_value=list(range(96))):
            result = enforce_budget(source, strict)
        p = result.analysis.playbacks[98]
        sample = next(s for s in result.analysis.samples if s.sample_id == p.sample_id)
        from pcm_bank_budget import _ac_peak, AC_NOISE_FLOOR
        frames = result.playback_rows[98]['checked_gate_frames']
        self.assertGreater(_ac_peak(_decode(sample.encoded_bytes, np)[:frames], np) * _gain(p.target_volume),
                           AC_NOISE_FLOOR)


if __name__ == '__main__':
    unittest.main()
