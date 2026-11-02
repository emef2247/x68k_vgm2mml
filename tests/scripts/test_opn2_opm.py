"""OPN2 (YM2612) S2: FM -> OPM projection shape and force policy."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'py'))

from opn2_opm import convert, project
from opn2_source import build_analysis

OPN2_CLOCK = 7670454


def build_vgm(body):
    header = bytearray(0x100)
    header[0:4] = b'Vgm '
    struct.pack_into('<I', header, 0x04, 0x100 + len(body) - 4)
    struct.pack_into('<I', header, 0x08, 0x171)
    struct.pack_into('<I', header, 0x0c, 3579545)
    struct.pack_into('<I', header, 0x2c, OPN2_CLOCK)
    struct.pack_into('<I', header, 0x34, 0x100 - 0x34)
    return bytes(header) + bytes(body)


def analyze(body):
    tmp = tempfile.mkdtemp()
    source = Path(tmp) / 'song.vgm'
    source.write_bytes(build_vgm(body))
    analysis, clock_raw, _end, _events = build_analysis(source, Path(tmp) / 'trace.csv')
    return analysis, clock_raw


def fm_body():
    body = bytearray()
    def w(cmd, reg, val):
        body.extend((cmd, reg, val))
    w(0x52, 0xb0, 0x32)
    w(0x52, 0xa4, 0x22)
    w(0x52, 0xa0, 0x00)
    w(0x52, 0x28, 0xf0)   # key on FM ch0
    w(0x53, 0xa4, 0x22)
    w(0x53, 0xa0, 0x00)
    w(0x52, 0x28, 0xf4)   # key on FM ch3 (port 1, local 0)
    body.append(0x62)
    w(0x52, 0x28, 0x00)
    w(0x52, 0x28, 0x04)
    body.append(0x66)
    return body


class Opn2ProjectionTests(unittest.TestCase):
    def test_key_and_pitch_rows_use_opna_channel_map(self):
        analysis, clock_raw = analyze(fm_body())
        rows, losses = project(analysis, clock_raw=clock_raw)
        keys = [r for r in rows if r['target_register'] == 8]
        self.assertEqual([r['target_data'] for r in keys], [0xf << 3 | 0, 0xf << 3 | 4, 0, 4])
        self.assertTrue(all(r['source_chip'] == 'opn2_fm' for r in rows if r['source_chip']))
        kc = [r for r in rows if r['target_register'] in (0x28, 0x2c)]
        self.assertEqual(len(kc), 2)
        self.assertFalse(losses.get('dac_data_writes_omitted'))

    def test_unmapped_operator_slot_is_tolerated(self):
        body = bytearray()
        body.extend((0x52, 0x87, 0xff, 0x52, 0x28, 0xf0, 0x62, 0x52, 0x28, 0x00, 0x66))
        analysis, clock_raw = analyze(bytes(body))
        _rows, losses = project(analysis, clock_raw=clock_raw)
        self.assertEqual(losses['unmapped_operator_slot_writes_ignored'], 1)

    def test_ch3_special_rejected_without_force(self):
        body = bytearray()
        body.extend((0x52, 0x27, 0x40, 0x52, 0x28, 0xf0, 0x62, 0x52, 0x28, 0x00, 0x66))
        analysis, clock_raw = analyze(bytes(body))
        with self.assertRaises(ValueError):
            project(analysis, clock_raw=clock_raw)
        _rows, losses = project(analysis, clock_raw=clock_raw, force=True)
        self.assertGreater(losses['ch3_special_frequencies_not_projected'], 0)


def dac_body():
    body = bytearray()
    def w0(reg, val):
        body.extend((0x52, reg, val))
    def w1(reg, val):
        body.extend((0x53, reg, val))
    w1(0xb2, 0x32)         # FM ch6 (index 5) algo/fb on port 1
    w1(0xb6, 0xc0)         # FM ch6 L/R on
    w1(0xa2, 0x00)
    w1(0xa6, 0x22)
    w0(0x28, 0xf6)         # key on ch6 (port 1, local 2)
    body.append(0x62)
    w0(0x2b, 0x80)         # DAC enable: ch6 FM output gated
    for index in range(8):
        w0(0x2a, 0x80 + index)
        body.append(0x73)
    w0(0x2b, 0x00)         # DAC disable: gate released
    body.append(0x62)
    w0(0x28, 0x06)         # key off ch6
    body.append(0x66)
    return body


class Opn2DacPolicyTests(unittest.TestCase):
    def test_dac_data_requires_force_or_bridge(self):
        analysis, clock_raw = analyze(dac_body())
        with self.assertRaises(ValueError):
            project(analysis, clock_raw=clock_raw)

    def test_dac_data_projects_to_pcm_via_bridge(self):
        generator = next((path for path in (
            Path(__file__).resolve().parents[2] / 'scripts/mdx_fixture_generator/target/release/mdx-fixture-generator',
            Path.home() / 'workspace/x68k_c140_worktree/scripts/mdx_fixture_generator/target/release/mdx-fixture-generator')
            if path.is_file()), None)
        if generator is None:
            self.skipTest('MDX fixture generator is not built in this environment')
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'song.vgm'
            source.write_bytes(build_vgm(dac_body()))
            mml, settings = convert(source, Path(tmp) / 'out', pcm_generator=generator)
            self.assertTrue(Path(mml).is_file())
            self.assertEqual(settings['dac']['playbacks'], 1)
            self.assertEqual(settings['dac']['write_bytes'], 8)
            self.assertEqual(settings['excluded_or_approximated']
                             ['dac_data_writes_projected_to_pcm'], 8)
            self.assertTrue(list(Path(tmp, 'out').rglob('*.pdx')))

    def test_dac_enable_gates_ch6_output(self):
        analysis, clock_raw = analyze(dac_body())
        rows, losses = project(analysis, clock_raw=clock_raw, force=True)
        self.assertEqual(losses['dac_data_writes_omitted'], 8)
        controls = [r for r in rows if r['target_register'] == 0x26]  # OPM ch6 control
        self.assertGreaterEqual(len(controls), 2)
        gated = [r for r in controls if r['reason'].startswith('DAC enable')]
        self.assertTrue(gated)
        self.assertEqual(gated[0]['target_data'] & 0xc0, 0)


    def test_dac_writes_while_never_enabled_are_inert(self):
        body = bytearray()
        body.extend((0x52, 0x2a, 0x80, 0x52, 0x2a, 0x81, 0x52, 0x28, 0xf0,
                     0x62, 0x52, 0x28, 0x00, 0x66))
        analysis, clock_raw = analyze(bytes(body))
        _rows, losses = project(analysis, clock_raw=clock_raw)
        self.assertEqual(losses['dac_data_writes_while_disabled_ignored'], 2)
        self.assertNotIn('dac_data_writes_omitted', losses)


class Opn2ConvertTests(unittest.TestCase):
    def test_dac_stream_without_bridge_requires_force_and_is_recorded(self):
        body = bytes((0x52, 0x28, 0xf0, 0x62, 0x52, 0x28, 0x00, 0x66))
        stream = {'play_commands': 12, 'seek_commands': 2}
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'song.vgm'
            source.write_bytes(build_vgm(body))
            with self.assertRaises(ValueError):
                convert(source, Path(tmp) / 'out', dac_stream=stream, dac=False)
            _mml, settings = convert(source, Path(tmp) / 'out', dac_stream=stream,
                                      dac=False, force=True)
            omitted = settings['force_projection']['omitted']
            self.assertEqual([o['source_chip'] for o in omitted], ['opn2_dac_stream'])
            self.assertEqual(omitted[0]['play_commands'], 12)

    def test_dcsg_audible_requires_force_and_is_recorded(self):
        body = bytearray()
        body.extend((0x52, 0x28, 0xf0, 0x62, 0x52, 0x28, 0x00))
        body.extend((0x50, 0xac, 0x50, 0x08, 0x50, 0xb5, 0x62, 0x50, 0xbf, 0x66))
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'song.vgm'
            source.write_bytes(build_vgm(bytes(body)))
            with self.assertRaises(ValueError):
                convert(source, Path(tmp) / 'out', dcsg_present=True)
            mml, settings = convert(source, Path(tmp) / 'out', dcsg_present=True, force=True)
            self.assertTrue(Path(mml).is_file())
            omitted = settings['force_projection']['omitted']
            self.assertEqual([o['source_chip'] for o in omitted], ['dcsg'])


if __name__ == '__main__':
    unittest.main()
