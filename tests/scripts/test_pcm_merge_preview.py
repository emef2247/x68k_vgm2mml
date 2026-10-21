"""Authored A/B listening diagnostics, ownership and event-gain checks."""
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
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
import test_pcm_bank_reduce as bank_fixture
from pcm_bank_reduce import _gain, reduce_bank
from pcm_merge_preview import MAX_HALF_SECONDS, _decode, dump_merge_previews


class PcmMergePreviewTests(unittest.TestCase):
    def original(self, count=2, **options):
        return bank_fixture.make_analysis(
            [bank_fixture.tone(amplitude=18000 // (2 ** index)) for index in range(count)], **options)

    def test_bounded_decoder_keeps_odd_nibble_prefix(self):
        payload = bytes((0x71, 0xa5, 0x3c, 0x49))
        self.assertEqual(_decode(payload, 5), _decode(payload)[:5])

    def test_checked_target_gate_extends_preview_beyond_source_gate(self):
        original = self.original(gates={0: 1000, 1: 1000})
        reduction = reduce_bank(original)
        events = tuple(dict(row, checked_gate_frames=1000) for row in reduction.playback_rows)
        reduction = replace(reduction, playback_rows=events)
        with tempfile.TemporaryDirectory() as temp:
            result = dump_merge_previews(original, reduction, temp, 'A')
            row = result['pairs'][0]
            self.assertEqual(row['gate_frames'], 1000)
            self.assertLess(row['source_gate_frames'], 1000)
            self.assertEqual(row['gate_frame_origin'], 'checked_target_gate')
            self.assertAlmostEqual(row['target_gate_seconds'], 1000 / bank_fixture.RATE)
            self.assertAlmostEqual(row['source_gate_seconds'], 1000 / 44100)
            with wave.open(str(Path(result['directory']) / row['file'])) as wav:
                values = struct.unpack('<' + 'h' * wav.getnframes(), wav.readframes(wav.getnframes()))
            # The portion after the source gate must be actual decoded tail,
            # rather than shortening the evidence to the pre-projection gate.
            expected = [round(v * _gain(row['original_volume']))
                        for v in _decode(original.samples[row['original_sample_id']].encoded_bytes)[
                            row['source_gate_frames']:1000]]
            self.assertEqual(list(values[row['source_gate_frames']:1000]), expected)
            self.assertTrue(any(expected))

    def test_invalid_checked_target_gate_is_rejected(self):
        original = self.original()
        reduction = reduce_bank(original)
        for invalid in (-1, 3.5, True, None):
            events = tuple(dict(row, checked_gate_frames=invalid) for row in reduction.playback_rows)
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(ValueError, 'checked gate frames'):
                    dump_merge_previews(original, replace(reduction, playback_rows=events), temp, 'A')

    def test_original_then_representative_with_composed_quantized_gain(self):
        original = self.original(volumes={1: 137})
        reduction = reduce_bank(original)
        before = tuple(s.encoded_bytes for s in original.samples)
        event = reduction.playback_rows[1]
        plan = SimpleNamespace(rows=[dict(playback_id=1, sample_id=event['target_sample_id'],
                                         target_volume=event['target_volume'])])
        with tempfile.TemporaryDirectory() as temp:
            result = dump_merge_previews(original, reduction, temp, 'A', plan=plan)
            self.assertEqual(result['wav_count'], 1)
            row = result['pairs'][0]
            self.assertEqual(row['projection_status'], 'retained')
            self.assertEqual(row['original_volume'], 137)
            self.assertEqual(row['target_volume'], event['target_volume'])
            with wave.open(str(Path(result['directory']) / row['file'])) as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), bank_fixture.RATE)
                values = struct.unpack('<' + 'h' * wav.getnframes(), wav.readframes(wav.getnframes()))
            n, gap = row['half_frames'], row['gap_frames']
            a, b = _decode(original.samples[1].encoded_bytes), _decode(original.samples[0].encoded_bytes)
            expected_a = [round(v * _gain(137)) for v in a]
            expected_b = [round(v * _gain(event['target_volume'])) for v in b]
            self.assertEqual(list(values[:len(a)]), expected_a)
            self.assertEqual(values[len(a):n], (0,) * (n - len(a)))
            self.assertEqual(values[n:n + gap], (0,) * gap)
            self.assertEqual(list(values[n + gap:n + gap + len(b)]), expected_b)
            manifest = json.loads(Path(result['manifest_path']).read_text())
            for name, digest in manifest['owned_files'].items():
                self.assertEqual(hashlib.sha256((Path(result['directory']) / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(before, tuple(s.encoded_bytes for s in original.samples))
        self.assertEqual(original.playbacks[1].sample_id, 1)

    def test_plan_missing_and_omitted_do_not_claim_retained(self):
        original = self.original()
        reduction = reduce_bank(original)
        with tempfile.TemporaryDirectory() as temp:
            unknown = dump_merge_previews(original, reduction, temp, 'A')
            self.assertEqual(unknown['pairs'][0]['projection_status'], 'not_projected')
            omitted = dump_merge_previews(original, reduction, temp, 'A', plan=SimpleNamespace(rows=[]))
            self.assertEqual(omitted['pairs'][0]['projection_status'], 'omitted')

    def test_modified_output_prevents_any_replacement(self):
        original = self.original()
        reduction = reduce_bank(original)
        with tempfile.TemporaryDirectory() as temp:
            result = dump_merge_previews(original, reduction, temp, 'A')
            manifest_before = Path(result['manifest_path']).read_bytes()
            path = Path(result['directory']) / result['pairs'][0]['file']
            path.write_bytes(b'user replacement')
            with self.assertRaisesRegex(ValueError, 'modified or unowned'):
                dump_merge_previews(original, reduction, temp, 'A')
            self.assertEqual(path.read_bytes(), b'user replacement')
            self.assertEqual(Path(result['manifest_path']).read_bytes(), manifest_before)

    def test_unowned_file_is_not_overwritten(self):
        original = self.original()
        reduction = reduce_bank(original)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / '_diagnostics' / 'A' / 'pcm_merge'
            root.mkdir(parents=True)
            (root / 'A.pairs.csv').write_text('user data')
            with self.assertRaisesRegex(ValueError, 'modified or unowned'):
                dump_merge_previews(original, reduction, temp, 'A')
            self.assertEqual((root / 'A.pairs.csv').read_text(), 'user data')

    def test_pair_limit_and_empty_result_remove_only_owned_stale_wavs(self):
        original = self.original(count=3)
        reduction = reduce_bank(original)
        self.assertEqual(reduction.summary['merged_sample_count'], 2)
        with tempfile.TemporaryDirectory() as temp:
            result = dump_merge_previews(original, reduction, temp, 'A', max_pairs=1)
            self.assertEqual(result['candidate_pair_count'], 2)
            self.assertEqual(result['omitted_preview_count'], 1)
            folder = Path(result['directory'])
            previous = folder / result['pairs'][0]['file']
            unrelated = folder / 'manual.wav'
            unrelated.write_bytes(b'user')
            empty = dump_merge_previews(original, reduce_bank(original, mode='off'), temp, 'A')
            self.assertEqual(empty['wav_count'], 0)
            self.assertFalse(previous.exists())
            self.assertEqual(unrelated.read_bytes(), b'user')

    def test_exact_rate_gate_padding_and_wav_rounding_are_reported(self):
        rate = Fraction(125000, 3)
        original = self.original(rates={0: rate, 1: rate}, gates={0: 4410, 1: 4410})
        reduction = reduce_bank(original)
        with tempfile.TemporaryDirectory() as temp:
            row = dump_merge_previews(original, reduction, temp, 'A')['pairs'][0]
            self.assertEqual((row['rate_num'], row['rate_den']), (125000, 3))
            self.assertEqual(row['wav_rate_hz'], 41667)
            self.assertEqual(row['gate_frames'], 4167)
            self.assertAlmostEqual(row['wav_rate_error_hz'], 1 / 3)
            self.assertFalse(row['clipped_to_preview_duration'])
            self.assertEqual(row['half_frames'], 4167)

    def test_long_gate_has_explicit_duration_cap(self):
        original = self.original(gates={0: 20 * 44100, 1: 20 * 44100})
        reduction = reduce_bank(original)
        with tempfile.TemporaryDirectory() as temp:
            row = dump_merge_previews(original, reduction, temp, 'A')['pairs'][0]
            self.assertTrue(row['clipped_to_preview_duration'])
            self.assertEqual(row['half_frames'], MAX_HALF_SECONDS * bank_fixture.RATE)
            self.assertEqual(row['gate_frames'], 20 * bank_fixture.RATE)

    def test_disagreeing_final_mapping_is_rejected(self):
        original = self.original()
        reduction = reduce_bank(original)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'disagrees'):
                dump_merge_previews(original, reduction, temp, 'A', plan=SimpleNamespace(
                    rows=[dict(playback_id=1, sample_id=1, target_volume=128)]))


if __name__ == '__main__':
    unittest.main()
