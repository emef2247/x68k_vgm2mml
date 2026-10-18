"""Small authored timing/filter/profile integration checks; no private inputs."""
from array import array
from fractions import Fraction
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/scripts')]
from opm_mdx import mdx_tick
from opm_target_vgm import write_target_vgm
from psg_scc_opm import AdditivePlan,TargetWrite
from psg_playback import PsgPlayback,PlaybackGate
from psg_pcm_mdx import project
from vgm_timing import command_times


class PsgPcmMdxTests(unittest.TestCase):
    def test_exact_writer_sorts_original_time_and_preserves_loop_and_eof(self):
        writes=[TargetWrite(0,'psg',0,0,5,mdx_tick(5),5,0x28+5,64,'later',),
                TargetWrite(1,'psg',1,0,1,mdx_tick(1),6,0x28+6,65,'earlier',)]
        plan=AdditivePlan(writes,[],{},2003,dict(target_clock=4000000))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'AUTH.vgm';mapping=path.with_suffix('.csv')
            write_target_vgm(plan,path,mapping_csv=mapping,song_loop_start=997,exact_source_times=True)
            times=list(command_times(path.read_bytes()))
            self.assertEqual([e.vgmticks for e in times if e.command==0x54],[1,5])
            self.assertEqual(times[-1].vgmticks,2003)
            from vgm_loop import read_loop_metadata
            self.assertEqual(read_loop_metadata(path.read_bytes())['loop_start_samples'],997)
            with mapping.open() as stream:rows=list(csv.DictReader(stream))
            self.assertEqual([int(r['target_vgmticks']) for r in rows],[1,5])
            self.assertEqual({r['serialized_timing'] for r in rows},{'original_source_samples'})

    def test_target_filter_and_profile_keep_native_waveform_and_shared_alignment(self):
        samples=array('h',[4000 if i%40<20 else 0 for i in range(4410) for _ in (0,1)])
        native=PsgPlayback(Fraction(44100),4410,samples,
            (PlaybackGate(0,Fraction(0),Fraction(4410),0,None,(0,1),'source_end'),),(),{})
        original=native.samples.tobytes()
        full=project(native,source_raw=b'authored',loop_start=1003)
        low=project(native,source_raw=b'authored',loop_start=1003,pcm_profile='ultra_low')
        self.assertEqual(native.samples.tobytes(),original)
        self.assertTrue(any(end==1003 for _,end,_ in full.chunks))
        self.assertLess(sum(len(s.encoded_bytes) for s in low.samples),sum(len(s.encoded_bytes) for s in full.samples)/3)
        aligned=low.align_to_clock(lambda t:mdx_tick(t,32),32)
        self.assertTrue(all(abs(r['target_duration_error_samples'])<=1 for r in aligned.target_mapping))
        self.assertEqual(aligned.source_loop_vgmticks,1003)
        self.assertTrue(any(e['code']=='psg_target_filter' for e in aligned.target_evidence))
        self.assertEqual(full.source_origin,'projected_msm6258_from_psg')


if __name__=='__main__':unittest.main()
