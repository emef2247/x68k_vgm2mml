"""Authored PCM-block listening/ownership checks; no private conversion or playback."""
import csv
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from msm6258 import PcmSample
from pcm_block_wav import dump_pcm_block_wavs


def sample(sample_id, payload=b'\x21'):
    return PcmSample(sample_id, 'msm6258-adpcm4-low-first', payload, hashlib.sha256(payload).hexdigest())


def playback(playback_id, sample_id, rate=Fraction(15625, 3)):
    return SimpleNamespace(playback_id=playback_id, sample_id=sample_id,
        rate_hz=rate, rate_num=rate.numerator, rate_den=rate.denominator,
        chip_instance=0, source_channel=playback_id, start_vgmticks=10 * playback_id,
        end_vgmticks=100 + 10 * playback_id, first_source_event_id=playback_id + 10,
        last_source_event_id=playback_id + 20, pan=0, target_volume=128)


def analysis(samples=None, playbacks=None):
    return SimpleNamespace(samples=(sample(0), sample(1, b'\x12')) if samples is None else samples,
        playbacks=(playback(0, 0), playback(1, 1)) if playbacks is None else playbacks,
        pcm_profile='standard', source_origin='projected_msm6258_from_segapcm_bank',
        bank_assets=(dict(sample_id=0, asset_kind='finite_rom_view', target_sample_count=1),),
        bank_events=(dict(playback_id=0, source_channel=3, native_gate_id=17),), bank_waveforms=())


class PcmBlockWavTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.root = self.out / '_diagnostics' / 'CASE' / 'pcm_blocks'

    def read_frames(self, filename):
        with wave.open(str(self.root / filename), 'rb') as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth()), (1, 2))
            rate = wav.getframerate()
            values = struct.unpack('<' + str(wav.getnframes()) + 'h', wav.readframes(wav.getnframes()))
        return rate, values

    def test_low_first_reset_scale_rate_and_padding_are_inspectable(self):
        report = dump_pcm_block_wavs(analysis(), self.out, 'CASE')
        row = report['assets'][0]
        rate, values = self.read_frames(row['file'])
        self.assertEqual(rate, 5208)
        self.assertEqual(values, (256, 896))
        self.assertEqual(row['frame_count'], 2)
        self.assertEqual(row['logical_sample_counts'], '[1]')
        self.assertAlmostEqual(row['wav_rate_error_hz'], -1 / 3)
        self.assertIn('padding', row['frame_scope'])
        self.assertIn('predictor=-2', row['decoder_reset_assumption'])
        self.assertEqual(row['amplitude'], 'decoded asset scale; no normalization or playback gain')

    def test_capacity_omitted_samples_remain_listenable_with_usage_links(self):
        target = SimpleNamespace(bindings=(SimpleNamespace(sample_id=0),),
            rows=(dict(playback_id=0),), omitted_playbacks=(),
            force_capacity=SimpleNamespace(rows=(dict(playback_id=1, action='omit', reason='slot capacity'),)))
        report = dump_pcm_block_wavs(analysis(), self.out, 'CASE', plan=target)
        self.assertEqual(report['sample_count'], 2)
        self.assertEqual(report['wav_count'], 2)
        self.assertEqual([r['binding_status'] for r in report['assets']], ['retained', 'omitted'])
        self.assertTrue(all((self.root / r['file']).is_file() for r in report['assets']))
        with (self.root / report['playback_csv']).open(encoding='utf-8', newline='') as stream:
            uses = list(csv.DictReader(stream))
        self.assertEqual(uses[0]['native_gate_id'], '17')
        self.assertEqual(uses[1]['projection_status'], 'omitted')
        self.assertEqual(uses[1]['omission_reasons'], 'slot capacity')

    def test_same_asset_distinct_rates_not_distinct_onset_volume(self):
        first, second = playback(0, 0), playback(1, 0, Fraction(15625))
        second.target_volume = 137
        item = analysis((sample(0),), (first, second))
        report = dump_pcm_block_wavs(item, self.out, 'CASE')
        self.assertEqual(report['wav_count'], 2)
        decoded = [self.read_frames(row['file'])[1] for row in report['assets']]
        self.assertEqual(decoded[0], decoded[1])
        self.assertEqual(item.playbacks[1].target_volume, 137)

    def test_merged_member_remains_listenable_and_maps_to_representative(self):
        item = analysis()
        item.bank_events = (dict(playback_id=0, view_id='representative'),
                            dict(playback_id=1, view_id='member'))
        item.bank_waveforms = (dict(sample_id=1, view_id='member',
            samples=(100, -200), rate_num=15625, rate_den=3),)
        target = SimpleNamespace(bindings=(SimpleNamespace(sample_id=0),),
            rows=(dict(playback_id=0, sample_id=0, target_volume=128),
                  dict(playback_id=1, sample_id=0, target_volume=137)),
            omitted_playbacks=(), force_capacity=None)
        report = dump_pcm_block_wavs(item, self.out, 'CASE', plan=target)
        decoded = [row for row in report['assets'] if row['stage'] == 'decoded_adpcm']
        self.assertEqual([row['binding_status'] for row in decoded], ['retained', 'represented'])
        member = decoded[1]
        self.assertEqual(member['encoded_sha256'], item.samples[1].sha256)
        self.assertEqual(member['target_sample_ids'], '[0]')
        self.assertEqual(member['represented_playback_count'], 1)
        self.assertEqual(member['retained_playback_count'], 1)
        self.assertEqual(member['omitted_playback_count'], 0)
        preview = next(row for row in report['assets'] if row['stage'] == 'pre_adpcm')
        self.assertEqual(preview['binding_status'], 'represented')
        self.assertEqual(preview['playback_ids'], '[1]')
        self.assertEqual(preview['target_sample_ids'], '[0]')
        with (self.root / report['playback_csv']).open(encoding='utf-8', newline='') as stream:
            uses = list(csv.DictReader(stream))
        self.assertEqual(uses[1]['projection_status'], 'represented')
        self.assertEqual(uses[1]['sample_id'], '1')
        self.assertEqual(uses[1]['target_sample_id'], '0')
        self.assertEqual(uses[1]['target_volume'], '128')
        self.assertEqual(uses[1]['projected_target_volume'], '137')

    def test_optional_pre_adpcm_asset_is_unscaled_and_distinct_from_decoded(self):
        item = analysis((sample(0),), (playback(0, 0),))
        item.bank_waveforms = (dict(sample_id=0, view_id='source-view',
            samples=(0, 1000, -2000), rate_num=15625, rate_den=3),)
        report = dump_pcm_block_wavs(item, self.out, 'CASE')
        self.assertEqual(report['wav_count'], 2)
        row = next(r for r in report['assets'] if r['stage'] == 'pre_adpcm')
        self.assertEqual(self.read_frames(row['file'])[1], (0, 1000, -2000))
        self.assertEqual(row['source_view_id'], 'source-view')
        self.assertEqual(row['frame_count'], 3)
        self.assertIn('before ADPCM', row['decoder_reset_assumption'])
        self.assertEqual(row['usage_scope'], 'encoded_sample')
        self.assertIn('source-derived resampled asset', row['amplitude'])

    def test_deduplicated_encoded_asset_keeps_pre_adpcm_view_usage_separate(self):
        item = analysis((sample(0),), (playback(0, 0), playback(1, 0)))
        item.bank_events = (dict(playback_id=0, view_id='view-a'), dict(playback_id=1, view_id='view-b'))
        item.bank_waveforms = tuple(dict(sample_id=0, view_id=view,
            samples=(0, 1000), rate_num=15625, rate_den=3) for view in ('view-a', 'view-b'))
        target = SimpleNamespace(bindings=(SimpleNamespace(sample_id=0),), rows=(dict(playback_id=0),),
            omitted_playbacks=(dict(playback_id=1, reason='normalization'),), force_capacity=None)
        report = dump_pcm_block_wavs(item, self.out, 'CASE', plan=target)
        decoded = next(row for row in report['assets'] if row['stage'] == 'decoded_adpcm')
        self.assertEqual(decoded['playback_ids'], '[0, 1]')
        previews = [row for row in report['assets'] if row['stage'] == 'pre_adpcm']
        self.assertEqual([row['usage_scope'] for row in previews], ['source_view', 'source_view'])
        self.assertEqual([row['playback_ids'] for row in previews], ['[0]', '[1]'])
        self.assertEqual([row['retained_playback_count'] for row in previews], [1, 0])
        self.assertEqual([row['omitted_playback_count'] for row in previews], [0, 1])
        self.assertEqual([row['binding_status'] for row in previews], ['retained', 'omitted'])

    def test_rerun_preserves_modified_wav_and_unowned_files(self):
        report = dump_pcm_block_wavs(analysis(), self.out, 'CASE')
        modified = self.root / report['assets'][0]['file']
        modified.write_bytes(b'user edit')
        before = (self.root / 'CASE.manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'modified or unowned'):
            dump_pcm_block_wavs(analysis(), self.out, 'CASE')
        self.assertEqual(modified.read_bytes(), b'user edit')
        self.assertEqual((self.root / 'CASE.manifest.json').read_bytes(), before)

    def test_obsolete_owned_outputs_removed_and_unrelated_files_preserved(self):
        report = dump_pcm_block_wavs(analysis(), self.out, 'CASE')
        obsolete = self.root / report['assets'][1]['file']
        other = self.root / 'my-recording.wav'
        other.write_bytes(b'unrelated')
        dump_pcm_block_wavs(analysis((sample(0),), (playback(0, 0),)), self.out, 'CASE')
        self.assertFalse(obsolete.exists())
        self.assertEqual(other.read_bytes(), b'unrelated')

    def test_without_manifest_preexisting_generated_name_is_not_overwritten(self):
        report = dump_pcm_block_wavs(analysis(), self.out, 'CASE')
        (self.root / 'CASE.manifest.json').unlink()
        wav = self.root / report['assets'][0]['file']
        before = wav.read_bytes()
        with self.assertRaisesRegex(ValueError, 'modified or unowned'):
            dump_pcm_block_wavs(analysis(), self.out, 'CASE')
        self.assertEqual(wav.read_bytes(), before)

    def test_unreferenced_asset_uses_explicit_profile_with_unbound_status(self):
        target = SimpleNamespace(bindings=(), rows=(), omitted_playbacks=(), force_capacity=None)
        report = dump_pcm_block_wavs(analysis((sample(0),), ()), self.out, 'CASE', plan=target)
        self.assertEqual(report['assets'][0]['rate_origin'], 'target_profile_unreferenced_asset')
        self.assertEqual(report['assets'][0]['binding_status'], 'unbound')

    def test_invalid_codec_or_hash_rejected(self):
        for bad in (replace(sample(0), codec='unknown'), replace(sample(0), sha256='wrong')):
            with self.subTest(sample=bad):
                with self.assertRaises(ValueError):
                    dump_pcm_block_wavs(analysis((bad,), (playback(0, 0),)), self.out, 'CASE')


if __name__ == '__main__':
    unittest.main()
