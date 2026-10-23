"""Authored DCSG source, musical-unit and target-allocation checks."""
from dataclasses import asdict
import csv
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests' / 'scripts')]
from dcsg import analyze, dump_analysis
from dcsg_opm import console_lines, dump_projection, musical_units, project
from opm_target_vgm import write_target_vgm
from vgm_timing import command_times


def vgm(commands, *, dual=False, clock=4000000, flags=5, loop=None):
    raw = bytearray(0x100)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 12, clock | (0x40000000 if dual else 0))
    struct.pack_into('<HBB', raw, 0x28, 3, 15, flags)
    struct.pack_into('<I', raw, 0x34, 0x100 - 0x34)
    if loop is not None:
        struct.pack_into('<I', raw, 0x1c, 0x100 + loop - 0x1c)
    raw.extend(commands + b'\x66')
    struct.pack_into('<I', raw, 4, len(raw) - 4)
    return bytes(raw)


def write(value, instance=0):
    return bytes((0x30 if instance else 0x50, value))


def tone(ch, period, instance=0):
    return write(0x80 | ch << 5 | period & 15, instance) + write(period >> 4, instance)


def level(ch, attenuation=0, instance=0):
    return write(0x90 | ch << 5 | attenuation, instance)


def noise(control=4, instance=0):
    return write(0xe0 | control, instance) + level(3, 0, instance)


def wait(samples=4410):
    return b'\x61' + struct.pack('<H', samples)


