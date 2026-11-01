"""Capacity reports distinguish configured transfer arithmetic from playback."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from pcm_capacity import resolve_pcm_capacity
from pcm_bank_stats import RESULT_FIELDS, format_lines, result_columns, summarize


def write_json(folder, suffix, value):
    (folder / ('X.' + suffix)).write_text(json.dumps(value), encoding='utf-8')


def write_pdx(folder, count):
    payload = bytearray(count)
    struct.pack_into('>II', payload, 0, 768, count - 768)
    path = folder / 'X.pdx';path.write_bytes(payload)
    return path


class PcmCapacityStatsTests(unittest.TestCase):
    def test_unowned_binary_and_estimated_timing_do_not_become_measured_capacity(self):
        capacity = resolve_pcm_capacity(buffer_kib=2, loader='mxctrl', margin_bytes=1000)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder, 'pcm.timing.json', dict(pcm_source_origin='native_msm6258',
                pcm_capacity=capacity.summary(pdx_bytes=770), pcm_sample_count=1))
            write_pdx(folder, 800)
            result = summarize(folder, 'X')
            self.assertEqual(result['pdx_byte_limit'], 778)
            self.assertIsNone(result['pdx_bytes'])
            self.assertIsNone(result['pcm_transfer_bytes'])
            self.assertIsNone(result['pdx_byte_budget_satisfied'])
            self.assertEqual(result['pcm_buffer_capacity_check'], 'unmeasured')
            self.assertEqual(result['runtime_buffer_fit'], 'unmeasured')

    def test_current_binary_uses_whole_file_and_recomputes_wrapper_and_margin(self):
        capacity = resolve_pcm_capacity(buffer_kib=2, loader='mxctrl', margin_bytes=1000)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            # An old estimate fits, but the final file includes additional bytes.
            write_json(folder, 'pcm.timing.json', dict(pcm_source_origin='native_msm6258',
                pcm_capacity=capacity.summary(pdx_bytes=770)))
            write_pdx(folder, 800)
            result = summarize(folder, 'X', allow_binary=True)
            self.assertEqual(result['pcm_buffer_bytes'], 2048)
            self.assertEqual(result['pcm_loader_overhead_bytes'], 270)
            self.assertEqual(result['pcm_buffer_margin_bytes'], 1000)
            self.assertEqual(result['pcm_transfer_bytes'], 1070)
            self.assertEqual(result['pcm_buffer_capacity_check'], 'exceeds_budget')
            self.assertFalse(result['pdx_byte_budget_satisfied'])
            self.assertEqual(result['runtime_buffer_fit'], 'unmeasured')
            write_pdx(folder, 778)
            boundary = summarize(folder, 'X', allow_binary=True)
            self.assertTrue(boundary['pdx_byte_budget_satisfied'])
            self.assertEqual(boundary['pcm_transfer_bytes'], 1048)
            self.assertEqual(boundary['pcm_buffer_capacity_check'], 'within_budget')

    def test_ownership_hash_can_establish_the_current_binary_without_exporter_override(self):
        capacity = resolve_pcm_capacity(buffer_kib=2, loader='direct', margin_bytes=0)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder, 'pcm.timing.json', dict(pcm_capacity=capacity.summary()))
            path = write_pdx(folder, 900)
            write_json(folder, 'pcm.assessment.json', dict(artifacts=dict(pdx=dict(
                path=str(path.resolve()), status='generated', sha256=hashlib.sha256(path.read_bytes()).hexdigest()))))
            result = summarize(folder, 'X')
            self.assertEqual(result['pdx_bytes'], 900)
            self.assertEqual(result['binary_evidence'], 'assessment_sha256')
            self.assertEqual(result['pcm_buffer_capacity_check'], 'within_budget')
            path.write_bytes(path.read_bytes() + b'changed')
            self.assertIsNone(summarize(folder, 'X')['pcm_transfer_bytes'])

    def test_blocked_canonical_metadata_is_visible_without_projection_or_binary(self):
        capacity = resolve_pcm_capacity(buffer_kib=312, loader='mxctrl')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder, 'conversion.json', dict(status='blocked', pcm_options=dict(
                applicable=True, capacity=capacity.summary())))
            result = summarize(folder, 'X')
            self.assertEqual(result['pdx_byte_limit'], 315122)
            self.assertEqual(result['pcm_buffer_bytes'], 319488)
            self.assertEqual(result['pcm_buffer_capacity_check'], 'unmeasured')
            self.assertIsNone(result['pdx_bytes'])
            lines = '\n'.join(format_lines(result))
            self.assertIn('loader mxctrl; overhead 270 bytes; margin 4096 bytes', lines)
            self.assertIn('PCM transfer: unmeasured bytes', lines)
            self.assertIn('Runtime PCM buffer fit: unmeasured', lines)

    def test_current_canonical_policy_overrides_a_stale_timing_policy(self):
        capacity = resolve_pcm_capacity(buffer_kib=2, loader='direct', margin_bytes=0)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder, 'conversion.json', dict(status='blocked', pcm_options=dict(
                applicable=True, capacity=capacity.summary())))
            write_json(folder, 'pcm.timing.json', dict(pcm_capacity=resolve_pcm_capacity().summary()))
            self.assertEqual(summarize(folder, 'X')['pdx_byte_limit'], 2048)

    def test_source_validation_only_and_reduction_only_retain_configured_policy(self):
        capacity = resolve_pcm_capacity(buffer_kib=2, loader='direct', margin_bytes=0)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder, 'pcm_bank.source_validation.json', dict(status='blocked',
                source_origin='native_msm6258', capacity=capacity.summary()))
            result = summarize(folder, 'X')
            self.assertEqual(result['pdx_byte_limit'], 2048)
            self.assertIsNone(result['pcm_transfer_bytes'])
            (folder / 'X.pcm_bank.source_validation.json').unlink()
            write_json(folder, 'pcm_bank_merge.json', dict(summary=dict(mode='budget96',
                input_sample_count=4, input_payload_bytes=1024, output_sample_count=2,
                output_payload_bytes=512, capacity=capacity.summary())))
            result = summarize(folder, 'X')
            self.assertEqual(result['pdx_byte_limit'], 2048)
            self.assertEqual(result['merge_samples_after'], 2)
            self.assertEqual(result['pcm_buffer_capacity_check'], 'unmeasured')

    def test_explicit_empty_target_reports_no_required_transfer_without_measuring_a_file(self):
        capacity = resolve_pcm_capacity(buffer_kib=2, loader='mxctrl', margin_bytes=0)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder, 'pcm.timing.json', dict(pcm_sample_count=0, pcm_capacity=capacity.summary()))
            result = summarize(folder, 'X')
            self.assertEqual(result['pcm_transfer_bytes'], 0)
            self.assertEqual(result['pcm_buffer_capacity_check'], 'not_required')
            self.assertIsNone(result['pdx_bytes'])
            self.assertIsNone(result['pdx_byte_budget_satisfied'])

    def test_result_column_order_and_defaults_keep_all_capacity_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder, 'pcm.timing.json', dict(pcm_source_origin='projected_msm6258_from_psg'))
            result = summarize(folder, 'X')
            columns = result_columns(result)
            self.assertEqual(tuple(columns), RESULT_FIELDS)
            self.assertEqual(columns['pcm_bank_pdx_operational_byte_limit'], 315122)
            self.assertEqual(columns['pcm_bank_buffer_bytes'], '')
            self.assertEqual(columns['pcm_bank_transfer_bytes'], '')
            self.assertEqual(columns['pcm_bank_buffer_capacity_check'], 'unconfigured')
            self.assertNotIn('PCM buffer capacity:', '\n'.join(format_lines(result)))

    def test_non_pcm_input_does_not_gain_generic_pcm_statistics_from_options_alone(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            write_json(folder, 'conversion.json', dict(pcm_options=dict(applicable=False,
                capacity=resolve_pcm_capacity().summary())))
            self.assertEqual(summarize(folder, 'X'), {})


if __name__ == '__main__':unittest.main()
