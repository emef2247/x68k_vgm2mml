"""Target buffer arithmetic, binding and independent final-file validation."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts'), str(Path(__file__).parent), str(ROOT)]
from pcm_capacity import PcmCapacityPolicy, resolve_pcm_capacity, PDX_BYTE_LIMIT
from generate_pcm_fixtures import playback, vgm
from msm6258 import analyze
from pcm_mdx import project, write_pdx, default_generator
from pcm_assessment import ProjectionError
import vgm2mml


class CapacityPolicyTests(unittest.TestCase):
    def test_omitted_buffer_uses_initial_resident_based_file_cap(self):
        policy = resolve_pcm_capacity()
        self.assertEqual(policy.pdx_byte_limit, 315122)
        self.assertEqual(PDX_BYTE_LIMIT, 315122)
        self.assertIsNone(policy.buffer_bytes)
        self.assertEqual(policy.summary(900000)['pcm_buffer_capacity_check'], 'unconfigured')
        self.assertEqual(policy.summary(900000)['runtime_buffer_fit'], 'unmeasured')
        with self.assertRaises(FrozenInstanceError):policy.buffer_bytes = 1024

    def test_buffer_alone_can_exceed_the_previous_file_ceiling(self):
        policy = resolve_pcm_capacity(buffer_kib=2048, loader='mxctrl')
        self.assertEqual(policy.pdx_byte_limit, 2097152 - 270 - 4096)
        self.assertEqual(policy.summary()['pdx_operational_byte_limit'], policy.pdx_byte_limit)

    def test_mxctrl_overhead_and_margin_are_within_the_resident_buffer(self):
        policy = resolve_pcm_capacity(buffer_kib=312, loader='mxctrl')
        self.assertEqual(policy.pdx_byte_limit, 319488 - 270 - 4096)
        at = policy.summary(policy.pdx_byte_limit)
        self.assertEqual(at['pcm_transfer_bytes'] + at['pcm_buffer_margin_bytes'],319488)
        self.assertEqual(at['pcm_buffer_capacity_check'], 'within_budget')
        self.assertEqual(policy.summary(policy.pdx_byte_limit + 1)['pcm_buffer_capacity_check'], 'exceeds_budget')
        self.assertEqual(policy.summary()['pcm_buffer_capacity_check'], 'unmeasured')

    def test_larger_resident_buffer_is_not_capped_at_1_2mb(self):
        self.assertEqual(resolve_pcm_capacity(buffer_kib=4096).pdx_byte_limit, 4096 * 1024 - 4096)

    def test_impossible_or_malformed_settings_are_rejected(self):
        for kwargs in ({'buffer_kib':0}, {'buffer_kib':True}, {'buffer_kib':1.5},
            {'buffer_kib':1}, {'buffer_kib':1,'loader':'mxctrl','margin_bytes':0},
            {'loader':'mxctrl'}, {'loader':'unknown'}, {'margin_bytes':-1}, {'margin_bytes':0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):resolve_pcm_capacity(**kwargs)
        self.assertEqual(PcmCapacityPolicy(buffer_bytes=768, margin_bytes=0).pdx_byte_limit,768)

    def test_cli_defaults_and_explicit_settings(self):
        parser = vgm2mml.build_parser()
        args = parser.parse_args(['source.vgm'])
        self.assertIsNone(args.pcm_buffer_kib)
        args = parser.parse_args(['source.vgm','--pcm-buffer-kib','312','--pcm-loader','mxctrl'])
        self.assertEqual((args.pcm_buffer_kib,args.pcm_loader,args.pcm_buffer_margin_bytes),(312,'mxctrl',4096))

    def test_policies_do_not_leak_between_consecutive_projections(self):
        body, _ = playback(bytes(range(32)))
        source = analyze(vgm(body))
        small = resolve_pcm_capacity(buffer_kib=1, margin_bytes=0)
        a = project(source, stem='a', policy='best-effort', capacity=small)
        b = project(source, stem='b', policy='best-effort')
        self.assertIs(a.capacity_policy,small)
        self.assertEqual(b.capacity_policy.pdx_byte_limit,PDX_BYTE_LIMIT)
        self.assertEqual(a.bindings,b.bindings)
        self.assertEqual(a.summary()['pcm_capacity']['pcm_buffer_capacity_check'],'within_budget')

    def test_binding_rejects_a_smaller_configured_budget(self):
        body, _ = playback(bytes(range(32)))
        source = analyze(vgm(body))
        with self.assertRaisesRegex(ProjectionError,'800/799'):
            project(source,stem='small',policy='best-effort',capacity=PcmCapacityPolicy(buffer_bytes=799,margin_bytes=0))

    def test_parallel_force_uses_one_global_byte_budget(self):
        from test_pcm_bank_budget import many_sounds
        source = many_sounds(4)
        source = replace(source,playbacks=tuple(replace(p,start_vgmticks=0,end_vgmticks=2000)
            for p in source.playbacks),source_end_vgmticks=3000)
        snapshot = source.samples,source.playbacks
        capacity = resolve_pcm_capacity(buffer_kib=1,margin_bytes=0)
        plan = project(source,stem='parallel',force=True,policy='best-effort',capacity=capacity)
        self.assertIs(plan.capacity_policy,capacity)
        self.assertEqual(len(plan.bindings),2)
        self.assertEqual(plan.summary()['pcm_pdx_estimated_bytes'],1024)
        self.assertEqual(plan.force_capacity.omitted_playback_ids,{2,3})
        self.assertEqual({r['mdx_track'] for r in plan.rows},{'P','Q'})
        self.assertEqual((source.samples,source.playbacks),snapshot)

    @unittest.skipUnless(default_generator().is_file(), 'Build external typed PCM helper')
    def test_normalization_preflight_keeps_the_resolved_policy(self):
        from opm_conversion import convert
        body, _ = playback(bytes(range(32)))
        raw = vgm(bytes.fromhex('54 28 40 54 08 78') + body + bytes.fromhex('54 08 00'),opm=True)
        capacity = resolve_pcm_capacity(buffer_kib=1,margin_bytes=0)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);source = root/'shared.vgm';source.write_bytes(raw)
            with patch('pcm_mdx.project',wraps=project) as calls:
                convert(source,root/'out',normalize_lengths=True,pcm_capacity=capacity)
            self.assertGreaterEqual(len(calls.call_args_list),3)
            self.assertTrue(all(call.kwargs.get('capacity') is capacity for call in calls.call_args_list))
            import json
            report = json.loads((root/'out/shared.mdx.normalization.json').read_text())
            self.assertTrue(report['adopted'])
            self.assertEqual(source.read_bytes(),raw)

    def test_actual_packed_bytes_include_extra_padding(self):
        body, _ = playback(bytes(range(32)))
        source = analyze(vgm(body))
        policy = resolve_pcm_capacity(buffer_kib=1,margin_bytes=0)
        plan = project(source,stem='packed',policy='best-effort',capacity=policy)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);generator = root/'helper';generator.write_bytes(b'placeholder')
            def pack(command, **kwargs):
                table = bytearray(768);struct.pack_into('>II',table,0,768,32)
                Path(command[-1]).write_bytes(table + source.samples[0].encoded_bytes + b'\0'*300)
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            with patch('pcm_mdx.subprocess.run', side_effect=pack):
                with self.assertRaisesRegex(ValueError,'Packed PDX.*1100/1024'):
                    write_pdx(plan,source,root,'packed',generator=generator)
            self.assertFalse((root/'packed.pdx').exists())
            self.assertEqual(source.samples[0].encoded_bytes,bytes(range(32)))

    @unittest.skipUnless(default_generator().is_file(), 'Build external typed PCM helper')
    def test_canonical_reduction_and_final_pdx_obey_the_same_budget(self):
        first, _ = playback(bytes(range(256)))
        second, _ = playback(bytes(reversed(range(256))))
        raw = vgm(first + second)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);source = root/'authored.vgm';source.write_bytes(raw)
            out = root/'out'
            command = [sys.executable,str(ROOT/'vgm2mml.py'),str(source),'--outdir',str(out),
                '--pcm-policy','best-effort','--pcm-buffer-kib','1','--pcm-buffer-margin-bytes','0',
                '--no-song-loop','--dump-passes']
            proc = subprocess.run(command,capture_output=True,timeout=60)
            self.assertEqual(proc.returncode,0,(proc.stdout+proc.stderr).decode(errors='replace'))
            self.assertLessEqual((out/'authored.pdx').stat().st_size,1024)
            import json
            merge = json.loads((out/'authored.pcm_bank_merge.json').read_text())['summary']
            timing = json.loads((out/'authored.pcm.timing.json').read_text())
            self.assertEqual(merge['capacity']['pdx_byte_limit'],1024)
            self.assertEqual(timing['pcm_pdx_byte_limit'],1024)
            self.assertEqual(timing['pcm_capacity']['pcm_buffer_capacity_check'],'within_budget')
            self.assertGreater(merge['forced_sample_count'],0)
            self.assertEqual(source.read_bytes(),raw)


if __name__ == '__main__':unittest.main()
