"""Canonical frontend routing and option boundaries."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_opm_reader import vgm

ROOT = Path(__file__).resolve().parents[2]


class CliRoutes(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'vgm2mml.py'), *map(str, args)],
                              capture_output=True, text=True, timeout=30)

    def test_explicit_mdx_matches_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'test.vgm'
            source.write_bytes(vgm(bytes.fromhex('54 28 40 54 08 78 62 54 08 00 62')))
            for name, options in [('default', []), ('explicit', ['--target', 'mdx'])]:
                run = self.run_cli(source, '--outdir', root / name, *options)
                self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual((root / 'default/test.mdx.mml').read_bytes(),
                             (root / 'explicit/test.mdx.mml').read_bytes())

    def test_target_specific_options_are_rejected(self):
        for options, message in [
            (['--target', 'mgs', '--notation', 'registers'], 'require --target mdx'),
            (['--track-layout', 'conductor'], 'require --notation registers'),
        ]:
            with self.subTest(options=options):
                run = self.run_cli('unused.vgm', *options)
                self.assertEqual(run.returncode, 2)
                self.assertIn(message, run.stderr)

    def test_psg_only_input_does_not_silently_select_mgs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'empty.vgm'
            source.write_bytes(vgm(bytes.fromhex('62'), clock=0))
            run = self.run_cli(source, '--outdir', root / 'output')
            self.assertEqual(run.returncode, 2)
            self.assertIn('no supported OPM stream', run.stderr)
            self.assertFalse((root / 'output/empty.mdx.mml').exists())

    def test_native_title_language_and_explicit_override(self):
        import struct
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'title.vgm'
            raw = bytearray(vgm(bytes.fromhex('54 28 40 54 08 78 62 54 08 00 62')))
            payload = ('English' + chr(0) + 'Japanese' + chr(0) * 10).encode('utf-16-le')
            struct.pack_into('<I', raw, 0x14, len(raw) - 0x14)
            raw += b'Gd3 ' + struct.pack('<II', 0x100, len(payload)) + payload
            struct.pack_into('<I', raw, 4, len(raw) - 4)
            source.write_bytes(raw)
            for name, options, expected in [
                ('ja', [], 'Japanese'),
                ('en', ['--gd3-language', 'en'], 'English'),
                ('override', ['--title', 'Override'], 'Override'),
            ]:
                run = self.run_cli(source, '--outdir', root / name, *options)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn('#title "' + expected + '"',
                              (root / name / 'title.mdx.mml').read_text(encoding='utf-8'))

    def test_native_rejects_explicit_scc_gain_including_compatibility_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'gain.vgm'
            source.write_bytes(vgm(bytes.fromhex('54 28 40 54 08 78 62 54 08 00 62')))
            for gain in ('0.125', '1'):
                run = self.run_cli(source, '--outdir', root / 'output', '--scc-gain', gain)
                self.assertEqual(run.returncode, 2)
                self.assertIn('do not apply to native MDX', run.stderr)
