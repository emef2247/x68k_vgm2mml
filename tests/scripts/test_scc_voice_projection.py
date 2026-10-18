"""Small authored SCC notes, two-lane allocation and fitted parameter checks."""
import copy
import csv
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/scripts')]
from chip_segments import SccSegment,SccAnalysis
from psg_scc_opm import project
from opm_performance import build_performance
from scc_note_units import interpret
from scc_voice_bank import load
from test_opm_performance import psg

SAW=bytes((i*8-128)&255 for i in range(32)).hex()
SINE=bytes(round(100*math.sin(i*math.pi/16))&255 for i in range(32)).hex()


def row(start=0,end=441,volume=15,**changes):
    base=SccSegment('vCtrl',0.,0,0,1,200,volume,4,'c',0,(),200,1,0,0,SAW,1,
                    vgmticks=start,vgmticks_end=end)
    return replace(base,**changes)


def bank(raw):
    identity=hashlib.sha256(bytes.fromhex(raw)).hexdigest()
    additive=dict(algorithm=7,feedback=0,operator_muls=[1,3,5,7],operator_tl=[30,40,50,60],carriers=[0,1,2,3],model='additive')
    fm=dict(algorithm=4,feedback=3,operator_muls=[2,1,1,1],operator_tl=[27,127,33,127],carriers=[2,3],model='fm')
    return dict(schema='scc-fm-fit-v1',target_chip='YM2151',target_clock_hz=4000000,
        reference_gain=.125,reference_frequency_hz=440.,search_version='authored-test',
        emulator=dict(core='authored test candidate',sample_rate_hz=48000,warmup_frames=2048,measured_frames=4096,
            carrier_tl0_peak_units=1.,source_sha256={name:'0'*64 for name in ('ym2151.c','ym2151.h','mamedef.h','scc_opm_probe.c')}),
        waveforms={identity:dict(waveform_hex=raw,waveform_sha256=identity,candidates={
            'additive':dict(parts=[additive],spectral_error=1.),
            'fm-additive':dict(parts=[fm,additive],spectral_error=.2)})})


