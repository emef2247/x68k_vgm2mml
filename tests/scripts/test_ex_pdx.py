"""EX-PDX/legacy boundaries using authored PCM assets, never private inputs."""
from dataclasses import replace
from pathlib import Path
import struct
import hashlib
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
from pcm_assessment import ProjectionError
from pcm_capacity import PDX_BYTE_LIMIT, PDX_TABLE_BYTES, sample_byte_limit
from pcm_mdx import project, write_pdx, default_generator
from pcm_force_capacity import select_capacity
from pcm_bank_reduce import reduce_bank
from pcm_bank_budget import enforce_budget
from pcm_bank_target import prepare
import test_pcm_force_capacity as force_fixtures


class ExPdxTests(unittest.TestCase):
    def source(self, lengths):
        source = force_fixtures.ForceCapacityTests().source(lengths)
        return replace(source, samples=tuple(replace(s, sha256=hashlib.sha256(s.encoded_bytes).hexdigest())
                                              for s in source.samples))

    def test_length_boundary_uses_target_format_without_changing_source(self):
        for size in (65535, 65536, 249856):
            source = self.source([size])
            unchanged = source
            plan = project(source, stem='BOUNDARY')
            self.assertEqual(plan.pdx_format, 'ex-pdx')
            self.assertEqual(len(plan.bindings), 1)
            self.assertEqual(plan.summary()['pcm_sample_byte_limit'], 0xffffff)
            if size <= 65535:
                self.assertEqual(len(project(source, stem='LEGACY', pdx_format='standard').bindings), 1)
            else:
                with self.assertRaises(ProjectionError) as caught:
                    project(source, stem='LEGACY', pdx_format='standard')
                self.assertIn('sample_length_overflow', [i['code'] for i in caught.exception.assessment.items])
            self.assertEqual(source, unchanged)

    def test_force_keeps_large_ex_asset_and_its_reuses(self):
        source = self.source([249856])
        again = replace(source.playbacks[0], playback_id=1,
                        start_vgmticks=10000, end_vgmticks=20000)
        source = replace(source, playbacks=(*source.playbacks, again), source_end_vgmticks=20000)
        ex = project(source, stem='REUSE', force=True)
        self.assertEqual(len(ex.bindings), 1)
        self.assertEqual({row['playback_id'] for row in ex.rows}, {0, 1})
        self.assertFalse(ex.force_capacity.omitted_playback_ids)
        legacy = project(source, stem='REUSE', force=True, pdx_format='standard')
        self.assertFalse(legacy.bindings)
        self.assertEqual(legacy.force_capacity.omitted_playback_ids, {0, 1})

    def test_parallel_voice_allocation_keeps_large_ex_asset(self):
        from test_pcm_bank_reduce import make_analysis, tone
        source = make_analysis([tone(length=256)] * 2)
        source = replace(source, samples=tuple(replace(s, encoded_bytes=b'\x11' * 65536)
                                               for s in source.samples))
        ex = project(source, stem='PARALLEL', force=True, policy='best-effort')
        self.assertEqual(len(ex.rows), 2)
        self.assertFalse(ex.force_capacity.omitted_playback_ids)
        self.assertEqual(ex.pdx_format, 'ex-pdx')
        legacy = project(source, stem='PARALLEL', force=True, policy='best-effort', pdx_format='standard')
        self.assertFalse(legacy.bindings)

    @unittest.skipUnless(default_generator().is_file(), 'built PDX helper unavailable')
    def test_external_packer_long_length_and_exact_bytes(self):
        for fmt, size in (('standard', 65535), ('ex-pdx', 65536), ('ex-pdx', 249856)):
            source = self.source([size])
            plan = project(source, stem='PACKED', pdx_format=fmt)
            with tempfile.TemporaryDirectory() as folder:
                pdx = write_pdx(plan, source, folder, 'PACKED').read_bytes()
            offset, length = struct.unpack_from('>II', pdx)
            self.assertEqual((offset, length), (768, size))
            self.assertEqual(pdx[offset:], source.samples[0].encoded_bytes)
            self.assertEqual(pdx[4:8], size.to_bytes(4, 'big'))
            self.assertEqual(len(pdx), 768 + size)

    def test_file_budget_is_independent_from_extended_length(self):
        source = self.source([PDX_BYTE_LIMIT - PDX_TABLE_BYTES + 1, 32])
        view = select_capacity(source)
        self.assertEqual([s.sample_id for s in view.analysis.samples], [1])
        self.assertEqual(view.rows[0]['cap_kind'], 'pdx_byte_capacity')
        with self.assertRaises(ProjectionError) as caught:
            project(source, stem='TOTAL')
        self.assertIn('pdx_byte_capacity', [i['code'] for i in caught.exception.assessment.items])

    def test_budget_candidates_must_fit_file_as_well_as_format(self):
        source = self.source([PDX_BYTE_LIMIT - PDX_TABLE_BYTES + 1, 256])
        strict = reduce_bank(source, mode='off')
        budget = enforce_budget(source, strict)
        self.assertEqual([s.sample_id for s in budget.analysis.samples], [1])
        self.assertEqual(len(budget.analysis.playbacks), 2)
        self.assertEqual(budget.summary['pdx_format'], 'ex-pdx')
        self.assertTrue(budget.summary['byte_budget_satisfied'])

    def test_no_byte_feasible_representative_has_clear_failure(self):
        source = self.source([PDX_BYTE_LIMIT])
        strict = reduce_bank(source, mode='off')
        with self.assertRaisesRegex(ValueError, 'sample/file budget'):
            enforce_budget(source, strict)

    def test_source_bank_validation_uses_selected_format(self):
        source = self.source([65536])
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNotNone(prepare(source, outdir=folder, stem='EX'))
            self.assertIsNone(prepare(source, outdir=folder, stem='STANDARD', pdx_format='standard'))

    def test_invalid_format_rejected(self):
        with self.assertRaises(ValueError):
            sample_byte_limit('typo')
        with self.assertRaises(ValueError):
            project(self.source([32]), stem='BAD', pdx_format='typo')


if __name__ == '__main__':
    unittest.main()
