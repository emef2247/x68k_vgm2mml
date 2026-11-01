"""NES APU source route: the APU front end projects to SCC + PSG noise,
then the ordinary PSG/SCC OPM route consumes the intermediate."""
from pathlib import Path
import json
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
from conversion_config import inspect_source, select_mdx_route


def nes_vgm(body, ay=False, opll=False):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 4, 256 + len(body) + 1 - 4)
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    struct.pack_into('<I', raw, 0x84, 1789773)  # NES APU clock
    if ay:
        struct.pack_into('<I', raw, 0x74, 1789773)
        struct.pack_into('<I', raw, 0x9c, 1789773)
    if opll:
        struct.pack_into('<I', raw, 0x10, 3579545)
    return bytes(raw) + body + b'\x66'


# One audible pulse note: constant volume 15, period 253 (~440 Hz).
PULSE_NOTE = bytes.fromhex('b4 00 9f b4 02 fd b4 03 f8 62 62 b4 00 80 62')
# AY tone channel A at volume 15.
AY_ACTIVE = bytes.fromhex('a0 00 00 a0 01 01 a0 08 0f 62 a0 08 00')
# OPLL melodic key-on (register 0x20, key bit set).
OPLL_ACTIVE = bytes.fromhex('51 20 30 62 51 20 20')


