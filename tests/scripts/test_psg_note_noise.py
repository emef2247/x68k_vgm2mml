"""Small authored source-unit/noise checks; no compiler/private regression."""
from dataclasses import replace
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/scripts')]
from chip_segments import SccAnalysis
from psg_note_units import interpret
from psg_scc_opm import project
from opm_performance import build_performance
from opm_target_state import build_target_trajectory
from test_opm_performance import psg
import test_opna_ssg_opm as ssg_helpers
from opna_ssg_opm import allocate,project as project_ssg


def baseline(rows):
    return project(rows,SccAnalysis({},()),psg_clock=1789772,scc_clock=0,
                   end_vgmticks=max(s.vgmticks_end for items in rows.values() for s in items),psg_model='fm')


class PsgNoteNoiseTests(unittest.TestCase):
    def test_decay_rise_and_zero_time_pitch_use_shared_notes(self):
        rows=[psg(vgmticks=0,vgmticks_end=1000),
              psg(volume=10,vgmticks=1000,vgmticks_end=2000),
              psg(volume=12,vgmticks=2000,vgmticks_end=3000),
              psg(ev_type='fCA',tone_period=180,vgmticks=3000,vgmticks_end=3000),
              psg(tone_period=180,vgmticks=3000,vgmticks_end=4000)]
        source=copy.deepcopy(rows);notes=interpret({0:rows})[0]
        self.assertEqual([n.length for n in notes],[2000,1000,1000])
        self.assertEqual(notes[0].runs,[(15,1000),(10,1000)])
        self.assertEqual(rows,source)
        perf=build_performance(baseline({0:rows}))
        self.assertEqual([(w.vgmticks,bool(w.data&120)) for w in perf.writes if w.inferred_key],
            [(0,True),(2000,False),(2000,True),(3000,False),(3000,True),(4000,False)])
        self.assertFalse(any(w.inferred_key and w.source_row==3 for w in perf.writes))

    def test_replayed_held_noise_has_no_boundary_attack_or_eof_disable(self):
        from psg_scc_conversion import convert
        from test_psg_force import authored_psg
        import struct
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);src=root/'LOOP.vgm';raw=authored_psg()[:0x100]
            commands=bytes.fromhex('a0 00 c8 a0 01 00 a0 06 0a a0 07 37 a0 08 0f')
            loop=0x100+len(commands)
            commands+=bytes.fromhex('61 e8 03 a0 08 0a 61 e8 03 66')
            raw.extend(commands);struct.pack_into('<I',raw,4,len(raw)-4)
            struct.pack_into('<I',raw,0x1c,loop-0x1c)
            src.write_bytes(raw)
            mml,plan=convert(src,root/'out',normalize_lengths=False)
            perf=plan.structured_context.performance
            self.assertFalse(any(w.inferred_key and w.vgmticks==2000 for w in perf.writes))
            self.assertFalse(any(w.reason.startswith('terminal ') for w in perf.writes))
            self.assertEqual(sum(w.inferred_key for w in perf.writes),1)
            self.assertIn(' L',mml.read_text())

    def test_final_state_is_interpreted_only_to_observed_vgm_end(self):
        source={0:[psg(vgmticks_end=1000),psg(volume=0,vgmticks=1000,vgmticks_end=1000)]}
        plan=project(source,SccAnalysis({},()),psg_clock=1789772,scc_clock=0,end_vgmticks=2000,psg_model='fm')
        self.assertEqual(source[0][-1].vgmticks_end,1000)
        self.assertEqual(plan.source_music[0][-1].length,1000)
        self.assertTrue(plan.source_music[0][-1].rest)
        keys=[w for w in build_performance(plan).writes if w.inferred_key]
        self.assertEqual([w.vgmticks for w in keys],[0,1000])
        self.assertEqual(plan.settings['source_interval_extensions'][0]['interpreted_end'],2000)

    def test_noise_owner_permutation_and_tone_restore(self):
        rows=[psg(vgmticks=0,vgmticks_end=1000),
              psg(mode=2,noise_period=10,vgmticks=1000,vgmticks_end=2000),
              psg(vgmticks=2000,vgmticks_end=3000)]
        plan=baseline({0:rows,2:[psg(ch=2,vgmticks=0,vgmticks_end=3000)]})
        self.assertEqual(plan.settings['psg_channel_map'],{0:7,1:6,2:5})
        self.assertTrue(all(w.target_ch==7 for w in plan.writes if w.register==15))
        noise=plan.rows[1]
        self.assertEqual(noise['voice_model'],'noise-only')
        self.assertGreater(noise['noise_source_rate_hz'],0)
        perf=build_performance(plan)
        self.assertTrue(all(w.target_ch==7 for w in perf.writes if w.source_ch==0))
        trajectory=build_target_trajectory(perf.scheduled_writes(),end_tick=perf.end_tick,source_end_vgmticks=3000)
        state=next(e.state for e in reversed(trajectory.events) if e.target_ch==7 and e.vgmticks==2000)
        self.assertEqual(state.noise_enabled,0)
        self.assertEqual([o.mul for o in state.operators],[2,1,1,1])
        self.assertEqual(state.operators[3].tl,127)
        loop=build_performance(plan,terminate=False)
        self.assertFalse(any(w.reason.startswith('terminal ') for w in loop.writes))

    def test_zero_time_noise_does_not_steal_the_positive_noise_owner(self):
        plan=baseline({0:[psg(mode=2,vgmticks_end=0),psg(volume=0)],
                       1:[psg(ch=1,mode=2,noise_period=10)]})
        self.assertEqual(plan.settings['noise_source_ch'],1)
        self.assertFalse(plan.rows[0]['target_audible'])
        self.assertTrue(plan.rows[-1]['target_audible'])
        self.assertEqual(plan.rows[-1]['frequency_hz'],'')
        self.assertEqual(plan.rows[-1]['target_frequency_hz'],'')

    def test_noise_conflicts_and_mixed_mode_are_reported(self):
        source={ch:[psg(ch=ch,mode=2,noise_period=10)] for ch in (0,1)}
        with self.assertRaisesRegex(ValueError,'noise/hardware EG'):baseline(source)
        plan=project(source,SccAnalysis({},()),psg_clock=1789772,scc_clock=0,
                     end_vgmticks=441,psg_model='fm',force=True)
        self.assertEqual(plan.settings['forced_omissions'][0]['reason'],'psg_noise_owner_conflict')
        self.assertEqual([r['target_audible'] for r in plan.rows],[True,False])
        with self.assertRaisesRegex(ValueError,'noise/hardware EG'):baseline({0:[psg(mode=3)]})

    def test_ssg_reserves_actual7_and_never_remaps_global_noise_register(self):
        fm,ssg=ssg_helpers.OpnaSsgOpmTests().analyze(ssg_helpers.body(range(6),mixer=0x31))
        _,mapping,_=allocate(fm,ssg)
        self.assertEqual(mapping[0],7)
        rows,_,_=project_ssg(ssg,{0:7})
        self.assertTrue(any(r['target_register']==15 and r['target_data']&128 for r in rows))
        with self.assertRaisesRegex(ValueError,'noise/hardware EG'):project_ssg(ssg,{0:3})
        rows,plan,_=project_ssg(ssg,{0:3},force=True)
        self.assertFalse(any(r['target_register']==15 for r in rows))
        self.assertTrue(plan.settings['forced_omissions'])

    def test_music_pass_and_canonical_mml_keep_noise_controls(self):
        from psg_scc_conversion import convert
        from test_psg_force import authored_psg
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);src=root/'NOISE.vgm'
            raw=authored_psg()
            # Retain finite authored tone/noise controls, remove later EG example.
            position=raw.index(bytes.fromhex('a0 0b d0'),0x100)
            raw=raw[:position]+bytes.fromhex('a0 08 00 61 e8 03 66')
            import struct
            struct.pack_into('<I',raw,4,len(raw)-4)
            # noise-only channel0: mixer tone disabled/noise enabled.
            position=raw.index(bytes.fromhex('a0 07 36'),0x100);raw[position+2]=0x37
            src.write_bytes(raw)
            mml,plan=convert(src,root/'out',song_loop=False,normalize_lengths=False)
            self.assertTrue((root/'out/NOISE.psg.music.csv').is_file())
            self.assertIn('y15,',mml.read_text())
            self.assertTrue(any(r['voice_model']=='noise-only' for r in plan.rows))


if __name__=='__main__':unittest.main()
