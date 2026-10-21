"""Authored single-bank encoded file capacity checks, without private input."""
from dataclasses import replace
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts'), str(ROOT / 'tests/scripts')]
from pcm_assessment import ProjectionError
from pcm_capacity import PDX_BYTE_LIMIT, PDX_TABLE_BYTES, packed_pdx_bytes
from pcm_force_capacity import select_capacity
from pcm_mdx import project, write_pdx, default_generator
import test_pcm_force_capacity as force_fixtures
from test_pcm_bank_reduce import make_analysis, tone


class PcmPdxCapacityTests(unittest.TestCase):
    def source(self, lengths):
        return force_fixtures.ForceCapacityTests().source(lengths)

    def test_native_projection_accepts_exact_total_and_rejects_one_more_byte(self):
        remainder = PDX_BYTE_LIMIT - PDX_TABLE_BYTES - 18 * 65535
        exact = self.source([65535] * 18 + [remainder])
        plan = project(exact, stem='EXACT')
        self.assertEqual(len(plan.bindings), 19)
        self.assertEqual(packed_pdx_bytes(exact.samples), PDX_BYTE_LIMIT)
        oversized = self.source([65535] * 18 + [remainder + 1])
        with self.assertRaises(ProjectionError) as caught:
            project(oversized, stem='OVER')
        self.assertIn('1200001/1200000', str(caught.exception))
        self.assertTrue(any(item['criterion'] == 'capacity' and item['code'] == 'pdx_byte_capacity'
                            for item in caught.exception.assessment.items))

    def test_force_reuses_bound_sample_and_allows_smaller_later_new_asset(self):
        source = self.source([65535] * 19 + [100])
        repeat = replace(source.playbacks[0], playback_id=20,
                         start_vgmticks=200000, end_vgmticks=210000)
        source = replace(source, playbacks=(*source.playbacks, repeat), source_end_vgmticks=220000)
        snapshot = source
        view = select_capacity(source)
        self.assertEqual(view.omitted_playback_ids, {18})
        self.assertEqual(view.rows[18]['cap_kind'], 'pdx_byte_capacity')
        self.assertEqual(view.rows[19]['action'], 'retain')
        self.assertEqual(view.rows[20]['action'], 'retain')
        self.assertEqual([s.sample_id for s in view.analysis.samples], [*range(18), 19])
        self.assertLessEqual(packed_pdx_bytes(view.analysis.samples), PDX_BYTE_LIMIT)
        plan = project(source, stem='FORCED', force=True)
        self.assertEqual({binding.sample_id for binding in plan.bindings}, {*range(18), 19})
        self.assertTrue(any(row['playback_id'] == 20 for row in plan.rows))
        self.assertEqual(source, snapshot)
        self.assertEqual(plan.units[-1].source_end_vgmticks, source.source_end_vgmticks)

    def test_force_byte_overflow_does_not_hide_invalid_source(self):
        source = self.source([65535] * 19)
        source = replace(source, samples=(*source.samples[:-1],
                         replace(source.samples[-1], codec='unrecognized-codec')))
        with self.assertRaises(ProjectionError):
            project(source, stem='INVALID', force=True)

    def test_unreferenced_parallel_assets_do_not_consume_final_file_budget(self):
        source = make_analysis([tone(length=256)] * 20)
        source = replace(source,
            samples=tuple(replace(sample, encoded_bytes=b'\x11' * 65535)
                          for sample in source.samples),
            playbacks=source.playbacks[:1])
        self.assertGreater(packed_pdx_bytes(source.samples), PDX_BYTE_LIMIT)
        plan = project(source, stem='UNUSED', policy='best-effort', force=False)
        self.assertEqual([binding.sample_id for binding in plan.bindings], [0])
        self.assertEqual(plan.summary()['pcm_pdx_estimated_bytes'], 768 + 65535)
        self.assertTrue(plan.summary()['pcm_pdx_estimate_within_budget'])
        self.assertEqual(len(source.samples), 20)

    def test_parallel_byte_rejected_gate_occupies_no_target_voice(self):
        source = make_analysis([tone(length=256)] * 19)
        samples = tuple(replace(s, encoded_bytes=b'\x11' * 65535) for s in source.samples)
        initial = tuple(replace(p, start_vgmticks=i * 10000, end_vgmticks=(i + 1) * 10000)
                        for i, p in enumerate(source.playbacks[:18]))
        overflow = replace(source.playbacks[18], start_vgmticks=180000, end_vgmticks=280000)
        repeats = tuple(replace(source.playbacks[0], playback_id=19 + i,
                                first_source_event_id=100 + i, source_channel=i,
                                start_vgmticks=180000, end_vgmticks=190000)
                        for i in range(8))
        source = replace(source, samples=samples, playbacks=(*initial, overflow, *repeats),
                         source_end_vgmticks=300000)
        plan = project(source, stem='PARALLEL', force=True, policy='best-effort')
        self.assertEqual(plan.force_capacity.omitted_playback_ids, {18})
        self.assertTrue({p.playback_id for p in repeats} <= {row['playback_id'] for row in plan.rows})
        self.assertEqual(len({u.track for u in plan.units if u.kind == 'pcm_note'
                              and u.source_start_vgmticks == 180000}), 8)

    @unittest.skipUnless(default_generator().is_file(), 'built public MDX helper unavailable')
    def test_real_external_packer_preserves_exact_total_and_payloads(self):
        remainder = PDX_BYTE_LIMIT - PDX_TABLE_BYTES - 18 * 65535
        source = self.source([65535] * 18 + [remainder])
        plan = project(source, stem='EXACTPACK')
        with tempfile.TemporaryDirectory() as temp:
            result = write_pdx(plan, source, temp, 'EXACTPACK')
            self.assertEqual(result.stat().st_size, PDX_BYTE_LIMIT)
            payload = result.read_bytes()
            for binding in plan.bindings:
                offset, length = struct.unpack_from('>II', payload, binding.slot * 8)
                self.assertEqual(payload[offset:offset + length],
                                 source.samples[binding.sample_id].encoded_bytes)

    def test_oversized_packer_result_is_rejected_and_removed(self):
        source = self.source([32])
        plan = project(source, stem='PACKED')
        with tempfile.TemporaryDirectory() as temp:
            def pack(command, **kwargs):
                table = bytearray(PDX_TABLE_BYTES)
                struct.pack_into('>II', table, 0, PDX_TABLE_BYTES, 32)
                payload = bytes(table) + source.samples[0].encoded_bytes
                payload += b'\0' * (PDX_BYTE_LIMIT + 1 - len(payload))
                Path(command[-1]).write_bytes(payload)
                return subprocess.CompletedProcess(command, 0, '', '')
            with patch('pcm_mdx.subprocess.run', side_effect=pack):
                with self.assertRaisesRegex(ValueError, 'Packed PDX file byte capacity exceeded'):
                    write_pdx(plan, source, temp, 'PACKED', generator=__file__)
            self.assertFalse((Path(temp) / plan.pdx_name).exists())

    def test_estimate_rejects_before_running_external_packer(self):
        source = self.source([65535] * 19)
        # Deliberately stale plan must still be checked at the packing boundary.
        short = self.source([32] * 19)
        plan = project(short, stem='STALE')
        with tempfile.TemporaryDirectory() as temp:
            with patch('pcm_mdx.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'PDX file byte capacity exceeded'):
                    write_pdx(plan, source, temp, 'STALE', generator=__file__)
            run.assert_not_called()
            self.assertFalse((Path(temp) / plan.pdx_name).exists())


if __name__ == '__main__':
    unittest.main()
