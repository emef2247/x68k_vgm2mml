"""Public authored source-view identity, fallback and complete assembly checks."""
from dataclasses import replace
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
from generate_segapcm_listening import patterns, make_vgm, voice, wait, write
from segapcm_bank import BankUnsupported, project, select
from segapcm_playback import render
from vgm_reader import parse_vgm


class SegaPcmBankTests(unittest.TestCase):
    def source(self, commands=None, loop=None, name='SEGABANK'):
        if commands is None:
            commands, loop, _ = patterns()[name]
        raw = make_vgm(commands, loop)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test.vgm'
            path.write_bytes(raw)
            traces, metadata = [], {}
            parse_vgm(str(path), temp, segapcm_trace_out=traces,
                      segapcm_metadata={}, opm_metadata=metadata)
            native = render(traces[0], metadata['source_end_vgmticks'])
        return traces[0], native, raw

    def test_identity_ignores_duration_gain_and_pan_with_shared_overlap(self):
        trace, native, raw = self.source()
        result = project(trace, native, source_raw=raw)
        self.assertEqual(len(result.samples), 1)
        self.assertEqual(len(result.bank_assets), 1)
        self.assertEqual(len(result.playbacks), 3)
        self.assertEqual([p.sample_id for p in result.playbacks], [0, 0, 0])
        self.assertEqual([p.source_channel for p in result.playbacks], [0, 1, 2])
        self.assertNotEqual(result.playbacks[0].first_source_event_id, result.playbacks[0].last_source_event_id)
        self.assertIsNone(result.bank_events[-1]['end_source_event_id'])
        self.assertEqual(result.bank_events[-1]['termination'], 'natural_stop')
        self.assertEqual([p.pan for p in result.playbacks], [2, 0, 1])
        self.assertEqual(len({p.target_volume for p in result.playbacks}), 3)
        self.assertFalse(hasattr(result, 'align_to_clock'))
        self.assertLessEqual(abs(result.bank_assets[0]['duration_error_target_samples']), 1)
        from pcm_mdx import project as target
        plan = target(result, stem='bank', policy='best-effort')
        self.assertEqual(len(plan.bindings), 1)
        self.assertEqual({u.track for u in plan.units}, {'P', 'Q'})
        changed = target(result, stem='bank', policy='best-effort', tick_mapper=lambda t: t // 11)
        self.assertEqual(plan.bindings, changed.bindings)
        with tempfile.TemporaryDirectory() as temp:
            result.dump(temp, 'bank')
            info = json.loads((Path(temp) / 'bank.pcm_source.json').read_text())
            self.assertEqual(info['consumption_origin'], 'derived_finite_rom_view')
            self.assertTrue((Path(temp) / 'bank.segapcm_bank.assets.csv').is_file())

    def test_explicit_capability_fallback_and_required_bank(self):
        trace, native, raw = self.source(name='SEGAMIX')
        with tempfile.TemporaryDirectory() as temp:
            mixed = select(trace, native, strategy='auto', outdir=temp, stem='mix', source_raw=raw)
            self.assertTrue(hasattr(mixed, 'align_to_clock'))
            report = json.loads((Path(temp) / 'mix.segapcm_projection.json').read_text())
            self.assertEqual(report['selected'], 'mix')
            self.assertEqual(report['fallback']['code'], 'sample_loop')
            with self.assertRaises(BankUnsupported):
                select(trace, native, strategy='bank', outdir=temp, stem='bank', source_raw=raw)

    def test_fractional_restart_has_its_own_view(self):
        base, _, _ = patterns()['SEGAONE']
        # Keep its ROM/FM setup, then explicitly stop and restart before exhaustion.
        from generate_segapcm_listening import fm
        setup = base[:base.index(fm()) + len(fm())]
        commands = (setup + voice(0, end=1) + wait(1) + write(0, 0x86, 1)
                    + voice(0, end=1) + wait(10000))
        trace, native, raw = self.source(commands)
        result = project(trace, native, source_raw=raw)
        self.assertEqual(len(result.bank_assets), 2)
        self.assertNotEqual(result.bank_assets[0]['address_fixed'], result.bank_assets[1]['address_fixed'])

    def test_loop_seam_is_diagnosed_and_finite_controls_use_variants(self):
        trace, native, raw = self.source()
        seam = native.gates[0].end_vgmticks / 2
        with self.assertRaisesRegex(BankUnsupported, 'song-loop'):
            project(trace, native, source_raw=raw, loop_start=seam)
        from generate_segapcm_listening import fm
        base, _, _ = patterns()['SEGAONE']
        setup = base[:base.index(fm()) + len(fm())]
        for commands in (
                setup + voice(0, delta=0) + wait(1000),
                setup + voice(0) + wait(1000) + write(0, 2, 10) + wait(1000)):
            trace, native, raw = self.source(commands)
            result = project(trace, native, source_raw=raw)
            self.assertEqual(result.bank_stats['trajectory_variant_count'], 1)
            self.assertEqual(len(result.playbacks), 1)

    def test_eof_cutoff_keeps_complete_asset_and_distinct_gate_stop(self):
        trace, native, raw = self.source(name='SEGAONE')
        full = project(trace, native, source_raw=raw)
        short_gate = replace(native.gates[0], end_vgmticks=1000, termination='source_end')
        short = project(trace, replace(native, gates=(short_gate,), source_end_vgmticks=1000), source_raw=raw)
        self.assertEqual(full.samples, short.samples)
        self.assertEqual(short.playbacks[0].end_vgmticks, 1000)
        self.assertEqual(short.playbacks[0].termination, 'source_end')

    def test_complete_public_conversion(self):
        from pcm_mdx import default_generator, validate_extended_layout
        if not default_generator().is_file():
            self.skipTest('built typed helper required')
        from opm_conversion import convert
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            commands, loop, _ = patterns()['SEGABANK']
            source = root / 'SEGABANK.vgm'
            source.write_bytes(make_vgm(commands, loop))
            out = root / 'output'
            mml, _, _ = convert(source, out, segapcm_source=True, segapcm_pcm=True,
                                pcm_policy='best-effort', dump_passes=True)
            text = mml.read_text()
            self.assertIn('\nP ', text)
            self.assertIn('\nQ ', text)
            validate_extended_layout((out / 'SEGABANK.mdx').read_bytes(), active_tracks=('P', 'Q'))
            bindings = (out / 'SEGABANK.pcm_bindings.csv').read_text().splitlines()
            self.assertEqual(len(bindings), 2)
            selected = json.loads((out / 'SEGABANK.segapcm_projection.json').read_text())
            self.assertEqual(selected['selected'], 'bank')
            assessment = json.loads((out / 'SEGABANK.pcm.assessment.json').read_text())
            self.assertEqual(assessment['target_layout']['active_pcm_tracks'], ['P', 'Q'])
            preview_path = out / '_diagnostics' / 'SEGABANK' / 'pcm_blocks' / 'SEGABANK.manifest.json'
            preview = json.loads(preview_path.read_text())
            self.assertEqual(preview['sample_count'], 1)
            self.assertEqual({row['stage'] for row in preview['assets']}, {'pre_adpcm', 'decoded_adpcm'})
            self.assertTrue(all(row['binding_status'] == 'retained' for row in preview['assets']))
            self.assertTrue(all((preview_path.parent / row['file']).is_file() for row in preview['assets']))

    def test_profiles_rate_variants_and_wrapped_zero_end_boundary(self):
        trace, native, raw = self.source(name='SEGAONE')
        variants = [project(trace, native, source_raw=raw, pcm_profile=p)
                    for p in ('standard', 'low', 'ultra_low')]
        self.assertGreater(len(variants[0].samples[0].encoded_bytes), len(variants[1].samples[0].encoded_bytes))
        self.assertGreater(len(variants[1].samples[0].encoded_bytes), len(variants[2].samples[0].encoded_bytes))
        self.assertEqual(len({p.bank_assets[0]['view_id'] for p in variants}), 3)
        from generate_segapcm_listening import fm
        base, _, _ = patterns()['SEGAONE']
        setup = base[:base.index(fm()) + len(fm())]
        # FF+1 wraps to zero; starting in FF must still play its final page.
        commands = (setup + voice(0, end=255, delta=255)[: -4]
                    + write(0, 0x85, 255) + write(0, 0x86, 2) + wait(2000))
        trace, native, raw = self.source(commands)
        result = project(trace, native, source_raw=raw)
        self.assertEqual(result.bank_assets[0]['address_fixed'], 0xff0000)
        self.assertEqual(result.bank_assets[0]['end_address_fixed'], 0x1000000)
        self.assertEqual(result.playbacks[0].termination, 'natural_stop')

    def test_auto_does_not_hide_missing_runtime_evidence(self):
        trace, native, raw = self.source()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(KeyError):
                select(trace, replace(native, runtime_events=()), strategy='auto',
                       outdir=temp, stem='invalid', source_raw=raw)


if __name__ == '__main__':
    unittest.main()
