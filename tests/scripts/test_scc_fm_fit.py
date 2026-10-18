import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from scc_fm_fit import CARRIERS, OpmProbe, fit_bank, read_waveforms, wave_bytes, pitch_check


class SccFmFitTests(unittest.TestCase):
    def test_waveform_identity_and_validation(self):
        raw = bytes(range(32))
        self.assertEqual(wave_bytes(raw.hex()), raw)
        self.assertEqual(wave_bytes([*range(16), *range(-16, 0)]), bytes([*range(16), *range(240, 256)]))
        with self.assertRaises(ValueError):
            wave_bytes('00')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'waves.json'
            path.write_text(json.dumps([list(raw), list(raw)]))
            self.assertEqual(read_waveforms(path), [raw])
        self.assertEqual(CARRIERS[4], [2, 3])
        for invalid in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                OpmProbe(ROOT, frequency=invalid)

    def test_authored_wave_actual_core_and_cache(self):
        try:
            probe = OpmProbe(ROOT)
        except RuntimeError as exc:
            if any(text in str(exc) for text in ('Missing external', 'requires NumPy', 'requires GCC')):
                self.skipTest(str(exc))
            else:
                raise
        import math
        raw = bytes(round(100 * math.sin(2 * math.pi * n / 32)) % 256 for n in range(32))
        with tempfile.TemporaryDirectory() as directory:
            bank = fit_bank([raw], probe, cache_dir=directory)
            again = fit_bank([raw], probe, cache_dir=directory)
            self.assertEqual(bank, again)
        identity = hashlib.sha256(raw).hexdigest()
        entry = bank['waveforms'][identity]
        self.assertEqual(bank['schema'], 'scc-fm-fit-v1')
        self.assertEqual(len(entry['candidates']), 5)
        self.assertLess(entry['candidates']['additive']['spectral_error'], .04)
        spec = probe.spectrum(probe.reference(raw, .125))
        checks = [OpmProbe(ROOT, frequency=f) for f in (220, 440, 880)]
        for name, candidate in entry['candidates'].items():
            self.assertAlmostEqual(candidate['spectral_error'], probe.error(spec, probe.render(candidate['parts'])))
            self.assertEqual(len(candidate['pitch_checks']), 3)
            self.assertFalse(candidate['pitch_checks'][0]['reoptimized'])
            for record, check_probe in zip(candidate['pitch_checks'], checks):
                self.assertEqual(record, pitch_check(raw, candidate['parts'], check_probe, .125))
            self.assertLessEqual(len(candidate['parts']), 2)
            for part in candidate['parts']:
                self.assertEqual(part['carriers'], CARRIERS[part['algorithm']])
                self.assertTrue(all(0 <= tl <= 127 for tl in part['operator_tl']))


if __name__ == '__main__':
    unittest.main()
