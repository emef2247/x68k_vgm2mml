"""Authored native-clock continuation/curve backport checks."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/scripts')]
from chip_segments import SccAnalysis
from opm_performance import build_performance
from psg_note_units import analyze as analyze_psg
from psg_scc_opm import project
from test_opm_performance import psg
from test_scc_voice_projection import row,SAW


class NativeVolumeCurveTests(unittest.TestCase):
    def test_same_period_release_and_pcm_audit_keep_source_samples(self):
        rows=[psg(vgmticks=0,vgmticks_end=1000),
              psg(volume=10,vgmticks=1000,vgmticks_end=2000),
              psg(ev_type='fCB',volume=8,vgmticks=2000,vgmticks_end=3000),
              psg(volume=0,vgmticks=3000,vgmticks_end=4000)]
        original=tuple(rows)
        curve=analyze_psg({0:rows})
        self.assertEqual(curve.summary()['tick_clock_hz'],44100)
        self.assertEqual(curve.summary()['unchanged_period_joins'],1)
        for output in ('opm','pcm'):
            plan=project({0:rows},SccAnalysis({},()),psg_clock=1789772,scc_clock=0,
                         end_vgmticks=4000,psg_model='fm',psg_output=output)
            self.assertEqual(plan.source_music[0][0].runs,[(15,1000),(10,1000),(8,1000)])
            self.assertEqual(plan.source_music[0][0].length,3000)
            if output=='opm':
                self.assertEqual([w.vgmticks for w in build_performance(plan).writes if w.inferred_key],[0,3000])
            with tempfile.TemporaryDirectory() as directory:
                plan.dump(directory,'AUTH')
                summary=json.loads((Path(directory)/'AUTH.psg.music.volume_curves.json').read_text())
                self.assertEqual(summary['unchanged_period_joins'],1)
                self.assertEqual(summary['tick_clock_hz'],44100)
        self.assertEqual(tuple(rows),original)

    def test_registered_ssg_events_use_curve_interpretation_and_keep_mixer_barrier(self):
        from dataclasses import dataclass, asdict, replace
        from chip_segments import PsgSegment
        @dataclass(frozen=True)
        class Registered(PsgSegment):
            register: int | None = None
        def native(start,stop,volume,register):
            return Registered(**asdict(psg(volume=volume,vgmticks=start,vgmticks_end=stop)),
                              register=register)
        rows=[native(0,1000,3,8),native(1000,2000,10,8),native(2000,3000,6,8)]
        curve=analyze_psg({0:rows})
        self.assertEqual(curve.summary()['accepted_curves'],1)
        self.assertEqual(curve.performance.channels[0][1][0].length,3000)
        rows=[native(0,1000,15,8),native(1000,1000,15,7),
              native(1000,1000,15,0),native(1000,2000,10,8)]
        guarded=analyze_psg({0:rows})
        self.assertEqual(guarded.summary()['unchanged_period_joins'],0)
        extended=analyze_psg({0:[native(0,1000,15,8)]},end=2000)
        original_view=extended.original.source_segments[0][1][0]
        self.assertEqual((original_view.l,original_view.vgmticks_end),(2000,1000))

    def test_pcm_chunk_prefers_complete_group_and_preserves_hard_loop(self):
        from array import array
        from fractions import Fraction
        from psg_playback import PsgPlayback,PlaybackGate
        from pcm_waveform_mdx import project as package
        end=400000
        native=PsgPlayback(Fraction(44100),end,array('h',[1000,1000])*end,
            (PlaybackGate(0,Fraction(0),Fraction(end),0,None,(0,),'source_end'),),(),{})
        groups=[dict(group_id='0:0',start=0,end=300000),
                dict(group_id='0:1',start=300000,end=end)]
        encoder=lambda values:(bytes((len(list(values))+1)//2),0)
        default=package(native,source_raw=b'authored',encoder=encoder)
        grouped=package(native,source_raw=b'authored',encoder=encoder,preferred_groups=groups)
        self.assertEqual(default.chunks[0][1],352800)
        self.assertEqual(grouped.chunks[0][1],300000)
        self.assertEqual(grouped.packaging_boundaries[0]['reason'],'complete_interpreted_group')
        silent_channel=dict(group_id='1:0',start=0,end=end,rest=True)
        with_rest=package(native,source_raw=b'authored',encoder=encoder,
                          preferred_groups=[*groups,silent_channel])
        self.assertEqual(with_rest.chunks,grouped.chunks)
        self.assertIn(silent_channel,with_rest.preferred_groups)
        looped=package(native,source_raw=b'authored',encoder=encoder,
                       preferred_groups=groups,loop_start=320000)
        self.assertEqual(looped.chunks[0][1],320000)
        self.assertEqual(looped.packaging_boundaries[0]['reason'],'span_or_loop_end')

    def test_complete_rise_decay_precedes_scc_structure(self):
        rows=[row(0,1000,3),row(1000,2000,10),row(2000,3000,6),row(3000,4000,0)]
        plan=project({},SccAnalysis({0:rows},(SAW,)),psg_clock=0,scc_clock=1789772,
                     end_vgmticks=4000)
        self.assertEqual(plan.scc_music[0][0].runs,[(3,1000),(10,1000),(6,1000)])
        self.assertEqual(plan.scc_music[0][0].segment_indices,[0,1,2])
        self.assertEqual([w.vgmticks for w in build_performance(plan).writes if w.inferred_key],[0,3000])
        with tempfile.TemporaryDirectory() as directory:
            plan.dump(directory,'AUTH')
            summary=json.loads((Path(directory)/'AUTH.scc.music.volume_curves.json').read_text())
            self.assertEqual(summary['accepted_curves'],1)
            with (Path(directory)/'AUTH.scc.music.csv').open() as stream:
                notes=list(csv.DictReader(stream))
            self.assertEqual(json.loads(notes[0]['source_rows']),[0,1,2])
            self.assertTrue((Path(directory)/'AUTH.scc.music.ch0.structure.csv').exists())


if __name__=='__main__':unittest.main()
