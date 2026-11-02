"""Native OPNA Segment-to-OPM target boundary checks."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))

from conversion_config import inspect_source, select_mdx_route
from opna_opm import project, write_vgm
from vgm_reader import parse_vgm
from vgm_timing import command_times


def vgm(body, clock=7987200, loop_offset=None):
    raw = bytearray(0x100) + body + b'\x66'
    raw[:4] = b'Vgm '
    for offset, value in ((4, len(raw)-4), (8, 0x171), (0x34, 0xcc), (0x48, clock)):
        struct.pack_into('<I', raw, offset, value)
    if loop_offset is not None:
        struct.pack_into('<I', raw, 0x1c, 0x100 + loop_offset - 0x1c)
    return raw


class OpnaOpmTests(unittest.TestCase):
    def analyze(self, body):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.vgm'
            source.write_bytes(vgm(body))
            metadata = {}
            parse_vgm(str(source), str(root / 'passes'), opna_metadata=metadata,
                      dump_opna_segments=True, loop_count=1)
            return metadata['analysis']

    def test_operator_bank_pan_key_and_committed_pitch(self):
        analysis = self.analyze(bytes.fromhex(
            '57 38 71 57 b0 1f 57 b4 80 '
            '56 a4 22 57 a0 69 56 28 f4 61 01 00 56 28 04'))
        before = analysis.segments
        rows, _ = project(analysis, clock_hz=7987200)
        controls = [(r['target_register'], r['target_data']) for r in rows]
        self.assertIn((0x54, 0x71), controls)  # OPN bank2/channel3 -> OPM bank2/channel4.
        self.assertIn((0x24, 0x5f), controls)  # left only -> OPM bit6.
        self.assertIn((8, 0x7c), controls)
        self.assertIn((8, 4), controls)
        pitch = [r for r in rows if r['source_frequency_hz'] is not None]
        self.assertTrue(pitch)
        # FNUM 0x269 at block 4 is C4 in the YM2608 note table; at the
        # 7.9872 MHz clock the hardware formula (phase counter 20 bits,
        # block scales by 2**(block-1)) gives ~261.1 Hz, not ~522.2.
        expected = 0x269 * 7987200 / (144 * 2**17)
        self.assertAlmostEqual(pitch[0]['source_frequency_hz'], expected)
        self.assertEqual(analysis.segments, before)

    def test_lfo_depths_bridged_while_lfo_active(self):
        analysis = self.analyze(bytes.fromhex(
            '56 22 0d 56 b4 e3 56 a4 22 56 a0 69 56 28 f0 '
            '61 01 00 56 28 00 56 22 05'))
        rows, losses = project(analysis, clock_hz=7987200)
        controls = [(r['target_register'], r['target_data']) for r in rows]
        self.assertIn((0x1b, 0x02), controls)      # triangle waveform
        self.assertIn((0x19, 0x80 | 86), controls)  # PMD 86
        self.assertIn((0x19, 16), controls)         # AMD 16
        self.assertEqual(losses['lfo_depths_bridged'], 1)
        start = controls.index((0x19, 0x80 | 86))
        self.assertIn((0x19, 0x80), controls[start:])
        self.assertIn((0x19, 0), controls[start:])

    def test_prescaler_shifts_eg_rates_but_not_zero(self):
        # Prescaler 3: AR/D1R/D2R +2 in the 5-bit space; RR +1 (its
        # effective rate is 4*RR+2 on both chips); rate 0 stays frozen.
        analysis = self.analyze(bytes.fromhex(
            '56 2e 00 '
            '56 50 0a 56 60 14 56 70 08 56 80 25 '
            '56 54 00 56 28 f0'))
        rows, losses = project(analysis, clock_hz=7987200)
        controls = [(r['target_register'], r['target_data']) for r in rows]
        self.assertIn((0x80, 0x0c), controls)   # AR 10 -> 12
        self.assertIn((0xa0, 0x16), controls)   # D1R 20 -> 22
        self.assertIn((0xc0, 0x0a), controls)   # D2R 8 -> 10
        self.assertIn((0xe0, 0x26), controls)   # SL 2, RR 5 -> 6
        self.assertIn((0x88, 0x00), controls)   # AR 0 stays 0
        self.assertGreater(losses['eg_rate_prescaler_adjustments'], 0)
        # Prescaler 2: +3 steps on the 5-bit rates, RR +1.
        analysis = self.analyze(bytes.fromhex(
            '56 2f 00 56 50 0a 56 80 25 56 28 f0'))
        rows, _ = project(analysis, clock_hz=7987200)
        controls = [(r['target_register'], r['target_data']) for r in rows]
        self.assertIn((0x80, 0x0d), controls)
        self.assertIn((0xe0, 0x26), controls)
        analysis = self.analyze(bytes.fromhex('56 50 0a 56 80 25 56 28 f0'))
        rows, losses = project(analysis, clock_hz=7987200)
        controls = [(r['target_register'], r['target_data']) for r in rows]
        self.assertIn((0x80, 0x0a), controls)
        self.assertIn((0xe0, 0x25), controls)
        self.assertNotIn('eg_rate_prescaler_adjustments', losses)

    def test_output_enable_changes_pan_without_invented_key_edges(self):
        analysis = self.analyze(bytes.fromhex(
            '56 29 80 57 b4 c0 56 28 f4 62 56 29 00 62 56 29 80 62'))
        rows, _ = project(analysis, clock_hz=7987200)
        self.assertEqual([(r['target_register'], r['target_data']) for r in rows
                          if r['target_register'] == 8], [(8, 0x7c)])
        self.assertEqual([r['target_data'] for r in rows if r['target_register'] == 0x24], [0, 0xc0, 0, 0xc0])

    def test_same_sample_loop_marker_uses_event_order_and_preserves_end(self):
        rows = [dict(source_event_id=i, source_vgmticks=3,
                     target_register=8, target_data=value) for i, value in ((5, 0), (7, 0x78))]
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'target.vgm'
            write_vgm(rows, target, end=9, loop_start=3, loop_event_id=7)
            raw = target.read_bytes()
            self.assertEqual(int.from_bytes(raw[0x1c:0x20], 'little') + 0x1c,
                             rows[1]['target_command_address'])
            events = list(command_times(raw))
            self.assertEqual(events[-1].vgmticks, 9)
            self.assertEqual([e.vgmticks for e in events if e.command == 0x54], [3, 3])

    def test_inventory_dispatch_and_unsupported_fm(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source.vgm'
            source.write_bytes(vgm(bytes.fromhex('56 28 f0 62')))
            self.assertEqual(select_mdx_route(inspect_source(source)), 'opna-fm-to-opm')
            source.write_bytes(vgm(bytes.fromhex('a6 28 f0 62')))
            with self.assertRaisesRegex(ValueError, 'Second OPNA'):
                select_mdx_route(inspect_source(source))
        for body in ('56 27 40 56 28 f2', '56 27 80 56 28 f2', '56 21 ff 56 28 f0'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                project(self.analyze(bytes.fromhex(body)), clock_hz=7987200)


if __name__ == '__main__':
    unittest.main()
