"""Authored target bank sharing checks; no private material or listening."""
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))

import numpy as np

from msm6258 import PcmAnalysis, PcmPlayback, PcmSample, TransferLog
from opna_adpcm import encode_msm6258
from pcm_bank_reduce import POLICY, _gain, reduce_bank
from segapcm_bank import BankAnalysis, BankPlayback


RATE = 15625


def tone(*, frequency=300, amplitude=18000, length=2048, decay=5, attack=0):
    time = np.arange(length) / RATE
    envelope = np.exp(-decay * np.arange(length) / length)
    if attack:
        envelope[:attack] *= np.linspace(0, 1, attack)
    return np.rint(amplitude * np.sin(2 * np.pi * frequency * time) * envelope).astype(int)


def make_analysis(waves, *, rates=None, volumes=None, gates=None, parallel=True):
    samples, playbacks, waveforms = [], [], []
    for sid, audio in enumerate(waves):
        data, _ = encode_msm6258(audio)
        samples.append(PcmSample(sid, 'msm6258-adpcm4-low-first', data,
                                 hashlib.sha256(data).hexdigest()))
        rate = Fraction((rates or {}).get(sid, RATE))
        start = sid * 20000
        stop = start + (gates or {}).get(sid, math_ceil(len(audio) * 44100 / float(rate)))
        values = dict(playback_id=sid, chip_instance=0, sample_id=sid,
            start_vgmticks=start, end_vgmticks=stop, first_source_event_id=10 + sid,
            last_source_event_id=20 + sid, transfer_start=0, transfer_end=0,
            supplied_bytes=0, clock_hz=8000000, divider=512,
            rate_num=rate.numerator, rate_den=rate.denominator, pan=sid % 3,
            reset_observed=False, decoder_reset_known=True,
            reset_origin='authored', termination='natural_stop',
            delivery_cadence_compatible=True, independently_playable=True,
            nominal_nibbles=len(audio), consumed_nibbles=None, issues=(),
            control_event_ids=(), stream_transfer_start=3, stream_transfer_end=4,
            delivery_max_error_vgmticks=0.25, unfed_tail_vgmticks=0.0)
        if parallel:
            playbacks.append(BankPlayback(**values, source_channel=sid % 16,
                target_volume=(volumes or {}).get(sid, 128)))
        else:
            playbacks.append(PcmPlayback(**values))
        waveforms.append(dict(sample_id=sid, samples=audio, rate_num=rate.numerator,
                              rate_den=rate.denominator))
    values = dict(source_end_vgmticks=max((p.end_vgmticks for p in playbacks), default=0),
        samples=tuple(samples), playbacks=tuple(playbacks), controls=(), issues=(),
        transfers=TransferLog(b''), raw_commands=(), source_raw=b'', clock_hz=8000000,
        options=4, initialization='authored', source_loop_vgmticks=None, blocks=())
    return BankAnalysis(**values, bank_waveforms=tuple(waveforms)) if parallel else PcmAnalysis(**values)


def math_ceil(value):
    import math
    return math.ceil(value)


def noise_drum(seed, amplitude=5000, decay=3, spectral_tilt=0):
    # Two independent phase sets have the same broad-band cycle spectrum.
    # This intentionally tests perceptual/timbre approximation rather than
    # pretending that their time-domain samples match.
    phase = np.random.default_rng(seed).uniform(-np.pi, np.pi, 65)
    spectrum = np.exp(1j * phase) * np.linspace(1, 0.01, 65) ** spectral_tilt
    spectrum[0] = spectrum[-1] = 0
    cycle = np.fft.irfft(spectrum, 128)
    cycle /= np.sqrt(np.mean(cycle ** 2))
    length = 8192
    return np.rint(np.tile(cycle, 64) * amplitude *
                   np.exp(-decay * np.arange(length) / length)).astype(int)


