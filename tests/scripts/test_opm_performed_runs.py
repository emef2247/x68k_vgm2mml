"""Exact performed-run grouping without short-state loss or source mutation."""
from pathlib import Path
import csv
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts')]
from opm_mdx import project_segments
from opm_mdx_music import build_music
from opm_performed_runs import HeldRun, coalesce
from test_opm_mdx import analyze, wait, write
from test_opm_reader import vgm


def setup():
    result = write(0x20, 0xc7) + write(0x28, 0x40) + write(0x30, 0) + write(0x38, 0)
    for slot in range(4):
        for base, value in ((0x40, 1), (0x60, 20), (0x80, 31),
                            (0xa0, 0), (0xc0, 0), (0xe0, 15)):
            result += write(base + slot * 8, value)
    return result


def attack(partitioned=False, terminal=b''):
    middle = write(0x30, 8) + write(0x30, 0) if partitioned else b''
    return (write(8, 120) + wait(226) + middle + wait(226)
            + terminal + write(8, 0) + wait(113))


class HeldRunTests(unittest.TestCase):
    def test_equal_adjacent_states_preserve_duration_ids_and_membership(self):
        runs = (HeldRun(10, 15, 'same', ('initial',), ('initial',), (1,)),
                HeldRun(15, 19, 'same', source_event_ids=(2, 3)),
                HeldRun(19, 25, 'same', source_event_ids=(4,)))
        before = tuple(runs)
        grouped, membership = coalesce(runs)
        self.assertEqual(grouped, (HeldRun(10, 25, 'same', ('initial',), ('initial',), (1, 2, 3, 4)),))
        self.assertEqual(membership, ((0, False), (0, True), (0, True)))
        self.assertEqual(sum(r.end_tick-r.start_tick for r in runs),
                         sum(r.end_tick-r.start_tick for r in grouped))
        self.assertEqual(runs, before)

    def test_gap_state_change_and_ordered_actions_are_barriers(self):
        for following in (HeldRun(6, 9, 'same'), HeldRun(5, 9, 'different'),
                          HeldRun(5, 9, 'same', commands=('y1,0',)),
                          HeldRun(5, 9, 'same', actions=(('register', 1, 0),))):
            with self.subTest(following=following):
                runs = (HeldRun(0, 5, 'same'), following)
                self.assertEqual(coalesce(runs), (runs, ((0, False), (1, False))))

    def test_short_different_state_is_preserved_even_for_one_tick(self):
        runs = (HeldRun(0, 100, 'pitch0'), HeldRun(100, 101, 'pitch1'),
                HeldRun(101, 201, 'pitch0'))
        self.assertEqual(coalesce(runs)[0], runs)

    def test_nonpositive_runs_are_rejected(self):
        for end in (4, 5):
            with self.subTest(end=end), self.assertRaisesRegex(ValueError, 'positive duration'):
                coalesce((HeldRun(5, end, 'state'),))


