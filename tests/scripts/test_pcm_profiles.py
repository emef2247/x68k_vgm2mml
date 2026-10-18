"""Small authored low-profile checks; no private regression or compiler."""
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/scripts'),str(ROOT/'scripts')]
from pcm_profiles import get_profile
from pcm_msm_profile import project as low_msm
from msm6258 import analyze
from pcm_mdx import project as bind
from pcm_assessment import ProjectionError
from test_msm6258 import source,write,wait
import test_segapcm_pcm as sega_helpers
import test_opna_adpcm as delta_helpers
import test_opna_adpcm_waveform as live_helpers


def msm(count=200,rate=Fraction(15625),clock=8000000,flags=6):
    commands=write(0,1)+write(2,0)+write(0,2);cursor=0
    for i in range(count):
        tick=int(Fraction(i*88200)/rate)
        if tick>cursor:commands+=wait(tick-cursor)
        commands+=write(1,(i*7)%256);cursor=tick
    end=int(Fraction(count*88200)/rate)
    commands+=wait(end-cursor)+write(0,1)
    return analyze(source(commands,clock=clock,flags=flags))


class PcmProfileTests(unittest.TestCase):
    def test_msm_half_payload_same_timing_and_source_bytes(self):
        native=msm();before=repr(native)
        self.assertIs(low_msm(native),native)
        low=low_msm(native,pcm_profile='low')
        self.assertEqual(repr(native),before)
        self.assertEqual(len(low.samples[0].encoded_bytes),100)
        self.assertEqual(low.playbacks[0].rate_hz,Fraction(15625,2))
        self.assertEqual((low.playbacks[0].start_vgmticks,low.playbacks[0].end_vgmticks),
                         (native.playbacks[0].start_vgmticks,native.playbacks[0].end_vgmticks))
        target=bind(low,stem='LOW',policy='best-effort')
        self.assertIn(2,[c['value'] for c in target.typed_commands if c['kind']=='frequency'])
        self.assertEqual(target.summary()['pcm_profile'],'low')
        self.assertEqual(target.summary()['pcm_payload_bytes'],100)
        with tempfile.TemporaryDirectory() as folder:
            native.dump(folder,'LOW');low.dump(folder,'LOW')
            report=json.loads((Path(folder)/'LOW.pcm_profile.json').read_text())
            self.assertEqual(report['source_payload_bytes'],200)
            self.assertEqual(report['target_payload_bytes'],100)
            self.assertEqual((Path(folder)/'LOW.pcm_samples/sample_0000.adpcm').read_bytes(),native.samples[0].encoded_bytes)

    def test_msm_already_low_rate_preserves_bytes_and_source_blockers(self):
        native=msm(40,Fraction(15625,4),clock=4000000,flags=4)
        low=low_msm(native,pcm_profile='low')
        self.assertEqual(low.samples[0].encoded_bytes,native.samples[0].encoded_bytes)
        self.assertEqual(low.playbacks[0].rate_hz,native.playbacks[0].rate_hz)
        self.assertEqual(low.target_evidence,())
        bind(low,stem='ALREADY_LOW',policy='strict')
        invalid=replace(native,options=native.options|8)
        self.assertIs(low_msm(invalid,pcm_profile='low'),invalid)
        with self.assertRaises(ProjectionError):bind(invalid,stem='INVALID',policy='best-effort')

    def test_sega_profile_chunks_rate_and_alignment(self):
        def encode(values):
            count=sum(1 for value in values)
            return bytes(count//2),0
        native=sega_helpers.native(20*44100)
        with patch('segapcm_pcm.encode_msm6258',encode):
            standard=sega_helpers.project(native,source_raw=b'')
            low=sega_helpers.project(native,source_raw=b'',pcm_profile='low')
        self.assertEqual(len(standard.chunks),3)
        self.assertEqual(len(low.chunks),2)
        self.assertEqual(sum(r['encoded_bytes'] for r in low.target_mapping)*2,
                         sum(r['encoded_bytes'] for r in standard.target_mapping))
        self.assertTrue(all(p.rate_hz==Fraction(15625,2) for p in low.playbacks))
        aligned=low.align_to_clock(lambda t:round(t/441),39)
        for row in aligned.target_mapping:
            wanted=Fraction((row['target_end_tick']-row['target_start_tick'])*39*256,1000000)*Fraction(15625,2)
            self.assertLessEqual(abs(row['target_sample_count']-wanted),1)
        self.assertEqual(get_profile().rate,15625)

    def test_batch_forwards_profile_to_canonical_cli(self):
        import contextlib,io,subprocess
        import export_mdx
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);src=root/'AUTH.vgm';src.write_bytes(msm(20).source_raw)
            helper=root/'helper';helper.write_bytes(b'authored placeholder')
            captured=[]
            def run(command,**kwargs):
                captured.append((command,kwargs))
                return subprocess.CompletedProcess(command,1,'','authored converter rejection')
            with patch('export_mdx.subprocess.run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
                rows=export_mdx.run_batch(src,root/'out',generator=helper,pcm_profile='ultra_low',pcm_policy='best-effort',no_vgm=True)
            self.assertEqual(rows[0]['status'],'conversion_failed')
            command,kwargs=captured[0]
            self.assertEqual(command[command.index('--pcm-profile')+1],'ultra_low')
            self.assertEqual(kwargs['timeout'],600)

    def test_ultra_low_quarter_payload_f0_and_original_evidence(self):
        native=msm();before=repr(native)
        ultra=low_msm(native,pcm_profile='ultra_low')
        self.assertEqual(repr(native),before)
        self.assertEqual(len(ultra.samples[0].encoded_bytes),50)
        self.assertEqual(ultra.playbacks[0].rate_hz,Fraction(15625,4))
        self.assertEqual((ultra.playbacks[0].clock_hz,ultra.playbacks[0].divider),(4000000,1024))
        target=bind(ultra,stem='ULTRA',policy='best-effort')
        self.assertEqual([c['value'] for c in target.typed_commands if c['kind']=='frequency'],[0])
        self.assertEqual(target.summary()['pcm_profile'],'ultra_low')
        with tempfile.TemporaryDirectory() as directory:
            native.dump(directory,'ULTRA');ultra.dump(directory,'ULTRA')
            report=json.loads((Path(directory)/'ULTRA.pcm_profile.json').read_text())
            self.assertEqual(report['pcm_profile'],'ultra_low')
            self.assertEqual(report['target_payload_bytes'],50)
            self.assertEqual((Path(directory)/'ULTRA.pcm_samples/sample_0000.adpcm').read_bytes(),native.samples[0].encoded_bytes)
            self.assertTrue((Path(directory)/'ULTRA.pcm_ultra_low.pcm_samples/sample_0000.adpcm').exists())
        already=msm(40,Fraction(15625,4),clock=4000000,flags=4)
        unchanged=low_msm(already,pcm_profile='ultra_low')
        self.assertEqual(unchanged.samples[0].encoded_bytes,already.samples[0].encoded_bytes)
        self.assertEqual(unchanged.target_evidence,())

        def encode(values):
            return bytes(sum(1 for _ in values)//2),0
        with patch('segapcm_pcm.encode_msm6258',encode):
            standard=sega_helpers.project(sega_helpers.native(40*44100),source_raw=source(wait(44100)*40))
            wave=sega_helpers.project(sega_helpers.native(40*44100),source_raw=source(wait(44100)*40),pcm_profile='ultra_low')
        self.assertEqual(len(wave.chunks),2)
        self.assertEqual(sum(r['encoded_bytes'] for r in wave.target_mapping)*4,
                         sum(r['encoded_bytes'] for r in standard.target_mapping))
        aligned=wave.align_to_clock(lambda t:round(t/441),39)
        self.assertTrue(all((p.clock_hz,p.divider,p.rate_hz)==(4000000,1024,Fraction(15625,4)) for p in aligned.playbacks))
        for row in aligned.target_mapping:
            wanted=Fraction((row['target_end_tick']-row['target_start_tick'])*39*256,1000000)*Fraction(15625,4)
            self.assertLessEqual(abs(row['target_sample_count']-wanted),1)
        with tempfile.TemporaryDirectory() as directory:
            aligned.dump(directory,'ULTRA')
            report=json.loads((Path(directory)/'ULTRA.segapcm_pcm_bridge.json').read_text())
            self.assertEqual((report['target_clock_hz'],report['target_divider'],report['mdx_frequency_index']),
                             (4000000,1024,0))
        from opna_adpcm import analyze as analyze_delta,project_msm6258
        raw,_=delta_helpers.source();delta=analyze_delta(raw);before=repr(delta)
        result=project_msm6258(delta,pcm_profile='ultra_low')
        self.assertTrue(result.samples)
        self.assertTrue(all(Fraction(s.rate_num,s.rate_den)==Fraction(15625,4) for s in result.samples))
        self.assertEqual(repr(delta),before)
        live=live_helpers.project(live_helpers.source(),source_raw=b'authored',pcm_profile='ultra_low')
        self.assertTrue(live.playbacks)
        self.assertTrue(all(p.rate_hz==Fraction(15625,4) and p.clock_hz==4000000 for p in live.playbacks))

    def test_batch_parser_default_and_explicit_timeout(self):
        import contextlib,io
        import export_mdx
        for extra,expected in (([],600),(['--timeout','17'],17)):
            with patch.object(sys,'argv',['export_mdx.py','AUTH.vgm','--outdir','unused',
                         '--pcm-profile','ultra_low',*extra]),patch.object(export_mdx,'run_batch',return_value=[]) as run,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(export_mdx.main(),0)
            self.assertEqual(run.call_args.kwargs['timeout'],expected)
            self.assertEqual(run.call_args.kwargs['pcm_profile'],'ultra_low')

    def test_delta_independent_and_live_controls_use_low_rate(self):
        from opna_adpcm import analyze as analyze_delta,project_msm6258
        from opna_pcm import adapt
        raw,_=delta_helpers.source();native=analyze_delta(raw);before=repr(native)
        standard=project_msm6258(native)
        low=project_msm6258(native,pcm_profile='low')
        self.assertLessEqual(sum(len(s.encoded_bytes) for s in low.samples),
                             sum(len(s.encoded_bytes) for s in standard.samples))
        self.assertTrue(all(Fraction(s.rate_num,s.rate_den)<=Fraction(15625,2) for s in low.samples))
        bridge=adapt(native,low,source_raw=raw,pcm_profile='low')
        self.assertEqual(bridge.pcm_profile,'low')
        self.assertEqual(repr(native),before)
        live=live_helpers.project(live_helpers.source(),source_raw=b'authored',pcm_profile='low')
        self.assertEqual(live.pcm_profile,'low')
        self.assertTrue(all(p.rate_hz==Fraction(15625,2) for p in live.playbacks))


if __name__=='__main__':unittest.main()
