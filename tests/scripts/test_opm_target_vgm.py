"""Projected intermediate provenance and reuse of the canonical OPM path."""
import csv
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT)]
from chip_segments import PsgSegment, SccAnalysis
from opm_mdx import projected_samples
from opm_performance import build_performance
from opm_performance_verify import compare_performance
from opm_target_vgm import write_target_vgm
from psg_scc_conversion import convert
from psg_scc_opm import project
from vgm_timing import command_times


class TargetVgmTests(unittest.TestCase):
    def test_serialization_maps_real_command_ids_and_preserves_end(self):
        first = PsgSegment('v', 0., 0, 0, 1, 200, 15, 4, 'c', 0, (),
                           1, 0, 0, 0, 0, 0x3e, 15, vgmticks=70000, vgmticks_end=71000)
        baseline = project({0: [first]}, SccAnalysis({}, ()), psg_clock=1789772,
                           scc_clock=0, end_vgmticks=80000, psg_model='fm')
        performance = build_performance(baseline)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_target_vgm(performance, root/'projected.vgm', mapping_csv=root/'mapping.csv')
            raw = path.read_bytes()
            commands = list(command_times(raw))
            observed = [(e.vgmticks, raw[e.address+1], raw[e.address+2]) for e in commands if e.command == 0x54]
            expected = [(projected_samples(w.mdx_tick), w.register, w.data) for w in performance.scheduled_writes()]
            self.assertEqual(observed, expected)
            self.assertEqual(commands[-1].vgmticks, projected_samples(performance.end_tick))
            with (root/'mapping.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                event = commands[int(row['target_source_event_id'])]
                self.assertEqual(event.address, int(row['target_command_address']))
                self.assertEqual(event.vgmticks, int(row['target_vgmticks']))
                self.assertEqual(row['state_origin'], 'projected_opm')

    def test_canonical_pipeline_and_baseline_are_separate_and_traceable(self):
        source = ROOT/'tests/fixtures/public/psg/short_pulses/short_pulses.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mml, baseline = convert(source, root/'structured')
            raw_mml, raw_plan = convert(source, root/'registers', notation='registers')
            self.assertEqual(baseline.writes, raw_plan.writes)
            self.assertEqual(baseline.rows, raw_plan.rows)
            self.assertIn('/* Track F */', mml.read_text())
            self.assertIn('@0 = {', mml.read_text())
            self.assertNotEqual(mml.read_text(), raw_mml.read_text())
            c = baseline.structured_context
            self.assertEqual(sum(bool(e.rising_mask) for e in c.analysis.events), 4)
            folder = root/'structured/projected_opm'
            provenance = json.loads((folder/'provenance.json').read_text())
            self.assertEqual(provenance['opm_pipeline'], 'opm_conversion.convert')
            self.assertLessEqual(provenance['max_abs_source_to_final_error_samples'], 12)
            with (folder/'short_pulses.opm.segments.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(all(r['state_origin'] == 'projected_opm' for r in rows))

    def test_validator_rejects_extra_same_mask_key_command(self):
        source = ROOT/'tests/fixtures/public/psg/short_pulses/short_pulses.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            _, baseline = convert(source, tmp)
            c = baseline.structured_context
            self.assertTrue(compare_performance(c, c.analysis, initialization=[])['passed'])
            on = next(e for e in c.analysis.events if e.rising_mask)
            index = c.analysis.events.index(on)
            duplicate = replace(on, rising_mask=0, falling_mask=0)
            actual = replace(c.analysis, events=c.analysis.events[:index+1]+(duplicate,)+c.analysis.events[index+1:])
            self.assertFalse(compare_performance(c, actual, initialization=[])['key_commands_match'])

    def test_validator_rejects_wrong_state_at_key_even_if_boundary_recovers(self):
        source = ROOT/'tests/fixtures/public/psg/short_pulses/short_pulses.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            _, baseline = convert(source, tmp)
            c = baseline.structured_context
            events = list(c.analysis.events)
            index = next(i for i,e in enumerate(events) if e.rising_mask)
            on = events[index]
            events[index] = replace(on, state=replace(on.state, kc_raw=0))
            events.insert(index+1, replace(on, source_event_id=max(e.source_event_id for e in events)+1,
                          register=0x28+on.ch, data=on.state.kc_raw, rising_mask=0, falling_mask=0))
            actual = replace(c.analysis, events=tuple(events))
            report = compare_performance(c, actual, initialization=[])
            self.assertTrue(report['key_commands_match'])
            self.assertEqual(report['known_state_mismatches'], 0)
            self.assertGreater(report['key_point_state_mismatches'], 0)
            self.assertFalse(report['passed'])

    def test_frontend_supports_register_baseline_and_no_loops(self):
        source = ROOT/'tests/fixtures/public/psg/short_pulses/short_pulses.vgm'
        with tempfile.TemporaryDirectory() as tmp:
            for flags in (['--notation','registers'], ['--no-loops']):
                out = Path(tmp)/flags[-1]
                run = subprocess.run([sys.executable,str(ROOT/'vgm2mml.py'),str(source),
                                      '--target','opm','--outdir',str(out),*flags],capture_output=True,text=True)
                self.assertEqual(run.returncode,0,run.stderr)
                self.assertEqual([p.name for p in out.iterdir()], ['short_pulses.mdx.mml'])


if __name__ == '__main__':
    unittest.main()