class DcsgOpmTests(unittest.TestCase):
    def test_native_independent_latches_and_exact_source_segments(self):
        raw = vgm(tone(0, 250) + level(0, 1) + tone(1, 500, 1)
                  + level(1, 2, 1) + write(4) + wait(16), dual=True)
        result = analyze(raw)
        source = [s for s in result.segments if s.audible]
        self.assertEqual([(s.chip_instance, s.ch, s.period, s.attenuation)
                          for s in source], [(0, 0, 250, 4), (1, 1, 500, 2)])
        self.assertEqual(result.end_sample, 16)
        self.assertEqual(source[0].frequency_hz, 500.)
        before = asdict(result)
        plan = project(result)
        self.assertEqual(asdict(result), before)
        self.assertEqual({w.target_ch for w in plan.writes}, {0, 4})
        self.assertEqual({r['source_row'] for r in plan.rows if r['native_channel'] < 3},
                         {s.segment_id for s in result.segments if s.ch < 3})

    def test_six_simultaneous_tones_preserve_independent_part_mapping(self):
        commands = b''.join(tone(ch, 200 + 100 * ch, chip) + level(ch, ch, chip)
                            for chip in range(2) for ch in range(3)) + wait()
        plan = project(analyze(vgm(commands, dual=True)))
        attacks = [w for w in plan.writes if w.inferred_key and w.data & 0x78]
        self.assertEqual({w.target_ch for w in attacks}, set(range(6)))
        self.assertEqual(len(attacks), 6)
        self.assertFalse(plan.settings['forced_omissions'])

    def test_decay_groups_volume_runs_before_target_filtering(self):
        commands = tone(0, 250) + level(0, 0) + wait(735) + level(0, 2) + wait(735)
        commands += level(0, 4) + wait(735) + level(0, 15) + wait(735)
        source = analyze(vgm(commands))
        _, notes, _ = musical_units(source)
        self.assertEqual(notes[0][0].runs, [(15, 735), (13, 735), (11, 735)])
        plan = project(source)
        self.assertEqual(sum(w.inferred_key and bool(w.data & 0x78) for w in plan.writes), 1)
        self.assertEqual([r['inferred_transition'] for r in plan.rows if r['source_ch'] == 0],
                         ['attack', 'continuation', 'continuation', 'release'])
        levels = [w.data for w in plan.writes if w.register == 0x60 and 'attenuation' in w.reason]
        self.assertEqual(levels, sorted(levels))

    def test_volume_rise_uses_shared_source_attack_rule(self):
        commands = tone(0, 250) + level(0, 3) + wait() + level(0, 0) + wait()
        plan = project(analyze(vgm(commands)))
        self.assertEqual(sum(w.inferred_key and bool(w.data & 0x78) for w in plan.writes), 2)

    def test_stereo_is_retained_in_target_channel_routing(self):
        commands = tone(0, 250) + level(0) + b'\x4f\x10' + wait()
        plan = project(analyze(vgm(commands, flags=1)))
        self.assertIn((0x20, 0x87), [(w.register, w.data) for w in plan.writes])

    def test_white_noise_has_explicit_rate_and_lfsr_approximation(self):
        plan = project(analyze(vgm(noise(4) + wait())))
        approximation = plan.settings['approximations'][0]
        self.assertEqual(approximation['source_rate_hz'], 7812.5)
        self.assertEqual(approximation['action'], 'approximate_noise')
        self.assertIn('LFSR', approximation['reason'])
        self.assertEqual({w.target_ch for w in plan.writes}, {7})

    def test_alternating_dual_noise_reuses_h_without_omission(self):
        commands = noise(4, 0) + level(3, 15, 1) + wait(735)
        commands += level(3, 15, 0) + noise(5, 1) + wait(735)
        plan = project(analyze(vgm(commands, dual=True)))
        self.assertFalse(plan.settings['forced_omissions'])
        attacks = [w for w in plan.writes if w.inferred_key and w.data & 0x78]
        self.assertEqual([(w.vgmticks, w.source_ch) for w in attacks], [(0, 3), (735, 7)])
        at_switch = [w for w in plan.writes if w.vgmticks == 735]
        off = next(i for i, w in enumerate(at_switch) if w.register == 8 and not w.data & 0x78)
        control = next(i for i, w in enumerate(at_switch) if w.register == 15)
        on = next(i for i, w in enumerate(at_switch) if w.register == 8 and w.data & 0x78)
        self.assertLess(off, control)
        self.assertLess(control, on)

    def test_overlapping_dual_noise_force_omits_overlap_then_resumes(self):
        commands = tone(2, 400, 1) + level(2, 0, 1) + noise(4, 0)
        commands += noise(5, 1) + wait(735) + level(3, 15, 0) + wait(735)
        source = analyze(vgm(commands, dual=True))
        with self.assertRaisesRegex(ValueError, 'single_noise_owner'):
            project(source)
        plan = project(source, force=True)
        omitted = plan.settings['forced_omissions']
        self.assertEqual([(r['source_ch'], r['start_vgmticks'], r['end_vgmticks'])
                          for r in omitted], [(7, 0, 735)])
        self.assertTrue(any(w.source_ch == 7 and w.vgmticks == 735 and w.inferred_key
                            and w.data & 0x78 for w in plan.writes))
        self.assertTrue(any(w.target_ch == 5 and w.inferred_key and w.data & 0x78 for w in plan.writes))

    def test_periodic_and_linked_noise_strict_or_force_interval_loss(self):
        for control, reason in ((0, 'periodic_noise'), (7, 'tone2_linked_noise')):
            with self.subTest(control=control):
                source = analyze(vgm(tone(2, 250) + level(2) + noise(control) + wait()))
                with self.assertRaisesRegex(ValueError, reason):
                    project(source)
                plan = project(source, force=True)
                self.assertEqual(len(plan.settings['forced_omissions']), 1)
                self.assertTrue(any(w.target_ch == 2 for w in plan.writes))
                self.assertFalse(any(w.target_ch == 7 for w in plan.writes))

    def test_pitch_policy_and_unknown_period_are_explicit(self):
        source = analyze(vgm(tone(0, 1) + level(0) + wait()))
        with self.assertRaisesRegex(ValueError, 'outside OPM'):
            project(source, pitch_policy='error')
        self.assertEqual(project(source).settings['approximations'][0]['action'], 'clamp_pitch')
        unknown = analyze(vgm(level(0) + wait()))
        with self.assertRaisesRegex(ValueError, 'unknown_period'):
            project(unknown)
        self.assertTrue(project(unknown, force=True).settings['forced_omissions'])

    def test_loop_replay_retains_native_latch_and_chip_state(self):
        prefix = tone(0, 250, 1)
        body = write(0x92, 1) + wait(735) + write(0x94, 1) + wait(735)
        result = analyze(vgm(prefix + body, dual=True, loop=len(prefix)), loop_count=2)
        self.assertEqual(result.end_sample, 2940)
        repeated = [w for w in result.writes if w.loop_iteration == 1]
        self.assertTrue(repeated)
        self.assertTrue(all(w.chip_instance == 1 for w in repeated))
        self.assertEqual([s.period for s in result.segments if s.chip_instance == 1 and s.ch == 0], [250] * 4)

    def test_unknown_latch_strict_rejects_and_force_exposes_unknown_prefix(self):
        raw = vgm(write(1) + wait(735) + tone(0, 250) + level(0) + wait(735))
        source = analyze(raw)
        before = asdict(source)
        with self.assertRaisesRegex(ValueError, 'data_before_known_latch'):
            project(source)
        plan = project(source, force=True)
        self.assertEqual(asdict(source), before)
        omitted = plan.settings['forced_omissions']
        writes = [r for r in omitted if r['count_kind'] == 'write']
        self.assertEqual(len(writes), 1)
        self.assertEqual((writes[0]['native_event_id'], writes[0]['source_event_id'],
                          writes[0]['command'], writes[0]['register'], writes[0]['known_mask']),
                         (0, 0, 0x50, None, 0))
        unknown = [r for r in omitted if r['action'] == 'omit_unknown_source_state']
        self.assertEqual([(r['source_ch'], r['end_vgmticks']) for r in unknown],
                         [(0, 735), (1, 1470), (2, 1470), (3, 1470)])
        attacks = [w for w in plan.writes if w.inferred_key and w.data & 0x78]
        self.assertEqual([(w.source_ch, w.vgmticks) for w in attacks], [(0, 735)])
        self.assertIn('4 omitted intervals / 1 omitted writes', console_lines(plan)[0])
        with tempfile.TemporaryDirectory() as folder:
            report = json.loads(dump_projection(plan, folder, 'unknown').read_text())
            with Path(report['paths']['forced_omissions']).open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 5)

    def test_unknown_latch_same_time_initialization_still_reports_write(self):
        commands = write(1)
        for ch in range(3):
            commands += tone(ch, 250) + level(ch, 15)
        commands += write(0xe4) + level(3, 15) + wait(735)
        source = analyze(vgm(commands))
        with self.assertRaisesRegex(ValueError, 'data_before_known_latch'):
            project(source)
        plan = project(source, force=True)
        self.assertEqual([r['action'] for r in plan.settings['forced_omissions']],
                         ['omit_uninterpreted_write'])

    def test_stereo_write_on_mono_variant_is_not_silently_discarded(self):
        source = analyze(vgm(tone(0, 250) + level(0) + bytes((0x4f, 0x10)) + wait(), flags=5))
        with self.assertRaisesRegex(ValueError, 'stereo_write_on_mono_variant'):
            project(source)
        plan = project(source, force=True)
        omitted = plan.settings['forced_omissions']
        self.assertEqual(len(omitted), 1)
        self.assertEqual(omitted[0]['action'], 'omit_uninterpreted_write')
        self.assertEqual(omitted[0]['command'], 0x4f)
        self.assertTrue(any(w.register == 0x20 and w.data == 0xc7 for w in plan.writes))

    def test_target_serialization_and_dumps_are_inspectable(self):
        source = analyze(vgm(tone(0, 250) + level(0) + noise(4) + wait(4410)))
        plan = project(source)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            dump_analysis(source, folder, 'authored')
            path = dump_projection(plan, folder, 'authored')
            report = json.loads(path.read_text())
            self.assertEqual(report['target_clock'], 4000000)
            self.assertTrue(report['approximations'])
            with (folder / 'authored.opm_performance.csv').open() as stream:
                self.assertTrue(list(csv.DictReader(stream)))
            target = write_target_vgm(plan, folder / 'target.vgm', exact_source_times=True)
            self.assertEqual(sum(e.wait_samples for e in command_times(target.read_bytes())), 4410)
            self.assertTrue(console_lines(report))


if __name__ == '__main__':
    unittest.main()