class SccProjectionTests(unittest.TestCase):
    def test_msx_envelope_pitch_wave_and_eof_boundaries_reach_both_lanes(self):
        rows=[row(),row(441,882,12),row(882,1323,8),row(1323,1764,14),
              row(1764,1764,14,ev_type='f1Ctrl'),row(1764,2205,13),
              row(2205,2646,10,waveform_id=1,waveform_hex=SINE),row(2646,2646,0)]
        before=repr(rows);notes=interpret({0:rows},end=3087)[0]
        self.assertEqual(notes[0].runs,[(15,441),(12,441),(8,441)])
        self.assertEqual([n.start for n in notes],[0,1323,1764,2205,2646])
        self.assertTrue(notes[-1].rest)
        self.assertEqual(notes[-1].length,441)
        result=project({},SccAnalysis({0:rows},(SAW,SINE)),psg_clock=0,scc_clock=1789772,
                       end_vgmticks=3087,scc_model='additive8')
        self.assertEqual(repr(rows),before)
        self.assertEqual(result.settings['scc_voice_projection']['extra_channel_map'],{0:1})
        perf=build_performance(result)
        for target in (0,1):
            attacks=[w.vgmticks for w in perf.writes if w.target_ch==target and w.inferred_key and w.data&0x78]
            self.assertEqual(attacks,[0,1323,1764,2205])
            self.assertTrue(all((w.data&7)==target if w.register==8 else (w.register&7)==target
                                for w in perf.writes if w.target_ch==target))
        self.assertEqual(len({w.write_id for w in perf.writes}),len(perf.writes))
        with tempfile.TemporaryDirectory() as directory:
            result.dump(directory,'AUTH');perf.dump(directory,'AUTH')
            with (Path(directory)/'AUTH.scc.music.csv').open() as stream:
                data=list(csv.DictReader(stream))
            self.assertEqual(json.loads(data[0]['volume_runs']),[[15,441],[12,441],[8,441]])
            self.assertTrue((Path(directory)/'AUTH.scc.music.ch0.structure.csv').exists())

    def test_extra_channels_rank_benefit_and_never_replace_source_or_psg(self):
        scc={0:[row(end=500),row(500,2000,0)],1:[row(end=2000,ch=1)]}
        scc.update({ch:[row(end=2000,ch=ch,waveform_hex='00'*32)] for ch in (2,3,4)})
        scc[4]=[replace(scc[4][0],tone_period=8)]
        psg_rows={ch:[replace(psg(),ch=ch,vgmticks_end=2000)] for ch in (0,1)}
        result=project(psg_rows,SccAnalysis(scc,(SAW,)),psg_clock=1789772,scc_clock=1789772,
                       end_vgmticks=2000,scc_model='additive8',psg_model='fm')
        self.assertEqual(result.settings['scc_voice_projection']['extra_channel_map'],{1:7})
        self.assertIn(4,result.settings['scc_voice_projection']['reserved_target_channels'])
        self.assertEqual({w.target_ch for w in result.writes if w.source_chip=='psg'},{5,6})
        decisions=result.settings['scc_voice_projection']['allocation']
        self.assertTrue(any(d['source_ch']==0 and d['action']=='quality_fallback_one_lane' for d in decisions))
        self.assertTrue(all(not d['source_channel_omitted'] for d in decisions))
        psg_rows[2]=[replace(psg(),ch=2,vgmticks_end=2000)]
        full=project(psg_rows,SccAnalysis(scc,(SAW,)),psg_clock=1789772,scc_clock=1789772,
                     end_vgmticks=2000,scc_model='additive8',psg_model='fm')
        self.assertEqual(full.settings['scc_voice_projection']['extra_channel_map'],{})

    def test_source_only_selection_retains_both_source_note_views(self):
        psg_rows={0:[psg()]}
        scc=SccAnalysis({0:[row()]},(SAW,))
        for selected in ('psg','scc'):
            result=project(psg_rows,scc,psg_clock=1789772,scc_clock=1789772,
                end_vgmticks=882,scc_model='additive8',source_selection=selected)
            self.assertEqual({r['source_chip'] for r in result.rows},{selected})
            self.assertTrue(result.source_music)
            self.assertTrue(result.scc_music)
            self.assertEqual(result.settings['excluded_sources'][0]['chip'],'scc' if selected=='psg' else 'psg')
        envelope={0:[replace(psg(),envelope_enabled=1)]}
        only_scc=project(envelope,scc,psg_clock=1789772,scc_clock=1789772,
            end_vgmticks=882,scc_model='additive8',source_selection='scc')
        self.assertEqual(only_scc.settings['forced_omissions'],[])
        self.assertNotIn(5,only_scc.settings['scc_voice_projection']['reserved_target_channels'])

    def test_silent_fitted_second_part_needs_no_spare_channel(self):
        data=bank(SAW)
        candidate=next(iter(data['waveforms'].values()))['candidates']['fm-additive']
        candidate['parts'][1]['operator_tl']=[127]*4
        scc={ch:[row(ch=ch)] for ch in range(5)}
        psg_rows={ch:[replace(psg(),ch=ch,vgmticks_end=441)] for ch in range(3)}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'voices.json';path.write_text(json.dumps(data))
            result=project(psg_rows,SccAnalysis(scc,(SAW,)),psg_clock=1789772,scc_clock=1789772,
                end_vgmticks=441,scc_model='fm-additive',scc_voice_bank=path)
            report=result.settings['scc_voice_projection']
            self.assertEqual(report['extra_channel_map'],{})
            self.assertEqual(report['waveform_decisions'][0]['channels'],1)
            self.assertEqual({r['voice_model'] for r in result.rows if r['source_chip']=='scc'},{'fm'})
            self.assertEqual({w.target_ch for w in result.writes},set(range(8)))

    def test_fm_volume_changes_carriers_only_and_bank_target_is_validated(self):
        rows=[row(),row(441,882,7)]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'voices.json';data=bank(SAW);path.write_text(json.dumps(data))
            result=project({},SccAnalysis({0:rows},(SAW,)),psg_clock=0,scc_clock=1789772,
                end_vgmticks=882,scc_model='fm-additive',scc_voice_bank=path)
            primary=[r for r in result.rows if r['target_lane']==0]
            a,b=[json.loads(r['carrier_tl']) for r in primary]
            self.assertEqual((a[0],a[1]),(b[0],b[1]))
            self.assertGreater(b[2],a[2])
            self.assertEqual(primary[0]['voice_model'],'fm')
            decisions=result.settings['scc_voice_projection']['waveform_decisions']
            self.assertEqual(decisions[0]['channels'],2)
            weak=copy.deepcopy(data);next(iter(weak['waveforms'].values()))['candidates']['fm-additive']['spectral_error']=2.
            path.write_text(json.dumps(weak))
            fallback=project({},SccAnalysis({0:rows},(SAW,)),psg_clock=0,scc_clock=1789772,
                end_vgmticks=882,scc_model='fm-additive',scc_voice_bank=path)
            self.assertEqual(fallback.settings['scc_voice_projection']['extra_channel_map'],{})
            self.assertIn('did not improve',fallback.settings['scc_voice_projection']['waveform_decisions'][0]['reason'])
            bad=copy.deepcopy(data);bad['emulator'].pop('source_sha256');path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'SHA-256'):load(path,clock=4000000)
            bad=copy.deepcopy(data);bad['target_chip']='YM2608';path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'YM2151'):load(path,clock=4000000)
            bad=copy.deepcopy(data);entry=next(iter(bad['waveforms'].values()));entry['candidates']['fm-additive']['parts'][0]['carriers']=[0,1]
            path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'carrier mask'):load(path,clock=4000000)


if __name__=='__main__':unittest.main()
