"""Source selection and shared PCM target integration for MSM6295."""
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
from conversion_config import inspect_source, select_mdx_route
from vgm_io import read_vgm_header
from opm_conversion import convert
from pcm_assessment import ProjectionError
from pcm_mdx import default_generator
from pcm_bank_stats import summarize
from generate_msm6295_public_fixtures import cases, make_vgm, start, wait, write


class Msm6295ConversionTests(unittest.TestCase):
    def test_route_uses_commands_and_empty_rom_is_inactive(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'AUTH.vgm'
            for name, raw, facts in cases():
                with self.subTest(name=name):
                    source.write_bytes(raw)
                    usage = inspect_source(source)
                    self.assertFalse(usage['unsupported_commands'])
                    self.assertEqual(read_vgm_header(raw)['msm6295_clock_raw'], 0x800f4240)
                    expected = 'opm-msm6295-source' if facts['expected_playbacks'] else 'native-opm-pcm'
                    self.assertEqual(select_mdx_route(usage), expected)
                    if not facts['expected_playbacks']:
                        self.assertIn('msm6295', usage['unused_declarations'])
            compact = bytearray(0x40)
            compact[:4] = b'Vgm '
            struct.pack_into('<I', compact, 8, 0x171)
            compact.extend(b'\x62\x66')
            self.assertEqual(read_vgm_header(compact)['msm6295_clock_raw'], 0)

    @unittest.skipUnless(default_generator().is_file(), 'External PCM target generator unavailable')
    def test_public_assets_are_shared_and_compile_with_auto_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            for name, raw, facts in cases():
                with self.subTest(name=name):
                    root = Path(temp) / name
                    root.mkdir()
                    source = root / (name + '.vgm')
                    source.write_bytes(raw)
                    out = root / 'out'
                    mml, _, _ = convert(source, out, msm6295_pcm=bool(facts['expected_playbacks']), dump_passes=True, song_loop=False)
                    self.assertTrue(mml.is_file())
                    if facts['expected_playbacks']:
                        self.assertTrue((out / (name + '.mdx')).is_file())
                        self.assertTrue((out / (name + '.pdx')).is_file())
                        stats = summarize(out, name)
                        self.assertEqual(stats['route_label'], 'MSM6295')
                        self.assertEqual(stats['sample_count'], facts['expected_assets'])
                        self.assertEqual(stats['playback_count'], facts['expected_playbacks'])
                        self.assertEqual(stats['omitted_playback_count'], 0)
                        self.assertLessEqual(stats['pdx_bytes'], 1200000)
                        assessment = json.loads((out / (name + '.pcm.assessment.json')).read_text())
                        self.assertEqual(assessment['policy_selection']['reason'], 'msm6295_bank_transcoding')
                        self.assertTrue((out / (name + '.msm6295.source.json')).is_file())
                        self.assertTrue((out / (name + '.msm6295_bank.events.csv')).is_file())
                    else:
                        self.assertFalse((out / (name + '.pdx')).exists())
                    self.assertEqual(source.read_bytes(), raw)

    def test_strict_and_unsupported_bank_keep_native_source_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, commands, options in (
                    ('strict', start() + wait(1000), dict(pcm_policy='strict')),
                    ('bank', start() + wait(50) + write(1, register=15) + wait(1000), {})):
                with self.subTest(name=name):
                    source = root / (name + '.vgm')
                    source.write_bytes(make_vgm(commands))
                    out = root / name
                    with self.assertRaises(ProjectionError):
                        convert(source, out, msm6295_pcm=True, song_loop=False, **options)
                    self.assertTrue((out / (name + '.msm6295.source.json')).is_file())
                    self.assertTrue((out / (name + '.msm6295.writes.csv')).is_file())
                    self.assertFalse((out / (name + '.mdx')).exists())

    def test_crossing_song_loop_retains_guard_without_fabricated_attack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prefix = start(2) + wait(400)
            source = root / 'held.vgm'
            source.write_bytes(make_vgm(prefix + wait(200), loop_offset=len(prefix)))
            with self.assertRaisesRegex(ProjectionError, 'song-loop'):
                convert(source, root / 'loop', msm6295_pcm=True, song_loop=True, normalize_lengths=False)
            self.assertTrue((root / 'loop/held.msm6295.source.json').is_file())


if __name__ == '__main__':
    unittest.main()
