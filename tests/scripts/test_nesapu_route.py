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


if __name__ == '__main__':
    unittest.main()
