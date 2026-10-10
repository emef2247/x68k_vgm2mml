"""Source-time gate omission, distinct from target-clock quantization."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts')]
from opm_conversion import convert
from opm_mdx import project_segments
from opm_note_normalization import normalize_projection
from opm_target_pruning import omit_short_gates
from test_opm_mdx import analyze, write, wait
from test_opm_reader import vgm


def setup():
    body = write(0x20, 0xc7) + write(0x28, 0x40) + write(0x30, 0) + write(0x38, 0)
    for slot in range(4):
        for base, value in ((0x40, 1), (0x60, 20), (0x80, 31), (0xa0, 0), (0xc0, 0), (0xe0, 15)):
            body += write(base + slot * 8, value)
    return body


class ShortOutputGateTests(unittest.TestCase):
    def fixture(self, folder, body):
        source = folder / 'gates.vgm'
        source.write_bytes(vgm(setup() + body))
        analysis = analyze(source, folder / 'trace')
        projection = project_segments(analysis.segments, end_vgmticks=analysis.source_end_vgmticks)
        return source, analysis, projection

    def test_352_omitted_353_retained_and_long_note_control_slice_kept(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, analysis, before = self.fixture(root, wait(441) + write(8, 120) + wait(352) + write(8, 0)
                + wait(441) + write(8, 120) + wait(353) + write(8, 0)
                + wait(441) + write(8, 120) + wait(50) + write(0x28, 0x45)
                + wait(8770) + write(8, 0) + wait(441))
            after, report = omit_short_gates(analysis.events, before)
            self.assertEqual(report['omitted_gate_count'], 1)
            self.assertEqual(report['omitted_duration_samples'], 352)
            self.assertEqual([w.data for w in after.writes if w.register == 8], [120, 0, 120, 0])
            self.assertIn((0x28, 0x45), [(w.register, w.data) for w in after.writes])
            self.assertEqual(after.source_end_vgmticks, before.source_end_vgmticks)
            self.assertEqual(after.end_mdx_tick, before.end_mdx_tick)
            self.assertEqual([w for w in after.writes if w.register != 8],
                             [w for w in before.writes if w.register != 8])

    def test_partial_retrigger_redundant_and_unclosed_operations_not_short_notes(self):
        bodies = (write(8, 120) + wait(50) + write(8, 8) + wait(50) + write(8, 0),
                  write(8, 120) + wait(50) + write(8, 120) + wait(50) + write(8, 0),
                  write(8, 120) + wait(50))
        for body in bodies:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as temp:
                _, analysis, before = self.fixture(Path(temp), body)
                after, report = omit_short_gates(analysis.events, before)
                self.assertEqual(report['omitted_gate_count'], 0)
                self.assertEqual(after, before)

    def test_omission_before_quantization_keeps_original_source_and_total_time(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, original, _ = self.fixture(root, wait(441) + write(8, 120)
                                               + wait(352) + write(8, 0) + wait(882))
            source_bytes = source.read_bytes()
            _, off, p = convert(source, root / 'off', normalize_lengths=False, dump_passes=True)
            mml, on, q = convert(source, root / 'on', normalize_lengths=True, dump_passes=True)
            report = json.loads((root / 'on/gates.mdx.normalization.json').read_text())
            self.assertEqual(original, on)
            self.assertEqual(on, off)
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(report['short_note_policy']['omitted_gate_count'], 1)
            self.assertFalse(any(w.register == 8 for w in q.writes))
            self.assertTrue(any(w.register == 8 for w in p.writes))
            self.assertEqual(q.source_end_vgmticks, p.source_end_vgmticks)
            self.assertLessEqual(abs(q.end_projected_vgmticks-p.source_end_vgmticks), 352)
            self.assertGreater(q.sample_multiplier, 1)
            self.assertIn('r', mml.read_text())
            self.assertNotIn('y8,120', mml.read_text())
            self.assertTrue((root / 'on/gates.mdx.normalization.csv').is_file())

    def test_side_effect_pulse_preserves_positive_duration(self):
        with tempfile.TemporaryDirectory() as temp:
            _, analysis, before = self.fixture(Path(temp), write(8, 120) + wait(1000) + write(8, 0)
                + wait(40) + write(8, 120) + wait(1000) + write(8, 0)
                + write(1, 2) + wait(20) + write(1, 0) + wait(441))
            after, report, _ = normalize_projection(analysis.segments, before,
                output_short_note_policy=True, source_events=analysis.events)
            keys = [w.mdx_tick for w in after.writes if w.register == 8]
            pulse = [w.mdx_tick for w in after.writes if w.register == 1]
            self.assertTrue(all(a < b for a, b in zip(keys, keys[1:])))
            self.assertLess(pulse[0], pulse[1])
            self.assertEqual(report['collapsed_protected_intervals'], 0)

    def test_short_rest_coalesces_but_both_key_requests_survive(self):
        with tempfile.TemporaryDirectory() as temp:
            _, analysis, before = self.fixture(Path(temp), write(8, 120) + wait(1000) + write(8, 0)
                + wait(12) + write(8, 120) + wait(1000) + write(8, 0) + wait(441))
            after, report, _ = normalize_projection(analysis.segments, before,
                output_short_note_policy=True, source_events=analysis.events)
            keys = [w for w in after.writes if w.register == 8]
            self.assertEqual([w.data for w in keys], [120, 0, 120, 0])
            self.assertLess(keys[0].mdx_tick, keys[1].mdx_tick)
            self.assertEqual(keys[1].mdx_tick, keys[2].mdx_tick)
            self.assertLess(keys[2].mdx_tick, keys[3].mdx_tick)
            self.assertEqual(report['coalesced_rest_duration_samples'], 12)
            self.assertTrue(report['intentional_timing_loss'])

    def test_original_mapped_352_353_cutoff_precedes_intermediate_rounding(self):
        for original_duration, intermediate_duration, omitted in ((352, 361, 1), (353, 350, 0)):
            with self.subTest(duration=original_duration), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source, analysis, _ = self.fixture(root, wait(451) + write(8, 120)
                    + wait(intermediate_duration) + write(8, 0) + wait(882))
                on, off = [e for e in analysis.events if e.register == 8]
                mapping = {on.source_event_id: 447, off.source_event_id: 447 + original_duration}
                _, unchanged, result = convert(source, root / 'out', normalize_lengths=True,
                    normalization_source_times=mapping, dump_passes=True)
                report = json.loads((root / 'out/gates.mdx.normalization.json').read_text())
                self.assertEqual(report['short_note_policy']['omitted_gate_count'], omitted)
                self.assertEqual(len([w for w in result.writes if w.register == 8]), 2 * (1 - omitted))
                self.assertEqual(unchanged, analysis)
                self.assertEqual(report['short_note_policy']['timing_basis'], 'original_source_before_normalization')

    def test_positive_song_with_all_notes_omitted_keeps_positive_end(self):
        with tempfile.TemporaryDirectory() as temp:
            _, analysis, before = self.fixture(Path(temp), write(8, 120) + wait(100) + write(8, 0))
            after, report, _ = normalize_projection(analysis.segments, before,
                output_short_note_policy=True, source_events=analysis.events)
            self.assertEqual(report['short_note_policy']['omitted_gate_count'], 1)
            self.assertGreater(after.end_mdx_tick, 0)
            self.assertFalse(any(w.register == 8 for w in after.writes))

    def test_loop_crossing_short_gate_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            _, analysis, before = self.fixture(Path(temp), wait(400) + write(8, 120)
                                               + wait(352) + write(8, 0) + wait(1000))
            after, report, _ = normalize_projection(analysis.segments, before,
                output_short_note_policy=True, source_events=analysis.events,
                loop_metadata=dict(status='valid', loop_offset=1, loop_start_samples=500,
                                   decoded_end_samples=before.source_end_vgmticks))
            self.assertEqual(report['short_note_policy']['omitted_gate_count'], 0)
            self.assertEqual(len([w for w in after.writes if w.register == 8]), 2)


if __name__ == '__main__':
    unittest.main()
