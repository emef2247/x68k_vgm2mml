"""Configurable shared short-state policy and source-preserving OPM adaptation."""
from pathlib import Path
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/scripts')]
from fm_state_runs import select_state_runs,fm_short_state_samples
from test_opm_performed_runs import setup
from test_opm_mdx import write,wait,analyze
from test_opm_reader import vgm
from opm_mdx import project_segments
from opm_mdx_music import build_music
from opm_conversion import convert

class FmShortStateTests(unittest.TestCase):
    def build(self,body,threshold=352):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'case.vgm';path.write_bytes(vgm(setup()+wait(1000)+body+wait(1000)))
            native=analyze(path,Path(tmp)/'trace');before=tuple(native.segments)
            plan=project_segments(before,end_vgmticks=native.source_end_vgmticks)
            music=build_music(plan,before,short_state_samples=threshold)
            self.assertEqual(native.segments,before)
            return music

    def test_shared_threshold_and_ms_conversion(self):
        self.assertEqual(fm_short_state_samples(),44)
        self.assertEqual(fm_short_state_samples(8),352)
        self.assertEqual(fm_short_state_samples(12),529)
        for n,drop in ((352,(1,)),(353,())):
            self.assertEqual(select_state_runs(((0,1000,'a'),(1000,1000+n,'b'),(1000+n,3000,'a')),max_samples=352)[1],drop)
        self.assertEqual(select_state_runs(((0,20,'a'),(20,40,'b'))),((1,),(0,)))
        for ms in (0,-1,float('inf'),float('nan')):
            with self.assertRaises(ValueError):fm_short_state_samples(ms)

    def test_transient_boundary_configurable_and_disabled(self):
        for n,ms,expected in ((352,8,1),(353,8,0),(529,12,1),(530,12,0)):
            body=write(8,120)+wait(1000)+write(0x30,8)+wait(n)+write(0x30,0)+wait(1000)+write(8,0)
            music=self.build(body,fm_short_state_samples(ms))
            self.assertEqual(music.summary()['fm_short_state_omissions'],expected)
            self.assertEqual(self.build(body,0).summary()['fm_short_state_omissions'],0)

    def test_prefix_backfills_attack_but_release_tail_is_protected(self):
        music=self.build(write(8,120)+wait(352)+write(0x30,8)+wait(1000)+write(8,0))
        note=next(u for u in music.units['A'] if u.kind=='note')
        self.assertEqual(note.performed_key[0].kf_raw,8)
        self.assertEqual(music.summary()['fm_short_state_omissions'],1)
        tail=self.build(write(8,120)+wait(1000)+write(0x30,8)+wait(352)+write(8,0))
        self.assertFalse(tail.summary()['fm_short_state_omissions'])
        self.assertTrue(any(r['reason']=='release_tail_state' for r in tail.short_state_rows))

    def test_ordered_tone_pan_global_and_terminal_zero_time_are_protected(self):
        for reg,value in ((0x40,2),(0x20,0x47),(1,2)):
            body=write(8,120)+wait(1000)+write(reg,value)+wait(20)+write(0x30,8)+wait(1000)+write(8,0)
            music=self.build(body)
            self.assertFalse(music.summary()['fm_short_state_omissions'])
            self.assertTrue(any('protected' in r['reason'] for r in music.short_state_rows))
        music=self.build(write(8,120)+wait(1000)+write(0x30,8)+wait(20)+write(0x30,0)+write(8,0))
        self.assertFalse(music.summary()['fm_short_state_omissions'])
        self.assertTrue(any(r['reason']=='protected_zero_time_operation' for r in music.short_state_rows))

    def test_collapsed_release_tail_retains_plan_and_terminal_writes(self):
        from opm_short_states import prepare
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'case.vgm'
            body=setup()+wait(1000)+write(8,120)+wait(20)+write(0x30,8)+wait(1000)+write(0x30,16)+wait(1)+write(8,0)+wait(1000)
            path.write_bytes(vgm(body));native=analyze(path,Path(tmp)/'trace')
            plan=project_segments(native.segments,end_vgmticks=native.source_end_vgmticks)
            # Reuse the actual ordered projection, with a coarse target clock.
            writes=[w for w in plan.writes if w.ch==0]
            onset=next(i for i,w in enumerate(writes) if w.register==8 and w.data==120)
            off=next(i for i,w in enumerate(writes[onset+1:],onset+1) if w.register==8 and w.data==0)
            segments={(s.ch,s.source_event_id):s for s in native.segments}
            runs,rows=prepare(writes,onset,off,lambda w:segments.get((w.ch,w.source_event_id)),lambda t:t//100)
            self.assertIsNotNone(runs)
            self.assertEqual(runs.terminal_writes,((0x30,16),))
            self.assertTrue(any(r['action']=='retain_terminal_write' for r in rows))
            self.assertTrue(any(r['action']=='omit_short_state' for r in rows))

    def test_compiled_omission_matches_explicit_retained_pitch_and_volume(self):
        from pcm_mdx import default_generator
        from verify_opm_mdx_roundtrip import generate
        generator=default_generator()
        if not generator.is_file():
            self.skipTest('Built MDX fixture generator is unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);replays=[]
            transient=write(0x30,8)+b''.join(write(0x60+8*op,30) for op in range(4))
            restore=write(0x30,0)+b''.join(write(0x60+8*op,20) for op in range(4))
            for name,extra in (('filtered',transient+wait(352)+restore),('expected',wait(352))):
                body=write(8,120)+wait(1000)+extra+wait(1000)+write(8,0)+wait(1000)
                music=self.build(body,352 if name=='filtered' else 0)
                if name=='filtered':
                    self.assertEqual(music.summary()['fm_short_state_omissions'],1)
                source=root/(name+'.mml');source.write_text(music.text)
                actual=generate(generator,source,root,name)
                channels={}
                for segment in actual.segments:
                    if segment.vgmticks_end<=segment.vgmticks:continue
                    rows=channels.setdefault(segment.ch,[])
                    item=(segment.vgmticks,segment.vgmticks_end,segment.state)
                    if rows and rows[-1][1]==item[0] and rows[-1][2]==item[2]:
                        rows[-1]=(rows[-1][0],item[1],item[2])
                    else:rows.append(item)
                replays.append(channels)
            self.assertEqual(replays[0],replays[1])

    def test_compiled_terminal_restore_includes_omitted_pitch_and_level_values(self):
        from pcm_mdx import default_generator
        from verify_opm_mdx_roundtrip import generate
        generator=default_generator()
        if not generator.is_file():
            self.skipTest('Built MDX fixture generator is unavailable')
        levels=b''.join(write(0x60+8*op,30) for op in range(4))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);replays=[]
            # The dropped KF/TL state owns values absent from the final KC write.
            for name,body in (
                ('filtered',write(8,120)+wait(1000)+write(0x30,8)+levels+wait(20)+write(0x28,0x41)+wait(1)+write(8,0)+wait(1000)),
                ('expected',write(8,120)+wait(1021)+write(8,0)+write(0x28,0x41)+write(0x30,8)+levels+wait(1000))):
                music=self.build(body,44 if name=='filtered' else 0)
                if name=='filtered':
                    self.assertEqual(music.summary()['fm_short_state_omissions'],1)
                    restores={r['register']:r['data'] for r in music.short_state_rows if r['action']=='restore_terminal_state'}
                    self.assertEqual(restores,{0x30:8,0x60:30,0x68:30,0x70:30,0x78:30})
                    note=next(u for u in music.units['A'] if u.kind=='note')
                    self.assertIn((0x28,0x41),note.performed_key[4])
                    self.assertIn((0x30,8),note.performed_key[4])
                source=root/(name+'.mml');source.write_text(music.text)
                actual=generate(generator,source,root,name)
                channels={}
                for segment in actual.segments:
                    if segment.vgmticks_end<=segment.vgmticks:continue
                    rows=channels.setdefault(segment.ch,[])
                    item=(segment.vgmticks,segment.vgmticks_end,segment.state)
                    if rows and rows[-1][1]==item[0] and rows[-1][2]==item[2]:
                        rows[-1]=(rows[-1][0],item[1],item[2])
                    else:rows.append(item)
                replays.append(channels)
            self.assertEqual(replays[0],replays[1])

    def test_consecutive_zero_target_tail_writes_keep_order_and_release_identity(self):
        body=write(8,120)+wait(1000)+write(0x30,8)+wait(20)+write(0x28,0x41)+wait(1)+write(0x30,16)+wait(1)+write(8,0)
        music=self.build(body,44)
        note=next(u for u in music.units['A'] if u.kind=='note')
        self.assertEqual(note.performed_key[4][:2],((0x28,0x41),(0x30,16)))
        self.assertTrue(any(r['action']=='omit_short_state' for r in music.short_state_rows))

    def test_canonical_conversion_uses_option_and_emits_audit(self):
        body=setup()+wait(2000)+write(8,120)+wait(2000)+write(0x30,8)+wait(400)+write(0x30,0)+wait(2000)+write(8,0)+wait(2000)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'AUTH.vgm';source.write_bytes(vgm(body));original=source.read_bytes()
            for name,ms,enabled,omits in (('default',None,True,1),('eight',8,True,0),('twelve',12,True,1),('off',12,False,0)):
                out=root/name
                convert(source,out,normalization_ms=8,normalize_lengths=enabled,dump_passes=True,song_loop=False,
                        **(dict(fm_state_ms=ms) if ms is not None else {}))
                report=json.loads((out/'AUTH.fm.short_states.json').read_text())
                self.assertEqual(report['threshold_samples'],fm_short_state_samples(24 if ms is None else ms))
                self.assertEqual(report['omitted_states'],omits)
                self.assertEqual(report['enabled'],enabled)
                timing=json.loads((out/'AUTH.mdx.normalization.json').read_text())
                self.assertEqual(timing['normalization_ms'],8)
                self.assertTrue((out/'AUTH.fm.short_states.csv').is_file())
            self.assertEqual(source.read_bytes(),original)

if __name__=='__main__':unittest.main()
