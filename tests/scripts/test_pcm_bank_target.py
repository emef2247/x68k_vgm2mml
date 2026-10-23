"""Native-source eligibility must survive common PCM8 bank projection."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
from pcm_bank_target import prepare
from pcm_bank_reduce import reduce_bank
from pcm_mdx import project
from pcm_assessment import ProjectionError
from test_pcm_bank_reduce import make_analysis, tone
from test_pcm_bank_budget import many_sounds
from msm6258 import PcmAnalysis, PcmPlayback
from dataclasses import fields


def native_copy(bank):
    values = {field.name: getattr(bank, field.name) for field in fields(PcmAnalysis)}
    values['playbacks'] = tuple(PcmPlayback(**{f.name: getattr(p, f.name)
        for f in fields(PcmPlayback)}) for p in bank.playbacks)
    return PcmAnalysis(**values)


class CommonPcmBankTests(unittest.TestCase):
    def test_native_source_and_supply_fields_survive_target_replacement(self):
        source = make_analysis([tone(), tone(amplitude=9000)], parallel=False)
        with tempfile.TemporaryDirectory() as folder:
            target = prepare(source, outdir=folder, stem='NATIVE', policy='best-effort')
            reduced = reduce_bank(target)
            plan = project(reduced.analysis, stem='NATIVE', policy='best-effort')
            self.assertEqual(len(source.samples), 2)
            self.assertEqual(len(plan.bindings), 1)
            self.assertEqual(target.transfers, source.transfers)
            self.assertEqual(target.controls, source.controls)
            for before, after in zip(source.playbacks, reduced.analysis.playbacks):
                for field in ('supplied_bytes', 'transfer_start', 'transfer_end',
                              'reset_origin', 'start_vgmticks', 'end_vgmticks'):
                    self.assertEqual(getattr(before, field), getattr(after, field))
            self.assertTrue(reduced.analysis.target_evidence)
            with self.assertRaises(ProjectionError):
                project(reduced.analysis, stem='STRICT', policy='strict')
            report = json.loads((Path(folder) / 'NATIVE.pcm_bank.source_validation.json').read_text())
            self.assertEqual(report['status'], 'validated')

    def test_unknown_independent_reset_is_not_repaired_by_bank_mode(self):
        source = make_analysis([tone()], parallel=False)
        source = replace(source, playbacks=(replace(source.playbacks[0],
            independently_playable=False, issues=('decoder_reset_unknown',)),))
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ProjectionError):
            prepare(source, outdir=folder, stem='BAD', policy='best-effort')

    def test_native_preflight_does_not_apply_slot_limit_before_reduction(self):
        source = native_copy(many_sounds())
        with tempfile.TemporaryDirectory() as folder:
            target = prepare(source, outdir=folder, stem='MANY', policy='best-effort')
            self.assertEqual(len(target.samples), 99)
            result = reduce_bank(target)
            self.assertLessEqual(len(result.analysis.samples), 96)
            plan = project(result.analysis, stem='MANY', policy='best-effort', force=False)
            self.assertEqual(len(plan.rows), 99)
            self.assertFalse(plan.omitted_playbacks)

    def test_no_bounded_material_preserves_existing_capacity_fallback(self):
        source = make_analysis([tone()], parallel=False)
        payload = b'\x12' * 65536
        source = replace(source, samples=(replace(source.samples[0], encoded_bytes=payload,
            sha256=hashlib.sha256(payload).hexdigest()),))
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(prepare(source, outdir=folder, stem='LONG', policy='best-effort', pdx_format='standard'))
            self.assertEqual(len(project(source, stem='LONG', policy='best-effort', force=True, pdx_format='standard').bindings), 0)


if __name__ == '__main__':
    unittest.main()
