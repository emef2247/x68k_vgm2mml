"""Candidate/retained counts must not hide allocation and force losses."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'py'))
from pcm_bank_stats import RESULT_FIELDS, format_lines, summarize, result_columns


class PcmBankStatsTests(unittest.TestCase):
    def test_actual_track_columns_and_capacity_omissions_union(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder/'X.segapcm_projection.json').write_text(json.dumps(dict(
                requested='auto',selected='bank',sample_count=100,playback_count=150,
                stats=dict(unique_sample_count=100,asset_payload_bytes=1000))))
            data = bytearray(768)
            struct.pack_into('>II', data, 0, 768, 2)
            (folder/'X.pdx').write_bytes(data + b'\x01\x02')
            (folder/'X.pcm_bindings.csv').write_text('sample_id,bank,slot,file\n0,0,0,s.adpcm\n')
            (folder/'X.pcm_projection.csv').write_text('playback_id,mdx_track,target_track\n0,P,P\n1,Q,Q\n')
            (folder/'X.pcm_omitted_playbacks.csv').write_text('playback_id\n2\n')
            (folder/'X.pcm.force_capacity.json').write_text(json.dumps(dict(rows=[
                dict(playback_id=2,action='omit'),dict(playback_id=3,action='omit'),
                dict(playback_id=4,action='omit_normalization'),dict(playback_id=0,action='retain')])))
            summary = summarize(folder,'X',allow_binary=True)
            self.assertEqual(summary['tracks'], ['P','Q'])
            self.assertEqual(summary['omitted_playback_count'],3)
            self.assertEqual(summary['retained_payload_bytes'],2)
            self.assertEqual(summary['asset_payload_bytes'],1000)
            self.assertEqual(summary['pdx_byte_limit'], 1200000)
            self.assertTrue(summary['pdx_byte_budget_satisfied'])
            self.assertIsNone(summarize(folder, 'X')['pdx_byte_budget_satisfied'])
            self.assertEqual(result_columns(summary)['pcm_bank_tracks'],'P,Q')
            # Presence alone is not evidence that an old binary is current.
            self.assertIsNone(summarize(folder,'X')['pdx_bytes'])

    def test_no_selection_no_stale_stats(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(summarize(temp,'X'),{})

    def test_merge_summary_keeps_original_counts_and_unknown_recovery_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'X.segapcm_projection.json').write_text(json.dumps(dict(
                requested='auto', selected='bank', sample_count=120, playback_count=200,
                stats=dict(unique_sample_count=120, asset_payload_bytes=12000))))
            merge = dict(summary=dict(mode='similar', input_sample_count=120,
                output_sample_count=80, input_payload_bytes=12000, output_payload_bytes=8000,
                merged_playback_count=50, recovered_playback_count=None))
            path = folder / 'X.pcm_bank_merge.json'
            path.write_text(json.dumps(merge))
            before = path.read_bytes()
            stats = summarize(folder, 'X')
            self.assertEqual((stats['sample_count'], stats['asset_payload_bytes']), (120, 12000))
            self.assertEqual((stats['merge_samples_after'], stats['merge_bytes_after']), (80, 8000))
            self.assertIsNone(stats['retained_sample_count'])
            self.assertIsNone(stats['recovered_playback_count'])
            columns = result_columns(stats)
            self.assertEqual(tuple(columns), RESULT_FIELDS)
            self.assertEqual(columns['pcm_bank_merge_mode'], 'similar')
            self.assertEqual(columns['pcm_bank_merged_playbacks'], 50)
            self.assertEqual(columns['pcm_bank_recovered_playbacks'], '')
            lines = '\n'.join(format_lines(stats))
            self.assertIn('samples 120 -> 80; payload 12000 -> 8000 bytes', lines)
            self.assertIn('recovered capacity playbacks unmeasured', lines)
            self.assertEqual(path.read_bytes(), before)
            merge['summary']['recovered_playback_count'] = 23
            merge['summary']['newly_omitted_playback_count'] = 3
            merge['summary']['retained_playback_delta'] = 20
            path.write_text(json.dumps(merge))
            self.assertEqual(result_columns(summarize(folder, 'X'))['pcm_bank_recovered_playbacks'], 23)
            columns = result_columns(summarize(folder, 'X'))
            self.assertEqual(columns['pcm_bank_newly_omitted_playbacks'], 3)
            self.assertEqual(columns['pcm_bank_retained_playback_delta'], 20)
            merge['summary'].update(mode='budget96', budget_limit=96,
                budget_input_sample_count=161, forced_sample_count=65, forced_playback_count=146)
            path.write_text(json.dumps(merge))
            stats = summarize(folder, 'X')
            self.assertEqual(result_columns(stats)['pcm_bank_budget_limit'], 96)
            self.assertEqual(result_columns(stats)['pcm_bank_forced_playbacks'], 146)
            self.assertIn('forced replacement 65 samples / 146 playbacks', '\n'.join(format_lines(stats)))
            merge['summary'].update(budget_input_pdx_bytes=1311468, budget_output_pdx_bytes=1180398)
            path.write_text(json.dumps(merge))
            stats = summarize(folder, 'X')
            columns = result_columns(stats)
            self.assertEqual(columns['pcm_bank_budget_input_pdx_bytes'], 1311468)
            self.assertEqual(columns['pcm_bank_budget_output_pdx_bytes'], 1180398)
            self.assertEqual(columns['pcm_bank_pdx_byte_limit'], 1200000)
            self.assertEqual(columns['pcm_bank_pdx_byte_budget_satisfied'], '')
            self.assertIn('Planned PDX bytes: 1311468 -> 1180398', '\n'.join(format_lines(stats)))


    def test_nonmerged_pcm_reports_current_binary_budget_without_inventing_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'X.pcm.timing.json').write_text(json.dumps(dict(
                pcm_source_origin='projected_msm6258_from_psg', pcm_payload_bytes=32)))
            (folder / 'X.pdx').write_bytes(b'x' * 800)
            stats = summarize(folder, 'X', allow_binary=True)
            self.assertEqual(stats['selected'], 'projected_msm6258_from_psg')
            self.assertIsNone(stats['sample_count'])
            self.assertIsNone(stats['playback_count'])
            self.assertEqual(stats['pdx_bytes'], 800)
            self.assertTrue(stats['pdx_byte_budget_satisfied'])
            self.assertEqual(stats['pdx_byte_limit'], 1200000)


if __name__ == '__main__':
    unittest.main()
