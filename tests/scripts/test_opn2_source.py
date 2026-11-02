"""OPN2 (YM2612) S1: frontend inventory, route, and native analysis."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'py'))

from conversion_config import inspect_source, select_mdx_route
from opn2_source import analyze_opn2_source

OPN2_CLOCK = 7670454
DCSG_CLOCK = 3579545


def build_vgm(body, *, opn2_clock=OPN2_CLOCK, version=0x171):
    header = bytearray(0x100)
    header[0:4] = b'Vgm '
    struct.pack_into('<I', header, 0x04, 0x100 + len(body) - 4)
    struct.pack_into('<I', header, 0x08, version)
    struct.pack_into('<I', header, 0x0c, DCSG_CLOCK)
    struct.pack_into('<I', header, 0x2c, opn2_clock)
    struct.pack_into('<I', header, 0x34, 0x100 - 0x34)
    return bytes(header) + bytes(body)


def fm_song_body():
    body = bytearray()
    def w(reg, val):
        body.extend((0x52, reg, val))
    w(0x22, 0x08)
    w(0xb0, 0x32)
    w(0xa4, 0x22)
    w(0xa0, 0x00)
    w(0x28, 0xf0)
    body.append(0x62)
    w(0x28, 0x00)
    w(0x2b, 0x80)
    for index in range(20):
        w(0x2a, 0x80 + index)
        body.append(0x73)
    w(0x2b, 0x00)
    body.extend((0x50, 0xac, 0x50, 0x08, 0x50, 0xb5))
    body.append(0x62)
    body.extend((0x50, 0xbf))
    body.append(0x66)
    return body


def inspect(raw):
    with tempfile.NamedTemporaryFile('wb', suffix='.vgm', delete=False) as stream:
        stream.write(raw)
        path = stream.name
    try:
        return inspect_source(path)
    finally:
        Path(path).unlink()


class Opn2FrontendTests(unittest.TestCase):
    def test_inventory_and_route(self):
        usage = inspect(build_vgm(fm_song_body()))
        self.assertEqual(usage['used_chips'], ['dcsg', 'opn2'])
        self.assertEqual(usage['declared_clocks']['opn2'], OPN2_CLOCK)
        self.assertEqual(usage['unsupported_commands'], [])
        self.assertEqual(select_mdx_route(usage), 'opn2-to-opm')

    def test_opn2_only_route(self):
        body = bytes((0x52, 0x28, 0xf0, 0x62, 0x52, 0x28, 0x00, 0x66))
        usage = inspect(build_vgm(body))
        self.assertEqual(usage['used_chips'], ['opn2'])
        self.assertEqual(select_mdx_route(usage), 'opn2-to-opm')

    def test_second_instance_is_unsupported(self):
        body = bytes((0x52, 0x28, 0xf0, 0xa2, 0x28, 0xf1, 0x66))
        usage = inspect(build_vgm(body))
        reasons = [item['reason'] for item in usage['unsupported_commands']]
        self.assertIn('Second OPN2 instance is not supported', reasons)
        with self.assertRaises(ValueError):
            select_mdx_route(usage)

    def test_missing_clock_declaration_is_unsupported(self):
        usage = inspect(build_vgm(fm_song_body(), opn2_clock=0))
        reasons = [item['reason'] for item in usage['unsupported_commands']]
        self.assertTrue(any('no clock declaration' in reason for reason in reasons))

    def test_dac_stream_controls_are_retained_evidence(self):
        body = bytearray()
        body.extend(bytes((0x67, 0x66, 0x00)) + struct.pack('<I', 4) + bytes((1, 2, 3, 4)))
        body.extend((0x90, 0x00, 0x02, 0x00, 0x2a))
        body.extend((0x91, 0x00, 0x00, 0x01, 0x00))
        body.extend(bytes((0x95, 0x00)) + struct.pack('<H', 0) + bytes((0,)))
        body.extend((0x52, 0x28, 0xf0, 0x62, 0x52, 0x28, 0x00, 0x66))
        usage = inspect(build_vgm(bytes(body)))
        self.assertEqual(usage['unsupported_commands'], [])
        self.assertEqual(len(usage['dac_stream_controls']), 3)
        self.assertEqual(select_mdx_route(usage), 'opn2-to-opm')


    def test_dac_stream_seek_and_play_are_opn2_evidence(self):
        body = bytearray()
        body.extend(bytes((0x67, 0x66, 0x00)) + struct.pack('<I', 4) + bytes((1, 2, 3, 4)))
        body.extend(bytes((0xe0,)) + struct.pack('<I', 0))
        body.extend((0x83, 0x85, 0x80))
        body.extend((0x52, 0x28, 0xf0, 0x62, 0x52, 0x28, 0x00, 0x66))
        usage = inspect(build_vgm(bytes(body)))
        self.assertEqual(usage['unsupported_commands'], [])
        self.assertEqual(usage['dac_stream'], {'play_commands': 3, 'seek_commands': 1})
        self.assertEqual(select_mdx_route(usage), 'opn2-to-opm')


class Opn2AnalysisTests(unittest.TestCase):
    def test_segments_dac_state_and_measurements(self):
        raw = build_vgm(fm_song_body())
        usage = inspect(raw)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'song.vgm'
            source.write_bytes(raw)
            summary = analyze_opn2_source(source, tmp, 'song', usage)
            for name in ('registers', 'states', 'segments', 'unmodeled'):
                self.assertTrue((Path(tmp) / f'song.native.opn2.{name}.csv').is_file())
        self.assertEqual(summary['clock_hz'], OPN2_CLOCK)
        self.assertEqual(summary['key_counts']['channel_attack_events'], 1)
        self.assertEqual(summary['key_counts']['operator_keyons'], 4)
        self.assertEqual(summary['unmodeled_counts'], {'dac_data': 20})
        self.assertEqual(summary['dac']['data_writes'], 20)
        self.assertEqual(summary['dac']['runs'], 1)
        self.assertEqual(summary['dac']['run_bytes'], [20])
        self.assertEqual(summary['dac']['median_write_gap_samples'], 4)
        self.assertEqual(summary['dac']['dac_enabled_samples'], 80)
        self.assertEqual(summary['dac']['stream_controls'], 0)
        self.assertGreater(summary['dcsg']['channels']['0:1']['duty'], 0.4)
        self.assertFalse(summary['csm_observed'])


if __name__ == '__main__':
    unittest.main()
