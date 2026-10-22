"""Authored reusable bank allocation and typed multi-track assembly checks."""
from dataclasses import dataclass, replace
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts')]
from generate_pcm_fixtures import playback, vgm
from msm6258 import PcmAnalysis, PcmPlayback, analyze
from pcm_mdx import project, write_pdx, write_mdx, default_generator, validate_extended_layout
from pcm_assessment import ProjectionError
from types import SimpleNamespace


@dataclass(frozen=True)
class BankAnalysis(PcmAnalysis):
    parallel_playbacks: bool = True


@dataclass(frozen=True)
class BankPlayback(PcmPlayback):
    source_channel: int = 0
    target_volume: int = 128


class PcmMultitrackTests(unittest.TestCase):
    def source(self, intervals):
        body, _ = playback(bytes(range(32)))
        base = analyze(vgm(body))
        note = base.playbacks[0]
        plays = tuple(BankPlayback(**dict(vars(note), playback_id=i,
                          start_vgmticks=start, end_vgmticks=end, control_event_ids=(),
                          termination='stop', source_channel=i,
                          target_volume=128+i, pan=i%4))
                      for i, (start, end) in enumerate(intervals))
        return BankAnalysis(**dict(vars(base), playbacks=plays, controls=(),
                                  source_end_vgmticks=max(e for _, e in intervals)+1000))

    def test_overlap_reuses_bank_and_freed_lane_and_retains_source(self):
        source = self.source([(0, 2000), (500, 2500), (2000, 3000)])
        before = source
        plan = project(source, stem='bank')
        self.assertEqual(source, before)
        self.assertEqual(len(plan.bindings), 1)
        by_id = {r['playback_id']:r for r in plan.rows}
        self.assertEqual([by_id[i]['mdx_track'] for i in range(3)], ['P','Q','P'])
        self.assertEqual([by_id[i]['source_channel'] for i in range(3)], [0,1,2])
        self.assertEqual({r['slot'] for r in plan.rows}, {0})
        self.assertIn('@v126', next(u.command for u in plan.units if u.track=='Q' and u.kind=='pcm_note'))
        for track in ('P','Q'):
            self.assertEqual(max(u.end_tick for u in plan.units if u.track==track),
                             max(u.end_tick for u in plan.units))
        with tempfile.TemporaryDirectory() as temp:
            text = plan.write_manifest(temp,'bank').read_text()
            self.assertIn('track\tQ\t\n', text)

    def test_voice_overflow_never_steals_and_force_omits_whole_new_gate(self):
        source = self.source([(0,3000)]*9+[(3000,4000)])
        samples=tuple(replace(source.samples[0],sample_id=i,encoded_bytes=bytes([i])*32)
                      for i in range(9))
        source=replace(source,samples=samples,playbacks=tuple(
            replace(p,sample_id=i if i<9 else 0) for i,p in enumerate(source.playbacks)))
        with self.assertRaises(ProjectionError) as error:
            project(source,stem='over')
        self.assertIn('eight simultaneous',str(error.exception))
        plan=project(source,stem='over',force=True)
        self.assertEqual([r['playback_id'] for r in plan.omitted_playbacks],[8])
        self.assertEqual({r['playback_id'] for r in plan.rows},set(range(8))|{9})
        self.assertEqual([b.sample_id for b in plan.bindings],list(range(8)))
        self.assertEqual(plan.pcm_payload_bytes,8*32)
        self.assertEqual(len(source.samples),9)
        self.assertEqual({u.track for u in plan.units},set('PQRSTUVW'))
        self.assertTrue(any(r['code']=='force_pcm_voice_capacity' for r in plan.assessment.items))

    def test_voice_omission_does_not_consume_last_bank_slot(self):
        intervals=[(i*2000,i*2000+1000) for i in range(87)]
        intervals += [(174000,177000)]*9 + [(177000,178000)]
        source=self.source(intervals)
        source=replace(source,samples=tuple(
            replace(source.samples[0],sample_id=i,encoded_bytes=bytes([i])*32)
            for i in range(97)),playbacks=tuple(
            replace(p,sample_id=i) for i,p in enumerate(source.playbacks)))
        plan=project(source,stem='lastslot',force=True)
        self.assertEqual([b.sample_id for b in plan.bindings],list(range(95))+[96])
        self.assertEqual(len(plan.bindings),96)
        self.assertEqual([r['playback_id'] for r in plan.omitted_playbacks],[95])
        self.assertIn(96,{r['playback_id'] for r in plan.rows})
        self.assertNotIn(95,{r['playback_id'] for r in plan.force_capacity.rows})
        self.assertFalse(any(r['action']=='omit' for r in plan.force_capacity.rows))
        self.assertEqual(len(source.samples),97)

    def test_capacity_omission_releases_lane_for_same_tick_next_gate(self):
        source=self.source([(0,3000)]*9)
        source=replace(source,samples=tuple(
            replace(source.samples[0],sample_id=i,
                    encoded_bytes=bytes([i])*(65536 if i==7 else 32))
            for i in range(9)),playbacks=tuple(
            replace(p,sample_id=i) for i,p in enumerate(source.playbacks)))
        plan=project(source,stem='reclaim',force=True)
        self.assertEqual([b.sample_id for b in plan.bindings],list(range(7))+[8])
        self.assertEqual(next(r['mdx_track'] for r in plan.rows if r['playback_id']==8),'W')
        self.assertEqual(plan.force_capacity.omitted_playback_ids,{7})
        self.assertFalse(plan.omitted_playbacks)
        self.assertFalse(any(r['code']=='force_pcm_voice_capacity' for r in plan.assessment.items))

    def test_all_capacity_omitted_has_no_active_pcm_tracks(self):
        source=self.source([(0,3000)])
        source=replace(source,samples=(replace(source.samples[0],encoded_bytes=b'x'*65536),))
        plan=project(source,stem='empty',force=True)
        self.assertFalse(plan.bindings)
        self.assertFalse(plan.rows)
        self.assertEqual(plan.assessment.active_pcm_tracks,[])

    def test_allocation_uses_final_tick_intervals_and_releases_before_attack(self):
        source=self.source([(0,1001),(1000,2000)])
        plan=project(source,stem='rounded',tick_mapper=lambda t:t//10)
        self.assertEqual([r['mdx_track'] for r in plan.rows],['P','P'])
        self.assertEqual([(r['start_mdx_tick'],r['end_mdx_tick']) for r in plan.rows],
                         [(0,100),(100,200)])
        self.assertEqual([(p.start_vgmticks,p.end_vgmticks) for p in source.playbacks],
                         [(0,1001),(1000,2000)])
        source=self.source([(0,1)])
        with self.assertRaises(ProjectionError) as error:
            project(source,stem='collapse',tick_mapper=lambda t:t//10)
        self.assertIn('collapses',str(error.exception))

    def test_force_voice_omission_cannot_hide_missing_source_bytes(self):
        source=self.source([(0,3000)]*9)
        source=replace(source,playbacks=source.playbacks[:8]+(
            replace(source.playbacks[8],sample_id=999),))
        with self.assertRaises(ProjectionError):
            project(source,stem='invalid',force=True)

    def test_force_short_omission_remains_inspectable(self):
        source=self.source([(0,200),(500,1500)])
        plan=project(source,stem='short',force=True,omit_playback_ids=(0,))
        self.assertEqual([r['playback_id'] for r in plan.omitted_playbacks],[0])
        self.assertEqual([r['playback_id'] for r in plan.rows],[1])

    def test_loop_marker_on_every_allocated_track_uses_shared_tick_mapper(self):
        source=self.source([(0,1000),(500,1000),(2000,3000),(2500,3500)])
        plan=project(source,stem='loop',song_loop_start=1500,
                     tick_mapper=lambda t:t//10)
        for track in ('P','Q'):
            markers=[u for u in plan.units if u.track==track and u.kind=='song_loop']
            self.assertEqual([u.start_tick for u in markers],[150])
        self.assertEqual({r['start_mdx_tick'] for r in plan.rows},{0,50,200,250})

    @unittest.skipUnless(default_generator().is_file(),'built helper required')
    def test_typed_helper_builds_shared_bank_and_two_active_tracks(self):
        source=self.source([(0,2000),(500,2500)])
        plan=project(source,stem='typed')
        end=max(u.end_tick for u in plan.units)
        fm=SimpleNamespace(text=f'A @t255 r%{end}\n')
        # Keep FM duration within the target syntax limit.
        fm.text='A @t255 '+ ' '.join('r%'+str(min(128,end-i)) for i in range(0,end,128))+'\n'
        with tempfile.TemporaryDirectory() as temp:
            write_pdx(plan,source,temp,'typed')
            path=write_mdx(plan,fm,temp,'typed')
            validate_extended_layout(path.read_bytes(),active_tracks=('P','Q'))
            with self.assertRaises(ValueError):
                validate_extended_layout(path.read_bytes())
