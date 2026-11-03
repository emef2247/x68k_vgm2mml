"""DCSG (SN76489) segment rendering and MSM6258 bridge checks (S4)."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests' / 'scripts')]
from dcsg import analyze
from opn2_dcsg_pcm import project_dcsg, render_dcsg_wave


def vgm(commands, *, clock=4000000, flags=5):
    raw = bytearray(0x100)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 12, clock)
    struct.pack_into('<HBB', raw, 0x28, 3, 15, flags)
    struct.pack_into('<I', raw, 0x34, 0x100 - 0x34)
    raw.extend(commands + b'\x66')
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


def write(value):
    return bytes((0x50, value))


def tone(ch, period):
    return write(0x80 | ch << 5 | period & 15) + write(period >> 4)


def level(ch, attenuation=0):
    return write(0x90 | ch << 5 | attenuation)


def noise(control=4):
    return write(0xe0 | control)


def wait(samples):
    return b'\x61' + struct.pack('<H', samples)


class DcsgRenderTests(unittest.TestCase):
    def test_tone_renders_square_at_segment_frequency(self):
        raw = vgm(tone(0, 250) + level(0, 0) + wait(44100))
        analysis = analyze(raw)
        wave, stats = render_dcsg_wave(analysis, analysis.end_sample)
        self.assertEqual(stats['audible_samples'], 44100)
        middle = wave[11025:33075]
        self.assertEqual(max(middle), 24576)
        self.assertEqual(min(middle), -24576)
        crossings = sum(1 for a, b in zip(middle, middle[1:]) if (a < 0) != (b < 0))
        self.assertAlmostEqual(crossings / 2 / 0.5, 500.0, delta=10.0)

    def test_attenuation_law_and_silence(self):
        raw = vgm(tone(0, 250) + level(0, 5) + wait(4410)
                  + level(0, 15) + wait(4410))
        analysis = analyze(raw)
        wave, _stats = render_dcsg_wave(analysis, analysis.end_sample)
        self.assertEqual(max(wave[:4410]), round(24576 * 10 ** -0.5))
        self.assertTrue(all(v == 0 for v in wave[4410:]))

    def test_noise_is_deterministic_and_sounds(self):
        raw = vgm(noise(4) + level(3, 0) + wait(44100))
        analysis = analyze(raw)
        wave, stats = render_dcsg_wave(analysis, analysis.end_sample)
        again, _ = render_dcsg_wave(analysis, analysis.end_sample)
        self.assertEqual(wave, again)
        self.assertGreater(stats['audible_samples'], 0)
        self.assertTrue(any(v != 0 for v in wave))
        changes = sum(1 for a, b in zip(wave, wave[1:]) if (a < 0) != (b < 0))
        self.assertGreater(changes, 100)

    def test_project_splits_at_silence_and_dedupes(self):
        phrase = tone(0, 250) + level(0, 0) + wait(4410)
        gap = level(0, 15) + wait(4410)
        raw = vgm(phrase + gap + phrase + level(0, 15) + wait(100))
        analysis = analyze(raw)
        bridge = project_dcsg(raw, analysis, source_end=analysis.end_sample)
        self.assertEqual(bridge.dcsg_stats['playbacks'], 2)
        self.assertEqual(bridge.dcsg_stats['unique_samples'], 1)
        self.assertEqual(len(bridge.playbacks), 2)
        self.assertLess(bridge.playbacks[0].start_vgmticks,
                        bridge.playbacks[1].start_vgmticks)

    def test_silent_dcsg_yields_no_playbacks(self):
        raw = vgm(tone(0, 250) + level(0, 15) + wait(4410))
        analysis = analyze(raw)
        bridge = project_dcsg(raw, analysis, source_end=analysis.end_sample)
        self.assertEqual(bridge.playbacks, ())
        self.assertEqual(bridge.dcsg_stats['playbacks'], 0)


if __name__ == '__main__':
    unittest.main()