class PerformedMusicTests(unittest.TestCase):
    def build(self, commands, root, **kwargs):
        path = root / 'authored.vgm'
        path.write_bytes(vgm(setup() + commands))
        analysis = analyze(path, root / 'trace')
        before = tuple(analysis.segments)
        projection = project_segments(before, end_vgmticks=analysis.source_end_vgmticks)
        music = build_music(projection, before, **kwargs)
        self.assertEqual(analysis.segments, before)
        self.assertEqual(sorted(event for units in music.units.values()
                                for unit in units for event in unit.source_event_ids),
                         sorted(w.source_event_id for w in projection.writes))
        return analysis, projection, music

    def test_equivalent_positive_states_share_loop_key_but_keep_native_trajectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            analysis, _, music = self.build(wait(113) + attack() + attack(True) + attack() + attack(True), Path(tmp))
            notes = [u for u in music.units['A'] if u.kind == 'note']
            self.assertEqual(len(notes), 4)
            self.assertEqual(len({u.key for u in notes}), 1)
            self.assertNotEqual(notes[0].trajectory, notes[1].trajectory)
            self.assertGreater(music.summary()['merged_performed_run_count'], 0)
            self.assertGreater(music.summary()['applied_loops'], 0)
            self.assertEqual([e.data for e in analysis.events if e.register == 0x30],
                             [0, 8, 0, 8, 0])
            self.assertEqual(notes[0].command, notes[1].command)

    def test_retrigger_edges_cannot_be_merged_into_one_sustained_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands = (wait(113) + write(8, 120) + wait(226) + write(8, 0)
                        + write(8, 120) + wait(226) + write(8, 0))
            analysis, _, music = self.build(commands, Path(tmp))
            notes = [u for u in music.units['A'] if u.kind == 'note']
            self.assertEqual(len(notes), 2)
            self.assertEqual(notes[0].end_tick, notes[1].start_tick)
            self.assertEqual(sum(bool(e.rising_mask) for e in analysis.events), 2)
            self.assertEqual(music.summary()['merged_performed_run_count'], 0)
            self.assertNotEqual(notes[0].source_event_ids, notes[1].source_event_ids)

    def test_dump_exposes_before_after_runs_with_native_event_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            analysis, _, music = self.build(wait(113) + attack(True), root)
            before = tuple(analysis.segments)
            prefix = root / 'structure'
            music.dump(prefix)
            with Path(str(prefix)+'.performed_runs.csv').open(newline='', encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2)
            self.assertEqual([r['action'] for r in rows], ['retain', 'merge_equal_state'])
            self.assertEqual(rows[0]['target_run_index'], rows[1]['target_run_index'])
            self.assertEqual(rows[0]['target_start_tick'], rows[1]['target_start_tick'])
            self.assertEqual(rows[0]['target_end_tick'], rows[1]['target_end_tick'])
            self.assertTrue(all(json.loads(row['source_event_ids']) for row in rows))
            self.assertEqual(analysis.segments, before)

    def test_operator_pan_and_lfo_raw_controls_remain_barriers(self):
        for register, value in ((0x40, 2), (0x20, 0x47), (0x18, 1)):
            with self.subTest(register=register), tempfile.TemporaryDirectory() as tmp:
                commands = write(8, 120) + wait(226) + write(register, value) + wait(226) + write(8, 0)
                _, _, music = self.build(commands, Path(tmp))
                note = next(u for u in music.units['A'] if u.kind == 'note')
                self.assertIn(f'y{register},{value}', note.command)
                self.assertEqual(music.summary()['merged_performed_run_count'], 0)
                self.assertTrue(any(row['actions'] != '[]' for row in music.run_rows))

    def test_raw_algorithm_controls_invalidate_same_level_volume_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            # The effective final voice/volume matches the preceding held state,
            # but raw algorithm setters intervene before a uniform TL group.
            # The renderer must explicitly restore its channel-volume setter.
            controls = (write(0x20, 0xc4) + write(0x60, 30)
                        + write(0x20, 0xc7) + write(0x60, 20))
            commands = (write(8, 120) + wait(226) + controls
                        + wait(226) + write(8, 0))
            _, _, music = self.build(commands, Path(tmp))
            note = next(u for u in music.units['A'] if u.kind == 'note')
            self.assertEqual(note.command.count('@v107'), 2)
            self.assertIn('y32,196', note.command)
            self.assertIn('y32,199', note.command)
            final_setter = note.command.rindex('@v107')
            self.assertLess(note.command.index('y32,196'), final_setter)
            self.assertLess(note.command.index('y32,199'), final_setter)
            self.assertEqual(music.summary()['merged_performed_run_count'], 0)

    def test_positive_short_pitch_excursion_survives_grouping(self):
        with tempfile.TemporaryDirectory() as tmp:
            commands = (write(8, 120) + wait(226) + write(0x30, 8) + wait(12)
                        + write(0x30, 0) + wait(226) + write(8, 0))
            _, _, music = self.build(commands, Path(tmp))
            self.assertEqual(len(music.run_rows), 3)
            self.assertEqual(music.summary()['merged_performed_run_count'], 0)
            self.assertEqual(sum(row['source_end_tick']-row['source_start_tick'] for row in music.run_rows),
                             next(u.end_tick-u.start_tick for u in music.units['A'] if u.kind == 'note'))
            self.assertIn('D-3', next(u.command for u in music.units['A'] if u.kind == 'note'))

    def test_compiled_grouped_and_ungrouped_notes_replay_identical_state_timeline(self):
        from pcm_mdx import default_generator
        from verify_opm_mdx_roundtrip import generate
        generator = default_generator()
        if not generator.is_file():
            self.skipTest('Built MDX fixture generator is unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = wait(113) + (attack() + attack(True)) * 4
            analysis, projection, grouped = self.build(commands, root)
            def identity(runs):
                return tuple(runs), tuple((i, False) for i in range(len(runs)))
            with patch('opm_mdx_music.coalesce', identity):
                baseline = build_music(projection, analysis.segments)
            replays = []
            sizes = []
            for name, music in (('grouped', grouped), ('baseline', baseline)):
                source = root / (name + '.mml')
                source.write_text(music.text, encoding='utf-8')
                actual = generate(generator, source, root, name)
                # Compare every positive native-state interval on every channel,
                # including ordered controls and releases, after redundant equal
                # partitions have been joined. Register/event counts may differ.
                channels = {}
                for segment in actual.segments:
                    if segment.vgmticks_end <= segment.vgmticks:
                        continue
                    rows = channels.setdefault(segment.ch, [])
                    item = (segment.vgmticks, segment.vgmticks_end, segment.state)
                    if rows and rows[-1][1] == item[0] and rows[-1][2] == item[2]:
                        rows[-1] = (rows[-1][0], item[1], item[2])
                    else:
                        rows.append(item)
                replays.append(channels)
                sizes.append((root / (name + '.mdx')).stat().st_size)
            self.assertEqual(replays[0], replays[1])
            self.assertLess(sizes[0], sizes[1])

    def test_terminal_controls_prevent_false_note_equality(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, music = self.build(attack(terminal=write(0x18, 1))
                                     + write(0x18, 0) + attack(terminal=write(0x18, 2)), Path(tmp))
            notes = [u for u in music.units['A'] if u.kind == 'note']
            self.assertEqual(len(notes), 2)
            self.assertNotEqual(notes[0].key, notes[1].key)
            self.assertIn('y24,1', notes[0].command)
            self.assertIn('y24,2', notes[1].command)


if __name__ == '__main__':
    unittest.main()
