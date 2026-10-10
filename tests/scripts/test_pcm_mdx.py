"""PCM source evidence -> shared MDX clock/binding -> independently read PDX."""
import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts')]
from generate_pcm_fixtures import cases, playback, stream_cases, vgm, wait, write
from okim6258 import analyze
from opm_conversion import convert
from opm_mdx_music import infer_clock
from pcm_mdx import default_generator, project
from pcm_assessment import ProjectionError
from pcm_assessment import PcmAssessment
from vgm_io import read_vgm_header
from verify_opm_mdx_roundtrip import source_facts


def record_previous_binaries(out, stem):
    artifacts = {name: dict(path=str(path), status='generated',
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                 for name in ('mdx', 'pdx') if (path := out / (stem + '.' + name)).is_file()}
    (out / (stem + '.pcm.assessment.json')).write_text(json.dumps(dict(artifacts=artifacts)))


class PcmMdxTests(unittest.TestCase):
    def test_assessment_keeps_loss_unknown_and_failure_separate(self):
        report = PcmAssessment('best-effort')
        report.add('pan', 'lossy', 'held_pan_latched', 'known pan loss')
        self.assertEqual(report.as_dict()['assessment_status'], 'lossy')
        self.assertEqual(report.as_dict()['validation_status'], 'unverified')
        report.add('sample', 'fail', 'payload_mismatch', 'unexpected byte mismatch')
        self.assertEqual(report.as_dict()['validation_status'], 'fail')
        self.assertEqual(len(report.as_dict()['known_losses']), 1)
        report.generated()
        self.assertEqual(report.as_dict()['artifact_status'], 'generated')
        self.assertEqual(report.as_dict()['validation_status'], 'fail')

    def test_known_target_loss_and_source_unknown_both_survive_preflight(self):
        commands = write(0, 2) + write(1, 0x12) + wait(20) + write(1, 0x34) + wait(5) + write(0, 1)
        with self.assertRaises(ProjectionError) as caught:
            project(analyze(vgm(commands, flags=14)), stem='mixed', policy='best-effort')
        report = caught.exception.assessment.as_dict()
        self.assertTrue(any(item['code'] == 'output_precision' for item in report['known_losses']))
        self.assertTrue(report['unverified_items'])
        self.assertEqual(report['artifact_status'], 'blocked')

    def test_strict_pan_loss_is_blocked_and_runtime_is_not_run(self):
        _, raw, _ = next(cases())
        with self.assertRaises(ProjectionError) as caught:
            project(analyze(raw), stem='strict')
        report = caught.exception.assessment.as_dict()
        self.assertEqual(report['artifact_status'], 'blocked')
        self.assertEqual(report['assessment_status'], 'lossy')
        self.assertEqual(report['validation_status'], 'unverified')
        self.assertEqual(report['validation_run'], 'not_run')
        self.assertEqual(len(report['known_losses']), 3)

    def test_best_effort_keeps_onset_pan_and_source_ir(self):
        _, raw, _ = next(cases())
        analysis = analyze(raw)
        before = analysis
        plan = project(analysis, stem='best', policy='best-effort')
        pans = [c['value'] for c in plan.typed_commands if c['kind'] == 'pan']
        self.assertEqual(pans, [1, 2])
        self.assertEqual(analysis, before)
        losses = plan.assessment.as_dict()['known_losses']
        self.assertEqual([item['source_value'] for item in losses], [2, 3, 0])
        self.assertTrue(all(item['projected_value'] == 1 for item in losses))
        self.assertTrue(all(item['end_vgmticks'] > item['start_vgmticks'] for item in losses))
        # One attack per source playback, with holds only for duration chunks.
        notes = [c for c in plan.typed_commands if c['kind'] == 'note']
        self.assertEqual(sum(c['ticks'] for c in notes), sum(u.end_tick-u.start_tick for u in plan.units if u.kind == 'pcm_note'))
        self.assertEqual(sum(c['kind'] == 'hold' for c in plan.typed_commands), len(notes)-2)

    def test_song_loop_is_target_loss_and_best_effort_keeps_one_finite_pass(self):
        commands, duration = playback(bytes(range(32)))
        raw = bytearray(vgm(commands))
        struct.pack_into('<I', raw, 0x1c, 0x100 - 0x1c)
        analysis = analyze(bytes(raw))
        self.assertEqual(analysis.source_loop_vgmticks, 0)
        with self.assertRaises(ProjectionError) as caught:
            project(analysis, stem='loop', policy='strict')
        losses = caught.exception.assessment.as_dict()['known_losses']
        self.assertIn('song_loop_not_emitted', [item['code'] for item in losses])
        plan = project(analysis, stem='loop', policy='best-effort')
        self.assertEqual(len([u for u in plan.units if u.kind == 'pcm_note']), 1)
        self.assertEqual(analysis.playbacks[0].end_vgmticks, duration)
        self.assertIn('song_loop_not_emitted',
                      [item['code'] for item in plan.assessment.as_dict()['known_losses']])

    def test_delayed_chip_stop_has_explicit_continuous_delivery_fallback(self):
        raw = next(raw for name, raw, _ in stream_cases() if name == 'stream_delayed_chip_stop')
        analysis = analyze(raw)
        before = analysis
        self.assertFalse(analysis.playbacks[0].independently_playable)
        self.assertEqual(analysis.playbacks[0].issues, ('irregular_byte_supply',))
        self.assertIsNone(analysis.playbacks[0].consumed_nibbles)
        with self.assertRaises(ProjectionError) as caught:
            project(analysis, stem='delayed', policy='strict')
        self.assertIn('byte_supply_schedule_not_preserved',
                      [item['code'] for item in caught.exception.assessment.as_dict()['known_losses']])
        plan = project(analysis, stem='delayed', policy='best-effort')
        self.assertEqual(analysis, before)
        self.assertEqual(analysis.samples[0].encoded_bytes, b'\x12\x34\x56\x78')
        loss = next(item for item in plan.assessment.as_dict()['known_losses']
                    if item['code'] == 'byte_supply_schedule_not_preserved')
        self.assertEqual(loss['fallback'], 'continuous_pdx_delivery')
        self.assertIn('consumed_nibbles_unknown',
                      [item['code'] for item in plan.assessment.as_dict()['unverified_items']])

    def test_stopped_stream_supply_is_inspectable_target_loss(self):
        raw = next(raw for name, raw, _ in stream_cases() if name == 'stream_stopped_supply_restart')
        analysis = analyze(raw)
        before = analysis
        self.assertFalse(analysis.issues)
        self.assertTrue(any(o.vgmticks == 17 for o in analysis.observations))
        self.assertEqual([s.encoded_bytes for s in analysis.samples], [b'\x12\x34\x56', b'\x12\x34\x56\x78'])
        with self.assertRaises(ProjectionError) as caught:
            project(analysis, stem='stopped', policy='strict')
        self.assertIn('stopped_stream_supply_not_projected',
                      [item['code'] for item in caught.exception.assessment.as_dict()['known_losses']])
        plan = project(analysis, stem='stopped', policy='best-effort')
        self.assertEqual(analysis, before)
        summary = plan.summary()
        self.assertNotIn('pcm_raw_bytes_preserved', summary)
        self.assertTrue(summary['pcm_sample_bytes_preserved'])
        self.assertIn('encoded playback samples stored in PDX', summary['pcm_byte_preservation_scope'])
        self.assertIn('profile-derived byte supply', summary['pcm_consumption_scope'])
        self.assertIn('decoder consumption not measured', summary['pcm_consumption_scope'])
        self.assertIn('stopped_stream_supply_not_projected',
                      [item['code'] for item in plan.assessment.as_dict()['known_losses']])
        self.assertEqual(len([u for u in plan.units if u.kind == 'pcm_note']), 2)

    def test_direct_stopped_data_remains_unresolved_under_best_effort(self):
        analysis = analyze(vgm(write(0, 1) + write(1, 0x34) + wait(6)))
        with self.assertRaises(ProjectionError) as caught:
            project(analysis, stem='direct_stopped', policy='best-effort')
        self.assertIn('data_outside_known_playback',
                      [item['code'] for item in caught.exception.assessment.as_dict()['unverified_items']])

    def test_long_playback_holds_before_duration_chunk_without_retrigger(self):
        commands, _ = playback(bytes(range(256)) * 4)
        plan = project(analyze(vgm(commands)), stem='long', sample_multiplier=1)
        timed = [(c['kind'], c['ticks']) for c in plan.typed_commands
                 if c['kind'] in ('hold', 'note', 'rest')]
        # A 1024-byte F4 sample lasts 512 ticks on the 256-us MDX clock.
        self.assertEqual(timed, [('hold', ''), ('note', 256), ('note', 256)])
        self.assertIn('n0,%256 & n0,%256', plan.units[0].command)

    def test_native_sample_length_loss_is_blocked_in_both_policies(self):
        _, raw, _ = next(cases())
        analysis = analyze(raw)
        sample = replace(analysis.samples[0], encoded_bytes=bytes(65536))
        analysis = replace(analysis, samples=(sample,))
        for policy in ('strict', 'best-effort'):
            with self.assertRaises(ProjectionError) as caught:
                project(analysis, stem='long', policy=policy)
            report = caught.exception.assessment.as_dict()
            self.assertEqual(report['artifact_status'], 'blocked')
            loss = report['known_losses'][0]
            self.assertEqual(loss['code'], 'sample_length_exceeds_native')
            self.assertEqual(loss['cause'], 'target_constraint')

    def test_source_invalid_and_unresolved_are_distinct(self):
        commands, _ = playback(bytes(range(16)))
        with self.assertRaises(ProjectionError) as invalid:
            project(analyze(vgm(commands, clock=0)), stem='invalid')
        self.assertEqual(invalid.exception.assessment.as_dict()['validation_status'], 'fail')
        commands = write(0, 2) + write(1, 0x12) + wait(20) + write(1, 0x34) + wait(5) + write(0, 1)
        with self.assertRaises(ProjectionError) as unknown:
            project(analyze(vgm(commands)), stem='unknown')
        self.assertEqual(unknown.exception.assessment.as_dict()['validation_status'], 'unverified')

    def test_typed_manifest_and_assessment_are_inspectable(self):
        name, raw, _ = next(cases())
        plan = project(analyze(raw), stem=name, policy='best-effort')
        with tempfile.TemporaryDirectory() as temp:
            plan.dump(temp, name)
            plan.assessment.dump(temp, name)
            manifest = (Path(temp) / (name+'.pcm') / 'target.tsv').read_text()
            self.assertTrue(manifest.startswith('kind\tvalue\tticks\n'))
            self.assertIn('volume\t128\t\n', manifest)
            self.assertTrue(manifest.endswith('end\t\t\n'))
            report = json.loads((Path(temp)/(name+'.pcm.assessment.json')).read_text())
            self.assertEqual(report['validation_status'], 'unverified')

    def test_clock_header_uses_6258_field_and_respects_data_boundary_and_version(self):
        raw = bytearray(vgm(wait(100)))
        struct.pack_into('<I', raw, 0x98, 1234567)
        self.assertEqual(read_vgm_header(raw)['okim6258_clock_raw'], 8000000)
        struct.pack_into('<I', raw, 8, 0x160)
        self.assertEqual(read_vgm_header(raw)['okim6258_clock_raw'], 0)
        struct.pack_into('<I', raw, 8, 0x171)
        struct.pack_into('<I', raw, 0x34, 12)  # command data begins at 0x40
        self.assertEqual(read_vgm_header(raw)['okim6258_clock_raw'], 0)
        self.assertEqual(read_vgm_header(raw)['okim6258_flags'], 0)

    def test_pcm_presence_audit_does_not_mistake_6295_for_6258(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'header.vgm'
            raw = bytearray(vgm(wait(100), clock=0))
            struct.pack_into('<I', raw, 0x98, 8000000)
            path.write_bytes(raw)
            self.assertFalse(source_facts(path, include_pcm=True)['source_pcm_present'])
            struct.pack_into('<I', raw, 0x90, 8000000)
            path.write_bytes(raw)
            self.assertTrue(source_facts(path, include_pcm=True)['source_pcm_present'])

    def test_shared_clock_accounts_for_pcm_boundaries(self):
        plain = infer_clock((), 4516)
        shared = infer_clock((), 4516, additional_times=(13, 101, 201))
        self.assertNotEqual(plain['chosen']['multiplier'], shared['chosen']['multiplier'])
        self.assertLessEqual(shared['chosen']['max_abs_error_samples'], 6)
        with self.assertRaisesRegex(ValueError, 'within the song'):
            infer_clock((), 10, additional_times=(11,))

    def test_public_source_evidence_matches_known_schedule_without_target_mutation(self):
        for name, raw, expected in cases():
            with self.subTest(name=name):
                a = analyze(raw)
                before = a
                self.assertEqual(a.source_end_vgmticks, expected['source_end_vgmticks'])
                self.assertEqual([p.sample_id for p in a.playbacks], expected['playback_samples'])
                self.assertEqual([p.start_vgmticks for p in a.playbacks], expected['starts'])
                self.assertEqual([p.end_vgmticks for p in a.playbacks], expected['ends'])
                self.assertEqual([p.pan for p in a.playbacks], expected['source_pan'])
                self.assertEqual([s.sha256 for s in a.samples], expected['sample_sha256'])
                self.assertTrue(all(p.independently_playable for p in a.playbacks))
                plan = project(a, stem=name, sample_multiplier=1, policy='best-effort')
                self.assertEqual([r['mdx_frequency'] for r in plan.rows], expected['mdx_frequencies'])
                notes = [u for u in plan.units if u.kind == 'pcm_note']
                for unit, pan in zip(notes, expected['mdx_pan']):
                    self.assertIn(f'p{pan} ', unit.command)
                self.assertEqual(a, before)
                self.assertTrue(all(u.source_pcm_playback_ids for u in notes))
                self.assertTrue(all(not u.source_segment_ids for u in notes))
                rests = [u for u in plan.units if u.kind == 'pcm_rest']
                if name == 'reset_pan_hold':
                    self.assertEqual([(u.source_start_vgmticks, u.source_end_vgmticks) for u in rests],
                                     [(expected['ends'][0], expected['starts'][1])])

    def test_adpcm_pan_uses_pcm_order_and_end_pan_does_not_leave_dangling_tie(self):
        data = bytes(range(32))
        for pan, target in ((0, 3), (1, 1), (2, 2), (3, 0)):
            cmd, _ = playback(data, pan=pan)
            a = analyze(vgm(cmd))
            self.assertIn(f'p{target} ', project(a, stem='pan').units[0].command)
        cmd, _ = playback(data)
        # Insert a pan immediately before the final STOP, at the note end.
        a = analyze(vgm(cmd[:-3] + write(2, 1) + cmd[-3:]))
        self.assertFalse(project(a, stem='end').units[0].command.rstrip().endswith('&'))

    def test_irregular_supply_and_rate_change_fail_before_any_target_sample_claim(self):
        cmd = write(0, 2) + write(1, 0x12) + wait(20) + write(1, 0x34) + wait(5) + write(0, 1)
        with self.assertRaisesRegex(ValueError, 'irregular_byte_supply'):
            project(analyze(vgm(cmd)), stem='irregular')
        cmd, _ = playback(bytes(range(16)), clock=1234567)
        with self.assertRaisesRegex(ValueError, 'no exact standard MDX'):
            project(analyze(vgm(cmd)), stem='rate')

    def test_source_layer_has_no_pdx_slot_limit(self):
        cmd = b''.join(playback(bytes((i, i ^ 255)))[0] for i in range(97))
        a = analyze(vgm(cmd))
        self.assertEqual(len(a.samples), 97)
        with self.assertRaisesRegex(ValueError, 'at most 96'):
            project(a, stem='capacity')

    def test_twelve_bit_output_is_retained_in_source_but_rejected_by_mdx(self):
        commands, _ = playback(bytes(range(16)))
        a = analyze(vgm(commands, flags=14))
        self.assertEqual(a.options, 14)
        self.assertTrue(a.samples)
        with self.assertRaisesRegex(ValueError, '10-bit output'):
            project(a, stem='twelve')

    def test_runtime_clock_write_cannot_invent_an_undeclared_source_chip(self):
        commands, _ = playback(bytes(range(16)))
        a = analyze(vgm(commands, clock=0))
        self.assertTrue(a.samples)
        self.assertEqual(a.playbacks[0].clock_hz, 8000000)
        with self.assertRaisesRegex(ValueError, 'absent_chip_declaration'):
            project(a, stem='absent')

    def test_missing_helper_is_explicit_and_source_passes_survive_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = folder / 'source.vgm'
            source.write_bytes(next(cases())[1])
            out = folder / 'out'
            out.mkdir()
            (out / 'source.pdx').write_bytes(b'old')
            record_previous_binaries(out, 'source')
            (out / 'source.mdx.mml').write_text('old')
            with self.assertRaisesRegex(ValueError, 'requires the built MDX helper'):
                convert(source, out, dump_passes=True, pcm_generator=folder / 'missing', pcm_policy='best-effort')
            self.assertTrue((out / 'source.pcm_segments.csv').is_file())
            self.assertTrue((out / 'source.pcm_bindings.csv').is_file())
            self.assertFalse((out / 'source.mdx.mml').exists())
            self.assertFalse((out / 'source.pdx').exists())
            report = json.loads((out / 'source.pcm.assessment.json').read_text())
            self.assertEqual(report['artifact_status'], 'error')
            self.assertEqual(report['validation_status'], 'fail')
            self.assertEqual(report['artifacts']['mdx']['status'], 'not_generated')

    def test_strict_rejection_removes_stale_target_but_keeps_input_and_report(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            source = out / 'source.vgm'
            original = next(cases())[1]
            source.write_bytes(original)
            for suffix in ('.mdx', '.pdx', '.mdx.mml', '.pcm_target_commands.csv'):
                (out / ('source' + suffix)).write_bytes(b'stale')
            record_previous_binaries(out, 'source')
            plan_folder = out / 'source.pcm'
            plan_folder.mkdir()
            (plan_folder / 'target.tsv').write_text('stale')
            with self.assertRaises(ProjectionError):
                convert(source, out, dump_passes=True)
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse((plan_folder / 'target.tsv').exists())
            self.assertFalse((out / 'source.pcm_target_commands.csv').exists())
            self.assertTrue((out / 'source.pcm_segments.csv').is_file())
            report = json.loads((out / 'source.pcm.assessment.json').read_text())
            self.assertEqual(report['artifact_status'], 'blocked')
            self.assertEqual(report['validation_run'], 'not_run')
            self.assertTrue(all(a['status'] == 'blocked' for a in report['artifacts'].values()))

    def test_failed_pdx_helper_cannot_publish_partial_file_as_generated(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.vgm'
            source.write_bytes(next(cases())[1])
            helper = Path(temp) / 'helper'
            helper.write_bytes(b'placeholder')
            out = Path(temp) / 'out'
            def failed(command, **kwargs):
                Path(command[-1]).write_bytes(b'incomplete PDX')
                return subprocess.CompletedProcess(command, 1, '', 'packing failed')
            with patch('pcm_mdx.subprocess.run', side_effect=failed):
                with self.assertRaisesRegex(ValueError, 'packing failed'):
                    convert(source, out, pcm_generator=helper, pcm_policy='best-effort')
            self.assertFalse((out / 'source.pdx').exists())
            report = json.loads((out / 'source.pcm.assessment.json').read_text())
            self.assertEqual(report['artifact_status'], 'error')
            self.assertEqual(report['artifacts']['pdx']['status'], 'not_generated')

    def test_pcm_does_not_overwrite_unowned_reference_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            source = out / 'source.vgm'
            source.write_bytes(next(cases())[1])
            references = {name: out / ('source.' + name) for name in ('mdx', 'pdx')}
            for path in references.values():
                path.write_bytes(b'original reference material')
            with self.assertRaisesRegex(ValueError, 'separate --outdir'):
                convert(source, out, pcm_policy='best-effort')
            for path in references.values():
                self.assertEqual(path.read_bytes(), b'original reference material')
            report = json.loads((out / 'source.pcm.assessment.json').read_text())
            self.assertEqual(report['artifact_status'], 'error')
            for name in references:
                self.assertEqual(report['artifacts'][name]['status'], 'preserved_existing')
                self.assertNotIn('sha256', report['artifacts'][name])

    def test_pcm_options_reject_register_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.vgm'
            source.write_bytes(next(cases())[1])
            with self.assertRaisesRegex(ValueError, 'structured notation'):
                convert(source, Path(temp) / 'out', notation='registers')

    @unittest.skipUnless(default_generator().is_file(), 'Build external MDX helper for integration checks')
    def test_normalization_default_on_retains_the_shared_pcm_clock_and_source(self):
        commands, _ = playback(bytes(range(32)))
        commands = bytes.fromhex('54 28 40 54 08 78') + commands + bytes.fromhex('54 08 00')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'shared.vgm'
            original = vgm(commands, opm=True)
            source.write_bytes(original)
            outputs = []
            for name, requested in [('default', None), ('on', True), ('off', False)]:
                out = root / name
                mml, analysis, projection = convert(source, out, dump_passes=True, normalize_lengths=requested)
                report = json.loads((out / 'shared.mdx.normalization.json').read_text())
                self.assertEqual(report['enabled'], requested is not False)
                self.assertFalse(report['adopted'])
                self.assertEqual(report['before'], report['selected'])
                if requested is not False:
                    self.assertIn('shared OPM/PCM clock', report['reason'])
                timing = json.loads((out / 'shared.mdx.timing.json').read_text())
                manifest = (out / 'shared.pcm/target.tsv').read_text()
                self.assertIn(f'tempo\t{256-projection.sample_multiplier}\t\n', manifest)
                self.assertEqual(analysis.source_end_vgmticks, projection.source_end_vgmticks)
                outputs.append((mml.read_bytes(), (out / 'shared.pdx').read_bytes(),
                                (out / 'shared.mdx').read_bytes(), (out / 'shared.pcm_segments.csv').read_bytes()))
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0], outputs[2])
            self.assertEqual(source.read_bytes(), original)

    @unittest.skipUnless(default_generator().is_file(), 'Build external MDX helper for integration checks')
    def test_unused_unsupported_opm_declaration_does_not_block_pcm_only(self):
        commands, _ = playback(bytes(range(32)))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'pcm.vgm'
            outputs = []
            for name, clock in [('plain', 0), ('unused', 0xc0000000 | 3579545)]:
                raw = bytearray(vgm(commands))
                struct.pack_into('<I', raw, 0x30, clock)
                source.write_bytes(raw)
                out = root / name
                mml, analysis, projection = convert(source, out, dump_passes=True)
                self.assertFalse(analysis.events)
                self.assertEqual(projection.clock_hz, 4000000)
                self.assertEqual(source.read_bytes(), raw)
                outputs.append((mml.read_bytes(), (out / 'pcm.mdx').read_bytes(), (out / 'pcm.pdx').read_bytes()))
            self.assertEqual(outputs[0], outputs[1])

    @unittest.skipUnless(default_generator().is_file(), 'Build external MDX helper for integration checks')
    def test_direct_mdx_failure_preserves_partial_artifacts_and_failure_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.vgm'
            source.write_bytes(next(cases())[1])
            out = Path(temp) / 'out'
            out.mkdir()
            (out / 'source.mdx').write_bytes(b'stale')
            record_previous_binaries(out, 'source')
            with patch('pcm_mdx.write_mdx', side_effect=ValueError('typed MDX failed')):
                with self.assertRaisesRegex(ValueError, 'typed MDX failed'):
                    convert(source, out, pcm_policy='best-effort')
            report = json.loads((out / 'source.pcm.assessment.json').read_text())
            self.assertEqual(report['artifact_status'], 'error')
            self.assertEqual(report['artifacts']['pdx']['status'], 'generated')
            self.assertEqual(report['artifacts']['mml']['status'], 'generated')
            self.assertEqual(report['artifacts']['mdx']['status'], 'not_generated')
            self.assertEqual(report['validation_status'], 'fail')
            self.assertEqual(report['validation_run'], 'not_run')
            self.assertEqual(len(report['known_losses']), 3)
            self.assertEqual(report['unexpected_mismatches'][0]['scope'], 'artifact')
            self.assertFalse((out / 'source.mdx').exists())

    @unittest.skipUnless(default_generator().is_file(), 'Build external MDX helper for integration checks')
    def test_native_mdx_capacity_retains_partial_outputs_and_target_dumps(self):
        raw = next(raw for name, raw, _ in stream_cases() if name == 'stream95_finite')
        real_run = subprocess.run
        def capacity_error(command, **kwargs):
            if command[1] == '--compile-pcm':
                Path(command[-1]).write_bytes(b'incomplete MDX')
                return subprocess.CompletedProcess(command, 1, '',
                    'data inconsistency: MDX track 8 offset exceeds the maximum 0xfffe')
            return real_run(command, **kwargs)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'capacity.vgm'
            source.write_bytes(raw)
            out = root / 'out'
            with patch('pcm_mdx.subprocess.run', side_effect=capacity_error):
                with self.assertRaisesRegex(ProjectionError, 'MDX capacity exceeded'):
                    convert(source, out, dump_passes=True)
            report = json.loads((out / 'capacity.pcm.assessment.json').read_text())
            self.assertEqual(report['artifact_status'], 'blocked')
            self.assertEqual(report['assessment_status'], 'lossy')
            self.assertEqual(report['validation_status'], 'unverified')
            self.assertEqual(report['validation_run'], 'not_run')
            self.assertEqual(report['known_losses'][0]['code'], 'mdx_capacity_exceeded')
            self.assertFalse(report['unexpected_mismatches'])
            self.assertEqual(report['artifacts']['mml']['status'], 'generated')
            self.assertEqual(report['artifacts']['pdx']['status'], 'generated')
            self.assertEqual(report['artifacts']['mdx']['status'], 'blocked')
            self.assertFalse((out / 'capacity.mdx').exists())
            for suffix in ('.mdx.controls.csv', '.mdx.structure.units.csv', '.mdx.timing.json',
                           '.pcm_stream_supplies.csv', '.pcm_target_commands.csv'):
                self.assertTrue((out / ('capacity' + suffix)).is_file(), suffix)
            self.assertEqual(source.read_bytes(), raw)

    @unittest.skipUnless(default_generator().is_file(), 'Build external MDX helper for integration checks')
    def test_public_pair_outputs_compile_and_pdx_payload_matches_source(self):
        for name, raw, expected in cases():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                source = folder / (name + '.vgm')
                source.write_bytes(raw)
                out = folder / 'out'
                mml, analysis, projection = convert(source, out, dump_passes=True, pcm_policy='best-effort')
                text = mml.read_text()
                self.assertIn(f'#pcmfile "{name}.pdx"', text)
                self.assertIn('/* Track P */', text)
                self.assertIn('n0,', text)
                self.assertTrue((out / (name + '.mdx')).is_file())
                self.assertNotIn('Track P', (out / (name + '.pcm') / 'opm.mml').read_text())
                assessment = json.loads((out / (name + '.pcm.assessment.json')).read_text())
                self.assertEqual(assessment['artifact_status'], 'generated')
                self.assertEqual(assessment['validation_status'], 'unverified')
                self.assertTrue(all(a['status'] == 'generated' for a in assessment['artifacts'].values()))
                if name == 'reset_pan_hold':
                    self.assertNotIn('&', text)  # each complete playback fits one note
                elif name == 'long_hold_stop':
                    self.assertIn('&', text)
                self.assertEqual(analysis.source_end_vgmticks, expected['source_end_vgmticks'])
                pdx = (out / (name + '.pdx')).read_bytes()
                offset, length = struct.unpack_from('>II', pdx)
                self.assertEqual(length, expected['sample_bytes'][0])
                self.assertEqual(hashlib.sha256(pdx[offset:offset + length]).hexdigest(), expected['sample_sha256'][0])
                self.assertEqual(pdx[8:768], bytes(760))
                report = json.loads((out / (name + '.mdx.timing.json')).read_text())
                self.assertLessEqual(report['pcm_max_abs_timing_error_samples'], 6)
                with (out / (name + '.mdx.structure.units.csv')).open() as stream:
                    rows = list(csv.DictReader(stream))
                self.assertTrue(any(row['track'] == 'P' for row in rows))
                mdx = out / (name + '.mdx')
                result = subprocess.run([str(default_generator()), '--compile-only', str(mml), str(mdx),
                                         '--pcm-mode', 'standard'], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                compiled = mdx.read_bytes()
                title_end = compiled.index(b'\r\n\x1a') + 3
                pdx_end = compiled.index(0, title_end)
                self.assertEqual(compiled[title_end:pdx_end], (name + '.pdx').encode())
                # One voice-table offset precedes nine track offsets.
                data_start = pdx_end + 1
                self.assertEqual(struct.unpack_from('>H', compiled, data_start + 2)[0], 20)
                p_start = data_start + struct.unpack_from('>H', compiled, data_start + 18)[0]
                self.assertIn(b'\x80', compiled[p_start:])  # sample slot zero note
                if name == 'reset_pan_hold':
                    self.assertNotIn(b'\xf7', compiled[p_start:])  # no artificial pan split
                elif name == 'long_hold_stop':
                    self.assertIn(b'\xf7', compiled[p_start:])  # preserve a genuine long hold

    @unittest.skipUnless(default_generator().is_file(), 'Build external MDX helper for integration checks')
    def test_public_finite_streams_generate_standard_pcm_without_rewriting_source(self):
        for name, raw, expected in stream_cases():
            if name not in ('stream95_finite', 'stream93_count', 'stream93_to_end'):
                continue
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                source = folder / (name + '.vgm')
                source.write_bytes(raw)
                out = folder / 'out'
                mml, _, _ = convert(source, out, dump_passes=True)
                self.assertEqual(source.read_bytes(), raw)
                self.assertIn('/* Track P */', mml.read_text())
                self.assertTrue((out / (name + '.mdx')).is_file())
                pdx = (out / (name + '.pdx')).read_bytes()
                offset, length = struct.unpack_from('>II', pdx)
                self.assertEqual(length, 4)
                self.assertEqual(hashlib.sha256(pdx[offset:offset + length]).hexdigest(),
                                 expected['sample_sha256'])
                with (out / (name + '.pcm_stream_supplies.csv')).open() as stream:
                    supplies = list(csv.DictReader(stream))
                self.assertEqual([int(s['vgmticks']) for s in supplies], expected['transfer_ticks'])
                report = json.loads((out / (name + '.pcm.assessment.json')).read_text())
                self.assertEqual(report['artifact_status'], 'generated')
                self.assertFalse(report['known_losses'])

    @unittest.skipUnless(default_generator().is_file(), 'Build external MDX helper for integration checks')
    def test_public_stream_fallbacks_pack_only_observed_bytes_and_report_loss(self):
        for name, code in (
                ('stream_delayed_chip_stop', 'byte_supply_schedule_not_preserved'),
                ('stream_stopped_supply_restart', 'stopped_stream_supply_not_projected')):
            raw = next(raw for case, raw, _ in stream_cases() if case == name)
            samples = analyze(raw).samples
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                source = folder / (name + '.vgm')
                source.write_bytes(raw)
                out = folder / 'out'
                mml, _, _ = convert(source, out, dump_passes=True, pcm_policy='best-effort')
                self.assertEqual(source.read_bytes(), raw)
                self.assertIn('/* Track P */', mml.read_text())
                pdx = (out / (name + '.pdx')).read_bytes()
                for slot, sample in enumerate(samples):
                    offset, length = struct.unpack_from('>II', pdx, slot * 8)
                    self.assertEqual(length, len(sample.encoded_bytes))
                    self.assertEqual(pdx[offset:offset + length], sample.encoded_bytes)
                report = json.loads((out / (name + '.pcm.assessment.json')).read_text())
                self.assertEqual(report['artifact_status'], 'generated')
                self.assertIn(code, [item['code'] for item in report['known_losses']])
                self.assertIn('consumed_nibbles_unknown',
                              [item['code'] for item in report['unverified_items']])

    def test_silent_native_opm_keeps_common_end_without_fabricating_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'silent.vgm'
            raw = bytearray(vgm(wait(4516), opm=True, clock=0))
            source.write_bytes(raw)
            mml, analysis, projection = convert(source, Path(temp) / 'out')
            self.assertFalse(analysis.events)
            self.assertFalse(projection.writes)
            self.assertIn('r', mml.read_text())
            self.assertEqual(analysis.source_end_vgmticks, 4516)

    def test_stopped_pcm_setup_without_samples_needs_no_empty_pdx_or_helper(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'stopped.vgm'
            source.write_bytes(vgm(write(0, 1) + write(2, 0) + wait(4516), opm=True))
            out = Path(temp) / 'out'
            mml, _, _ = convert(source, out, dump_passes=True, pcm_generator=Path(temp) / 'missing')
            self.assertNotIn('#pcmfile', mml.read_text())
            self.assertNotIn('Track P', mml.read_text())
            self.assertFalse((out / 'stopped.pdx').exists())
            self.assertTrue((out / 'stopped.pcm_state.csv').exists())

    def test_silent_psg_ordinary_opm_path_produces_only_rests(self):
        from psg_scc_conversion import convert as convert_psg
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'silent_psg.vgm'
            raw = bytearray(vgm(b'\xa0\x08\x00' + wait(4516), clock=0))
            struct.pack_into('<I', raw, 0x74, 1789772)
            source.write_bytes(raw)
            mml, plan = convert_psg(source, Path(temp) / 'out')
            self.assertIn('r', mml.read_text())
            self.assertNotIn('y8,', mml.read_text())


if __name__ == '__main__':
    unittest.main()