class NesapuRouteTests(unittest.TestCase):
    def test_apu_only_selects_nesapu_route(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'nes.vgm'
            source.write_bytes(nes_vgm(PULSE_NOTE))
            usage = inspect_source(source)
            self.assertEqual(usage['used_chips'], ['nesapu'])
            self.assertFalse(usage['unsupported_commands'])
            self.assertEqual(select_mdx_route(usage), 'nesapu-to-opm')

    def test_apu_with_active_ay_still_routes(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'nes_ay.vgm'
            source.write_bytes(nes_vgm(PULSE_NOTE + AY_ACTIVE, ay=True))
            usage = inspect_source(source)
            self.assertEqual(usage['used_chips'], ['nesapu', 'psg'])
            self.assertEqual(select_mdx_route(usage), 'nesapu-to-opm')

    def test_apu_with_active_opll_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'nes_opll.vgm'
            source.write_bytes(nes_vgm(PULSE_NOTE + OPLL_ACTIVE, opll=True))
            usage = inspect_source(source)
            with self.assertRaises(ValueError) as caught:
                select_mdx_route(usage)
            self.assertIn('Unsupported MDX source combination', str(caught.exception))

    def test_cli_generates_mdx_through_intermediate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'nes.vgm'
            source.write_bytes(nes_vgm(PULSE_NOTE))
            outdir = root / 'output'
            run = subprocess.run(
                [sys.executable, str(ROOT / 'vgm2mml.py'), str(source),
                 '--outdir', str(outdir)],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads((outdir / 'nes.conversion.json').read_text())
            self.assertEqual(report['chip_projection'], 'nesapu-to-opm')
            self.assertEqual(report['status'], 'generated')
            intermediate = (outdir / '_nesapu_target' / 'nes.vgm').read_bytes()
            # The downstream PSG/SCC profile models the AY8910 legacy type;
            # the intermediate copy declares type 0.
            self.assertEqual(intermediate[0x78], 0)
            self.assertTrue((outdir / 'nes.nesapu_projection.json').is_file())
            self.assertTrue((outdir / 'nes.mdx.mml').is_file())

    def test_cli_nes_balance_gains_reach_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'nes.vgm'
            source.write_bytes(nes_vgm(PULSE_NOTE))

            def projection_summary(outdir, *extra):
                run = subprocess.run(
                    [sys.executable, str(ROOT / 'vgm2mml.py'), str(source),
                     '--outdir', str(outdir), *extra],
                    capture_output=True, text=True, timeout=120)
                self.assertEqual(run.returncode, 0, run.stderr)
                summary = json.loads((outdir / 'nes.nesapu_projection.json').read_text())
                return summary['mapping_gains']

            self.assertEqual(projection_summary(root / 'plain'), {})
            self.assertEqual(
                projection_summary(root / 'balanced', '--nes-balance'),
                {'pulse': 1.3, 'triangle': 0.75, 'noise': 0.8,
                 'dpcm': 1.25, 'fds': 1.0})
            overridden = projection_summary(root / 'override', '--nes-gain', 'pulse=1.0')
            self.assertEqual(overridden['pulse'], 1.0)
            self.assertEqual(overridden['triangle'], 0.75)

    def test_cli_dpcm_rides_adpcm_by_default(self):
        # A covered DPCM sample (RAM block + trigger) is diverted to
        # the MSM6258 ADPCM/PDX target: the projection keeps the SCC
        # lane free of slices and the MDX gains a PCM track. The PDX
        # helper is stubbed with a minimal valid builder.
        block = (b'\x67\x66\xc2' + struct.pack('<I', 2 + 129)
                 + struct.pack('<H', 0xc000) + b'\xff' * 129)
        trigger = bytes.fromhex(
            'b4 12 00 b4 13 08 b4 10 0f b4 15 10') + b'\x62' * 6
        stub = (
            '#!/usr/bin/env python3\n'
            'import struct, sys\n'
            'from pathlib import Path\n'
            'args = sys.argv[1:]\n'
            'if args[0] == "--build-pdx":\n'
            '    manifest, pdx = Path(args[1]), Path(args[2])\n'
            '    rows = []\n'
            '    for line in manifest.read_text().splitlines()[1:]:\n'
            '        if line.strip():\n'
            '            sid, bank, slot, file = line.split("\\t")\n'
            '            rows.append((int(slot), (manifest.parent / file).read_bytes()))\n'
            '    table, payload, offset = bytearray(768), bytearray(), 768\n'
            '    for slot, data in sorted(rows):\n'
            '        struct.pack_into(">II", table, slot * 8, offset, len(data))\n'
            '        payload += data; offset += len(data)\n'
            '    pdx.write_bytes(bytes(table) + bytes(payload))\n'
            'else:\n'
            '    offsets = [0] + [34 + 2 * i for i in range(16)]\n'
            '    body = b"".join(b"\\xe8\\x00" if i == 0 else b"\\xf1\\x00" for i in range(16))\n'
            '    Path(args[3]).write_bytes(b"STUB\\r\\n\\x1a\\x00" + struct.pack(">17H", *offsets) + body)\n')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'nes.vgm'
            source.write_bytes(nes_vgm(block + PULSE_NOTE + trigger))
            helper = root / 'helper.py'
            helper.write_text(stub)
            helper.chmod(0o755)

            def run_cli(outdir, *extra):
                run = subprocess.run(
                    [sys.executable, str(ROOT / 'vgm2mml.py'), str(source),
                     '--outdir', str(outdir), '--force',
                     '--pcm-generator', str(helper), *extra],
                    capture_output=True, text=True, timeout=300)
                self.assertEqual(run.returncode, 0, run.stderr)
                return json.loads((outdir / 'nes.conversion.json').read_text())

            report = run_cli(root / 'adpcm')
            self.assertEqual(report['status'], 'generated')
            settings = report['projection_settings']
            self.assertEqual(settings['nes_dpcm']['events'], 1)
            self.assertEqual(settings['nes_dpcm']['samples'], 1)
            summary = json.loads(
                (root / 'adpcm' / 'nes.nesapu_projection.json').read_text())
            self.assertEqual(summary['dpcm_slices'], 0)
            self.assertEqual(summary['dpcm_external_pcm']['events'], 1)
            mml = (root / 'adpcm' / 'nes.mdx.mml').read_text()
            self.assertIn('#pcmfile "nes.pdx"', mml)
            self.assertIn('/* Track P */', mml)

            report = run_cli(root / 'slices', '--no-nes-dpcm')
            self.assertNotIn('nes_dpcm',
                             report['projection_settings'] or {})
            summary = json.loads(
                (root / 'slices' / 'nes.nesapu_projection.json').read_text())
            self.assertGreater(summary['dpcm_slices'], 0)
            self.assertNotIn('dpcm_external_pcm', summary)
            mml = (root / 'slices' / 'nes.mdx.mml').read_text()
            self.assertNotIn('#pcmfile', mml)


if __name__ == '__main__':
    unittest.main()
