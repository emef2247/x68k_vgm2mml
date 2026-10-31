"""C140 source route, target policy, statistics and public binary integration."""
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'py'),str(ROOT/'tests/scripts')]
from conversion_config import inspect_source,select_mdx_route
from vgm_io import read_vgm_header
from test_c140 import make_vgm,voice,wait,write
from opm_conversion import convert
from pcm_mdx import default_generator,validate_extended_layout
from pcm_assessment import ProjectionError
from pcm_bank_stats import summarize
from generate_c140_public_fixtures import cases


class C140ConversionTests(unittest.TestCase):
    def test_actual_commands_select_route_and_header_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'AUTH.vgm'
            raw=make_vgm(voice()+wait(1000))
            source.write_bytes(raw)
            usage=inspect_source(source)
            self.assertEqual(usage['used_chips'],['c140'])
            self.assertEqual(select_mdx_route(usage),'opm-c140-source')
            self.assertFalse(usage['unsupported_commands'])
            self.assertEqual(read_vgm_header(raw)['c140_clock_raw'],12288000)
            header=bytearray(raw[:256]);header.extend(b'\x62\x66')
            struct.pack_into('<I',header,4,len(header)-4)
            source.write_bytes(header)
            with self.assertRaisesRegex(ValueError,'clock declarations alone'):
                select_mdx_route(inspect_source(source))
            # Header bytes overlapping command data never become clock fields.
            compact=bytearray(0x40);compact[:4]=b'Vgm '
            struct.pack_into('<I',compact,8,0x171)
            compact.extend(b'\x62\x66')
            self.assertEqual(read_vgm_header(compact)['c140_clock_raw'],0)

    @unittest.skipUnless(default_generator().is_file(),'Build external MDX helper for binary integration')
    def test_public_fixtures_compile_through_shared_bank_and_record_route(self):
        with tempfile.TemporaryDirectory() as temp:
            for name,raw,_ in cases():
                with self.subTest(name=name):
                    root=Path(temp)/name;root.mkdir()
                    source=root/(name+'.vgm');source.write_bytes(raw)
                    out=root/'out'
                    mml,_,_=convert(source,out,c140_pcm=True,dump_passes=True,song_loop=False)
                    self.assertTrue(mml.is_file())
                    mdx=out/(name+'.mdx');pdx=out/(name+'.pdx')
                    self.assertTrue(mdx.is_file());self.assertTrue(pdx.is_file())
                    selection=json.loads((out/(name+'.c140_projection.json')).read_text())
                    self.assertEqual(selection['selected'],'bank')
                    assessment=json.loads((out/(name+'.pcm.assessment.json')).read_text())
                    self.assertEqual(assessment['policy_selection']['effective'],'best-effort')
                    self.assertEqual(assessment['policy_selection']['reason'],'c140_bank_transcoding')
                    self.assertLessEqual(pdx.stat().st_size,1200000)
                    stats=summarize(out,name)
                    self.assertEqual(stats['route_label'],'C140')
                    self.assertGreater(stats['retained_playback_count'],0)
                    self.assertTrue((out/(name+'.c140.segments.csv')).is_file())
                    self.assertTrue((out/(name+'.c140_bank.events.csv')).is_file())
                    self.assertEqual(source.read_bytes(),raw)

    def test_source_nine_voices_are_retained_until_explicit_target_capacity_selection(self):
        from c140 import analyze
        from c140_bank import project as bank
        from pcm_mdx import project as target
        commands=b''.join(voice(ch,mode=0x90) for ch in range(9))+wait(500)
        commands+=b''.join(write(ch*16+5,0) for ch in range(9))+wait(500)
        raw=make_vgm(commands)
        native=analyze(raw);projection=bank(native,source_raw=raw)
        self.assertEqual(len(projection.playbacks),9)
        with self.assertRaises(ProjectionError):target(projection,stem='capacity')
        limited=target(projection,stem='capacity',force=True)
        self.assertEqual(len(limited.omitted_playbacks),1)
        self.assertEqual(len({u.track for u in limited.units if u.kind=='pcm_note'}),8)
        self.assertEqual(len(projection.playbacks),9)

    def test_mix_projection_converts_ten_voices_without_force(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'AUTH.vgm'
            commands=b''.join(voice(ch,mode=0x90) for ch in range(10))+wait(500)
            commands+=b''.join(write(ch*16+5,0) for ch in range(10))+wait(100)
            source.write_bytes(make_vgm(commands))
            out=root/'out'
            convert(source,out,c140_pcm=True,c140_projection='mix',song_loop=False)
            selection=json.loads((out/'AUTH.c140_projection.json').read_text())
            self.assertEqual(selection['requested'],'mix')
            self.assertEqual(selection['selected'],'mix')
            self.assertTrue((out/'AUTH.c140_mix_mapping.csv').is_file())
            omitted=out/'AUTH.pcm_omitted_playbacks.csv'
            if omitted.is_file():
                self.assertEqual(len(omitted.read_text().strip().splitlines()),1)

    def test_explicit_strict_retains_source_and_blocks_transcoding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'AUTH.vgm'
            source.write_bytes(make_vgm(voice()+wait(1000)))
            with self.assertRaises(ProjectionError):
                convert(source,root/'out',c140_pcm=True,song_loop=False,pcm_policy='strict')
            self.assertTrue((root/'out/AUTH.c140.source.json').is_file())
            self.assertFalse((root/'out/AUTH.mdx').exists())


if __name__=='__main__':unittest.main()
