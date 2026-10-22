"""Code-profile onset gain checks, independent of native listening validation."""
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from pcm8_volume import MXDRV_PCM_LEVELS, PCM8_GAINS, project_pcm8_volume


class Pcm8VolumeTests(unittest.TestCase):
    def test_full_and_half_gain_are_not_muted_at_the_driver(self):
        full, half = project_pcm8_volume(128), project_pcm8_volume(64)
        self.assertEqual((full.raw_volume, full.pcm8_level, full.effective_gain), (128, 15, 1.0))
        self.assertEqual((half.raw_volume, half.pcm8_level, half.effective_gain), (137, 12, 0.5))
        for result in (full, half):
            self.assertLess(result.raw_volume & 127, 43)
            self.assertEqual(MXDRV_PCM_LEVELS[result.raw_volume & 127], result.pcm8_level)
        # The previous raw192 byte becomes attenuation64, above the driver's mute threshold.
        self.assertGreaterEqual(192 & 127, 43)

    def test_all_reference_gains_round_trip_through_both_tables(self):
        for index, gain in enumerate(PCM8_GAINS):
            with self.subTest(index=index):
                result = project_pcm8_volume(gain, source_scale=80)
                self.assertEqual(result.pcm8_level, index)
                self.assertEqual(PCM8_GAINS[MXDRV_PCM_LEVELS[result.raw_volume & 127]], gain)
                self.assertEqual(result.gain_error, 0.0)

    def test_true_silence_does_not_select_nonzero_minimum(self):
        result = project_pcm8_volume(0)
        self.assertTrue(result.silent)
        self.assertIsNone(result.raw_volume)
        self.assertIsNone(result.pcm8_level)
        self.assertEqual(result.effective_gain, 0.0)
        next_attack = project_pcm8_volume(128)
        self.assertFalse(next_attack.silent)
        self.assertEqual(next_attack.raw_volume, 128)

    def test_low_positive_level_reports_nonzero_floor(self):
        result = project_pcm8_volume(Fraction(1, 128))
        self.assertFalse(result.silent)
        self.assertEqual(result.pcm8_level, 0)
        self.assertEqual(result.effective_gain, 2 / 80)
        self.assertAlmostEqual(result.gain_error, result.effective_gain - result.desired_gain)
        self.assertEqual(result.absolute_gain_error, abs(result.gain_error))

    def test_tie_selects_quieter_gain_and_is_monotonic(self):
        self.assertEqual(project_pcm8_volume(Fraction(72, 80), source_scale=1).pcm8_level, 14)
        values = [project_pcm8_volume(i).effective_gain for i in range(129)]
        self.assertEqual(values, sorted(values))

    def test_shared_scale_and_report_do_not_normalize_each_playback(self):
        result = asdict(project_pcm8_volume(32))
        self.assertEqual(result['source_scale'], 128.0)
        self.assertEqual(result['desired_gain'], 0.25)
        self.assertEqual(result['effective_gain'], 0.25)
        self.assertEqual(result['compatibility_profile'], 'mxdrv206_17_x5s_x68sound_pcm8')

    def test_invalid_values_are_rejected_without_clipping(self):
        for level, scale in ((-1, 128), (129, 128), (0, 0), (1, -1),
                             (float('nan'), 128), (1, float('inf')), (float('inf'), 128)):
            with self.subTest(level=level, scale=scale):
                with self.assertRaises(ValueError):
                    project_pcm8_volume(level, source_scale=scale)


if __name__ == '__main__':
    unittest.main()
