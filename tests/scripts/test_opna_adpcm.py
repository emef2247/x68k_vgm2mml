"""Native Delta-T/target PCM IR boundaries; listening verification is separate."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))

from opna_adpcm import analyze, decode_adpcm_b, encode_msm6258, encode_msm6258_beam, project_msm6258, _msm_next
from pcm_mdx import RATES
from test_opna_opm import vgm


def source(*, prefix=b'', tail=b'', memory_mode=0xc1):
    encoded = bytes((0x70,)) + bytes(31)
    payload = struct.pack('<II', 32, 0) + encoded
    block = b'\x67\x66\x81' + struct.pack('<I', len(payload)) + payload
    writes = bytes((0x57, 1, memory_mode, 0x57, 9, 0, 0x57, 10, 0x20,
                    0x57, 11, 255, 0x57, 0, 0xa0))
    return vgm(block + prefix + writes + tail + b'\x61\x64\x00'), encoded


def _decode_msm6258(payload, count):
    signal, index = -2, 0
    result = []
    nibbles = []
    for byte in payload:
        nibbles.append(byte & 15)
        nibbles.append(byte >> 4)
    for tick in range(count):
        signal, index = _msm_next(signal, index, nibbles[tick])
        result.append(signal * 64)
    return result


class OpnaAdpcmTests(unittest.TestCase):
    def test_beam_encoder_contract_and_tone_suppression(self):
        import numpy as np
        self.assertEqual(encode_msm6258_beam([]), (b'', 0))
        ticks = np.arange(15625) / 15625
        source = 800. * np.sin(2 * np.pi * 440 * ticks)
        def band_share(decoded):
            window = 4096
            win = np.hanning(window)
            freqs = np.fft.rfftfreq(window, 1 / 15625)
            band = (freqs >= 7600) & (freqs <= 7812)
            total = share = 0.
            for start in range(0, len(decoded) - window, 2048):
                power = np.abs(np.fft.rfft(decoded[start:start + window] * win)) ** 2
                total += power.sum()
                share += power[band].sum()
            return 10 * np.log10(share / total)
        results = {}
        for name, encoder in (('greedy', encode_msm6258), ('beam', encode_msm6258_beam)):
            encoded, error = encoder([float(value) for value in source])
            self.assertEqual(len(encoded), (len(source) + 1) // 2)
            decoded = _decode_msm6258(encoded, len(source))
            replayed = sum((value - float(sample)) ** 2 for value, sample in zip(decoded, source))
            self.assertAlmostEqual(error, replayed, delta=replayed * 1e-9)
            snr = 10 * np.log10((source ** 2).mean() / ((np.asarray(decoded) - source) ** 2).mean())
            results[name] = (snr, band_share(np.asarray(decoded, dtype=np.float64)))
        # The beam encoder suppresses the near-Nyquist limit-cycle tone
        # of the greedy encoder on smooth low-level material, at a small
        # broadband SNR cost.
        self.assertLessEqual(results['beam'][1], results['greedy'][1] - 6)
        self.assertGreaterEqual(results['beam'][0], results['greedy'][0] - 3)

    def test_nominal_decoder_golden_high_nibble_first(self):
        # Manual decode: +15*127/8 ->238; next +303/8 ->275.
        self.assertEqual(decode_adpcm_b(b'\x70'), [238, 275])

    def test_native_memory_stays_distinct_from_transcoded_sample(self):
        raw, encoded = source()
        native = analyze(raw)
        self.assertEqual(native.samples[0].encoded_bytes, encoded)
        self.assertEqual(native.samples[0].sha256, hashlib.sha256(encoded).hexdigest())
        self.assertEqual(native.segments[0].termination, 'source_eof_without_reset')
        target = project_msm6258(native)
        self.assertTrue(target.playbacks[0].eligible)
        sample = target.samples[0]
        self.assertIn(sample.rate_num / sample.rate_den, [float(rate) for rate in RATES])
        self.assertNotEqual(sample.codec, native.samples[0].codec)
        self.assertNotEqual(sample.encoded_bytes, encoded)
        self.assertEqual(native.samples[0].encoded_bytes, encoded)

    def test_parameter_continuation_is_retained_and_ineligible(self):
        raw, _ = source(tail=bytes.fromhex('61 0a 00 57 0b 80'))
        native = analyze(raw)
        self.assertEqual(len(native.segments), 2)
        self.assertEqual(native.segments[0].playback_id, native.segments[1].playback_id)
        self.assertEqual(native.segments[1].continuation_index, 1)
        self.assertTrue(all(not s.independently_playable for s in native.segments))
        self.assertTrue(all(not p.eligible for p in project_msm6258(native).playbacks))

    def test_readonly_ram1_uses_four_byte_addresses_with_seed_assumption(self):
        raw, encoded = source(memory_mode=0xc0, prefix=bytes.fromhex(
            '57 02 01 57 04 02'))
        native = analyze(raw)
        sample, segment = native.samples[0], native.segments[0]
        self.assertEqual((sample.start_address, sample.end_address_exclusive), (4, 12))
        self.assertEqual(sample.encoded_bytes, encoded[4:12])
        self.assertEqual(segment.memory_mode, 'ram1')
        self.assertTrue(segment.independently_playable)
        observation = 'ram1_seeded_from_vgm_rom_block_assumption'
        self.assertIn(observation, segment.observations)
        target = project_msm6258(native)
        self.assertTrue(target.playbacks[0].eligible)
        self.assertIn(observation, target.playbacks[0].diagnostics)

    def test_ram1_still_rejects_record_and_cpu_playback(self):
        for control in (0xe0, 0x80):
            with self.subTest(control=control):
                raw, _ = source(memory_mode=0xc0)
                raw = raw.replace(bytes.fromhex('57 00 a0'), bytes((0x57, 0, control)))
                native = analyze(raw)
                self.assertFalse(native.segments[0].independently_playable)
                self.assertFalse(project_msm6258(native).playbacks[0].eligible)

    def test_prescaler_and_unresolved_ram_write_history_cannot_transcode(self):
        cases = [dict(tail=bytes.fromhex('56 2f 00')),
                 dict(prefix=bytes.fromhex('56 2e 00')),
                 dict(memory_mode=0xc2, prefix=bytes.fromhex(
                     '57 01 c2 57 00 60 57 08 11 57 08 00'))]
        for parameters in cases:
            with self.subTest(parameters=parameters):
                raw, _ = source(**parameters)
                native = analyze(raw)
                self.assertTrue(native.segments)
                self.assertTrue(all(not s.independently_playable for s in native.segments))
                self.assertTrue(all(not p.eligible for p in project_msm6258(native).playbacks))

    def test_unknown_memory_and_empty_manifest_do_not_claim_old_samples(self):
        native = analyze(vgm(bytes.fromhex('57 01 c1 57 0a 20 57 00 a0 62')))
        self.assertFalse(native.segments[0].independently_playable)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, _ = source()
            project_msm6258(analyze(raw)).dump(root, 'case')
            project_msm6258(analyze(vgm(b'\x62'))).dump(root, 'case')
            report = json.loads((root / 'case.msm6258_ir.analysis.json').read_text())
            self.assertEqual(report['samples'], [])
            self.assertFalse(any('sample' in name for name in report['current_files']))


if __name__ == '__main__':
    unittest.main()