class PcmBankReductionTests(unittest.TestCase):
    def test_scaled_drum_shares_stronger_existing_asset_and_composes_gain_once(self):
        audio = tone()
        original = make_analysis([audio, np.rint(audio / 2).astype(int)], volumes={1: 137})
        result = reduce_bank(original)
        self.assertEqual(result.summary['output_sample_count'], 1)
        self.assertEqual(result.analysis.samples[0], original.samples[0])
        self.assertEqual(result.analysis.playbacks[1].sample_id, 0)
        self.assertAlmostEqual(_gain(result.analysis.playbacks[1].target_volume), 0.25)
        self.assertEqual(original.playbacks[1].sample_id, 1)
        self.assertEqual(original.playbacks[1].target_volume, 137)
        self.assertEqual(len(original.samples), 2)
        self.assertTrue(result.analysis.target_evidence)

    def test_every_original_event_field_is_retained(self):
        original = make_analysis([tone(), tone(amplitude=9000)])
        result = reduce_bank(original)
        p, q = original.playbacks[1], result.analysis.playbacks[1]
        for name in PcmPlayback.__dataclass_fields__:
            if name not in ('sample_id', 'nominal_nibbles'):
                self.assertEqual(getattr(p, name), getattr(q, name), name)
        self.assertEqual(q.source_channel, p.source_channel)
        self.assertEqual(q.original_sample_id, p.sample_id)
        self.assertEqual(q.original_target_volume, p.target_volume)
        self.assertFalse(result.summary['playback_timing_modified'])
        self.assertFalse(hasattr(result.analysis, 'align_to_clock'))

    def test_serial_plain_analysis_is_supported_without_new_clock_alignment(self):
        original = make_analysis([tone(), tone(amplitude=9000)], parallel=False)
        result = reduce_bank(original)
        self.assertEqual(len(result.analysis.samples), 1)
        self.assertEqual(len(result.analysis.playbacks), 2)
        self.assertTrue(hasattr(result.analysis.playbacks[1], 'target_volume'))

    def test_mode_off_retains_samples_and_reports_identity_rows(self):
        original = make_analysis([tone(), tone(amplitude=9000)])
        result = reduce_bank(original, mode='off')
        self.assertEqual(result.analysis.samples, original.samples)
        self.assertEqual([r['target_sample_id'] for r in result.sample_rows], [0, 1])
        self.assertEqual(result.summary['merged_playback_count'], 0)
        self.assertEqual(result.sample_rows[0]['reason'], 'disabled')

    def test_different_envelopes_are_not_loudness_variants(self):
        result = reduce_bank(make_analysis([tone(decay=1), tone(decay=12)]))
        self.assertEqual(len(result.analysis.samples), 2)

    def test_large_onset_delay_does_not_get_erased_by_alignment(self):
        audio = tone()
        delayed = np.concatenate([np.zeros(100, dtype=int), audio[:-100]])
        result = reduce_bank(make_analysis([audio, delayed]))
        self.assertEqual(len(result.analysis.samples), 2)

    def test_representative_tail_is_checked_beyond_common_prefix(self):
        audio = tone(decay=0)
        shorter = audio.copy()
        shorter[-180:] = 0
        result = reduce_bank(make_analysis([audio, shorter]))
        self.assertEqual(len(result.analysis.samples), 2)

    def test_finite_tail_outside_short_gate_can_share(self):
        audio = tone(decay=0)
        later_changed = audio.copy()
        later_changed[-180:] = 0
        result = reduce_bank(make_analysis([audio, later_changed], gates={0: 3000, 1: 3000}))
        self.assertEqual(len(result.analysis.samples), 1)

    def test_mixed_target_rates_do_not_share_by_changing_F(self):
        result = reduce_bank(make_analysis([tone(), tone(amplitude=9000)], rates={1: Fraction(RATE, 2)}))
        self.assertEqual(len(result.analysis.samples), 2)
        self.assertEqual(result.analysis.playbacks[1].rate_hz, Fraction(RATE, 2))

    def test_different_tonal_pitch_over_one_semitone_is_rejected(self):
        result = reduce_bank(make_analysis([tone(frequency=300), tone(frequency=340)]))
        self.assertEqual(len(result.analysis.samples), 2)

    def test_small_detune_keeps_actual_F_and_event_timing(self):
        original = make_analysis([tone(frequency=300, decay=2),
                                  tone(frequency=305, amplitude=14000, decay=2)])
        result = reduce_bank(original)
        self.assertEqual(len(result.analysis.samples), 1)
        self.assertEqual(result.analysis.playbacks[1].rate_hz, RATE)
        self.assertEqual(result.analysis.playbacks[1].start_vgmticks,
                         original.playbacks[1].start_vgmticks)
        row = result.sample_rows[1]
        self.assertEqual(row['pitch_status'], 'estimated_tonal')
        self.assertLessEqual(abs(row['measured_pitch_cents']), POLICY['max_pitch_cents'])

    def test_groups_are_not_transitive_over_pitch_tolerance(self):
        # Every pair is judged against the actual representative, and the
        # group's endpoints cannot chain beyond one semitone via its middle.
        frequencies = [300, 310, 320]
        original = make_analysis([tone(frequency=f, amplitude=a, decay=2)
                                  for f, a in zip(frequencies, [16000, 18000, 14000])])
        result = reduce_bank(original)
        self.assertGreaterEqual(len(result.analysis.samples), 2)
        groups = {}
        for row in result.sample_rows:
            groups.setdefault(row['target_sample_id'], []).append(frequencies[row['original_sample_id']])
        import math
        for values in groups.values():
            self.assertLessEqual(1200 * math.log2(max(values) / min(values)), 101)

    def test_short_noise_drum_can_share_by_actual_temporal_spectrum(self):
        original = make_analysis([noise_drum(1), noise_drum(2, amplitude=4000)])
        result = reduce_bank(original)
        self.assertEqual(len(result.analysis.samples), 1)
        row = result.sample_rows[1]
        self.assertEqual(row['similarity_method'], 'spectral_envelope')
        self.assertEqual(row['pitch_status'], 'unknown_noise_or_complex')
        self.assertIsNone(row['measured_pitch_cents'])
        self.assertGreater(row['waveform_error'], 1)
        self.assertLess(row['temporal_spectral_error'], POLICY['temporal_spectral_error'])

    def test_noise_drum_with_different_envelope_or_timbre_stays_distinct(self):
        original = make_analysis([noise_drum(1), noise_drum(2, amplitude=4000, decay=10),
                                  noise_drum(2, amplitude=4000, spectral_tilt=2)])
        result = reduce_bank(original)
        self.assertEqual(len(result.analysis.samples), 3)

    def test_unique_source_family_rate_overrides_misleading_decoded_pitch(self):
        original = make_analysis([tone(), tone(amplitude=9000)])
        identities = []
        for sid, delta in enumerate((128, 256)):
            identities.append(dict(sample_id=sid, identity_json=json.dumps(dict(
                source_bytes_sha256='authored_same_rom_material', address_fixed=0,
                end_address_fixed=4096, delta=delta, source_rate='31250'))))
        original = replace(original, bank_assets=tuple(identities))
        result = reduce_bank(original)
        self.assertEqual(len(result.analysis.samples), 2)
        self.assertGreater(result.summary['rejection_counts'].get('pitch', 0), 0)

    def test_unique_source_rate_family_is_recorded_when_merged(self):
        original = make_analysis([tone(), tone(amplitude=9000)])
        assets = tuple(dict(sample_id=sid, source_bytes_sha256='authored_same_rom',
            address_fixed=0, end_address_fixed=4096, delta=128,
            source_rate_num=31250, source_rate_den=1) for sid in range(2))
        result = reduce_bank(replace(original, bank_assets=assets))
        self.assertEqual(result.sample_rows[1]['pitch_status'], 'known_source_rate')
        self.assertAlmostEqual(result.sample_rows[1]['measured_pitch_cents'], 0)

    def test_tiny_gain_cannot_be_approximated_by_nonzero_minimum_volume(self):
        original = make_analysis([tone(amplitude=30000, decay=0), tone(amplitude=350, decay=0)])
        result = reduce_bank(original)
        self.assertEqual(len(result.analysis.samples), 2)
        self.assertGreater(result.summary['rejection_counts'].get('gain_quantization', 0), 0)

    def test_all_playbacks_must_pass_their_own_quantized_gain(self):
        original = make_analysis([tone(), tone(amplitude=9000)])
        # One ordinary playback is feasible; the same sample's very quiet
        # second occurrence cannot be represented below PCM8's minimum gain.
        extra = replace(original.playbacks[1], playback_id=2, start_vgmticks=50000,
                        end_vgmticks=60000, target_volume=168)
        original = replace(original, playbacks=(*original.playbacks, extra))
        result = reduce_bank(original)
        self.assertEqual(len(result.analysis.samples), 2)
        self.assertEqual(result.analysis.playbacks[1].sample_id, 1)
        self.assertEqual(result.analysis.playbacks[2].sample_id, 1)
        self.assertGreater(result.summary['rejection_counts'].get('gain_quantization', 0), 0)

    def test_clipped_target_is_not_amplified_or_reencoded(self):
        clipped = np.clip(tone(amplitude=60000, decay=0), -32768, 32767)
        original = make_analysis([clipped, tone(amplitude=15000, decay=0)])
        result = reduce_bank(original)
        for asset in result.analysis.samples:
            self.assertEqual(asset.encoded_bytes, original.samples[asset.sample_id].encoded_bytes)
        self.assertTrue(all(0 <= _gain(p.target_volume) <= 1 for p in result.analysis.playbacks))

    def test_off_does_not_import_numpy(self):
        original = make_analysis([tone(), tone(amplitude=9000)])
        from unittest.mock import patch
        import builtins
        original_import = builtins.__import__
        def reject_numpy(name, *args, **kwargs):
            if name == 'numpy':
                raise AssertionError('off must not need numpy')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=reject_numpy):
            result = reduce_bank(original, mode='off')
        self.assertEqual(result.summary['merged_playback_count'], 0)

    def test_long_phrase_needs_actual_unshifted_waveform_match(self):
        length = 20000
        audio = tone(length=length, decay=0)
        other = tone(length=length, frequency=301, decay=0)
        result = reduce_bank(make_analysis([audio, other]))
        self.assertEqual(len(result.analysis.samples), 2)

    def test_exact_repeated_long_phrase_is_shared(self):
        audio = tone(length=16000, decay=1)
        result = reduce_bank(make_analysis([audio, audio.copy()]))
        self.assertEqual(len(result.analysis.samples), 1)
        self.assertEqual(result.analysis.samples[0].encoded_bytes,
                         result.analysis.samples[0].encoded_bytes)

    def test_quiet_zero_and_silent_volume_are_not_invented_attacks(self):
        result = reduce_bank(make_analysis([np.zeros(128, dtype=int), np.zeros(128, dtype=int)]))
        self.assertEqual(len(result.analysis.samples), 2)
        original = make_analysis([tone(), tone(amplitude=9000)], volumes={1: 192})
        result = reduce_bank(original)
        self.assertEqual(len(result.analysis.samples), 2)
        self.assertEqual(result.analysis.playbacks[1].target_volume, 192)

    def test_capacity_policy_does_not_blindly_truncate_97_candidates(self):
        # Exact same authored material exercises reduction before the 96-slot
        # capacity decision. A distinct final instrument must still survive.
        audio = tone(length=256)
        waves = [audio] * 96 + [tone(length=256, frequency=1100)]
        result = reduce_bank(make_analysis(waves))
        self.assertEqual(len(result.analysis.samples), 2)
        self.assertEqual(result.analysis.playbacks[-1].sample_id, 96)
        self.assertEqual(len(result.analysis.playbacks), 97)
        self.assertIsNone(result.summary['recovered_playback_count'])

    def test_explicit_omission_does_not_make_gain_claim_or_drop_evidence(self):
        original = make_analysis([tone(), tone(amplitude=9000)], gates={1: 200})
        result = reduce_bank(original, omit_playback_ids=(1,))
        self.assertEqual(result.analysis.playbacks[1].sample_id, 1)
        self.assertTrue(result.playback_rows[1]['explicit_omission'])
        self.assertEqual(result.summary['merged_playback_count'], 0)

    def test_long_requested_omission_still_validates_and_merges_ordinary_playback(self):
        original = make_analysis([tone(), tone(amplitude=9000)])
        result = reduce_bank(original, omit_playback_ids=(1,))
        self.assertFalse(result.playback_rows[1]['explicit_omission'])
        self.assertEqual(result.analysis.playbacks[1].sample_id, 0)
        self.assertEqual(result.summary['merged_playback_count'], 1)

    def test_actual_projected_gate_reveals_tail_hidden_by_source_gate(self):
        audio = tone(decay=0)
        different_tail = audio.copy()
        different_tail[-180:] = 0
        original = make_analysis([audio, different_tail], gates={0: 3000, 1: 3000})
        source = reduce_bank(original)
        self.assertEqual(len(source.analysis.samples), 1)
        # An intentionally expanded custom clock exposes the otherwise gated
        # tail. Its real duration must govern acceptance, not source timestamps.
        projected = reduce_bank(original, tick_mapper=lambda t: t * 2, sample_multiplier=1)
        self.assertEqual(len(projected.analysis.samples), 2)
        self.assertEqual(projected.summary['gate_duration_basis'], 'projected_mdx_clock')
        self.assertGreater(projected.playback_rows[0]['checked_gate_frames'], len(audio))
        self.assertEqual(projected.analysis.playbacks[0].start_vgmticks,
                         original.playbacks[0].start_vgmticks)

    def test_default_mdx_mapper_has_same_gate_frame_calculation(self):
        from opm_mdx import mdx_tick
        original = make_analysis([tone(), tone(amplitude=9000)])
        result = reduce_bank(original, sample_multiplier=3)
        p = original.playbacks[1]
        ticks = mdx_tick(p.end_vgmticks, 3) - mdx_tick(p.start_vgmticks, 3)
        expected = math_ceil(Fraction(ticks * 3 * 256, 1000000) * p.rate_hz)
        self.assertEqual(result.playback_rows[1]['checked_gate_frames'], expected)

    def test_invalid_input_is_not_hidden_by_mode_off_or_removal(self):
        original = make_analysis([tone(), tone()])
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            reduce_bank(replace(original, samples=(replace(original.samples[0], sha256='bad'),
                                                   original.samples[1])), mode='off')
        with self.assertRaisesRegex(ValueError, 'unknown playback sample'):
            reduce_bank(replace(original, playbacks=(replace(original.playbacks[0], sample_id=999),)))
        with self.assertRaisesRegex(ValueError, 'positive playback rates'):
            reduce_bank(replace(original, playbacks=(replace(original.playbacks[0], rate_num=0),)))

    def test_diagnostics_have_identity_and_merge_rows_and_mutable_final_summary(self):
        result = reduce_bank(make_analysis([tone(), tone(amplitude=9000)]))
        result.summary['recovered_playback_count'] = 1
        with tempfile.TemporaryDirectory() as temp:
            path = result.dump(temp, 'AUTH')
            report = json.loads(path.read_text())
            self.assertEqual(report['summary']['recovered_playback_count'], 1)
            csv = (Path(temp) / 'AUTH.pcm_bank_merge.samples.csv').read_text()
            self.assertIn('similar_existing_representative', csv)
            self.assertIn('original_sample_id', csv)
        self.assertEqual(len(result.sample_rows), 2)
        self.assertEqual(len(result.playback_rows), 2)


if __name__ == '__main__':
    unittest.main()
