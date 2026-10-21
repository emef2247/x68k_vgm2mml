"""Authored source-to-MDX checks of approximate bank reduction and evidence."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
import generate_segapcm_listening as sega_fixture


def csv_rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def gain_variant_vgm():
    base, _, _ = sega_fixture.patterns()['SEGAONE']
    fm_setup = sega_fixture.fm()
    setup = base[:base.index(fm_setup) + len(fm_setup)]
    commands = setup
    for initial, held in ((96, 48), (48, 24)):
        commands += (sega_fixture.voice(0, left=initial, right=0, end=3)
                     + sega_fixture.wait(3528) + sega_fixture.write(0, 2, held)
                     + sega_fixture.wait(3528) + sega_fixture.write(0, 0x86, 1)
                     + sega_fixture.wait(7056))
    # Each gate consumes 5000 native frames. Both starts therefore have the
    # same 16.8 cursor fraction; only the entire gain trajectory differs.
    return sega_fixture.make_vgm(commands + bytes((0x54, 8, 0)))


class PcmBankMergeIntegrationTests(unittest.TestCase):
    def test_gain_variant_reduction_preserves_source_ir_and_preview_bytes(self):
        from pcm_mdx import default_generator
        if not default_generator().is_file():
            self.skipTest('built typed PCM helper required')
        from opm_conversion import convert
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'GAINPAIR.vgm'
            source.write_bytes(gain_variant_vgm())
            outputs = {}
            for mode in ('off', 'similar', 'budget96'):
                out = root / mode
                options = {} if mode == 'budget96' else dict(pcm_bank_merge=mode)
                convert(source, out, segapcm_source=True, segapcm_pcm=True,
                        pcm_policy='best-effort', force=True, song_loop=False,
                        dump_passes=True, **options)
                outputs[mode] = out
            plain, reduced = outputs['off'], outputs['similar']
            samples = csv_rows(plain / 'GAINPAIR.pcm_samples.csv')
            self.assertEqual(len(samples), 2)
            # Approximation changes the target view, never the saved original
            # sample inventory, source timings, or encoded candidate bytes.
            for suffix in ('samples', 'segments'):
                self.assertEqual(csv_rows(plain / f'GAINPAIR.pcm_{suffix}.csv'),
                                 csv_rows(reduced / f'GAINPAIR.pcm_{suffix}.csv'))
            for sample in samples:
                self.assertEqual((plain / sample['filename']).read_bytes(),
                                 (reduced / sample['filename']).read_bytes())
            self.assertEqual(len(csv_rows(plain / 'GAINPAIR.pcm_bindings.csv')), 2)
            self.assertEqual(len(csv_rows(reduced / 'GAINPAIR.pcm_bindings.csv')), 1)
            summary = json.loads((reduced / 'GAINPAIR.pcm_bank_merge.json').read_text())['summary']
            self.assertEqual(summary['input_sample_count'], 2)
            self.assertEqual(summary['output_sample_count'], 1)
            self.assertEqual(summary['merged_playback_count'], 1)
            self.assertEqual(summary['gate_duration_basis'], 'projected_mdx_clock')
            self.assertEqual(summary['recovered_playback_count'], 0)
            self.assertEqual(summary['newly_omitted_playback_count'], 0)
            self.assertEqual(summary['retained_playback_delta'], 0)
            self.assertEqual(summary['preview_wav_count'], 1)
            budget = json.loads((outputs['budget96'] / 'GAINPAIR.pcm_bank_merge.json').read_text())['summary']
            self.assertEqual(budget['mode'], 'budget96')
            self.assertLessEqual(budget['output_sample_count'], 96)
            self.assertEqual(csv_rows(outputs['budget96'] / 'GAINPAIR.pcm_bindings.csv'),
                             csv_rows(reduced / 'GAINPAIR.pcm_bindings.csv'))
            comparison = json.loads((Path(summary['preview_directory']) / 'GAINPAIR.manifest.json').read_text())
            self.assertEqual(comparison['pairs'][0]['gate_frame_origin'], 'checked_target_gate')
            self.assertLess(summary['output_payload_bytes'], summary['input_payload_bytes'])
            mapping = csv_rows(reduced / 'GAINPAIR.pcm_bank_merge.samples.csv')
            self.assertEqual({r['original_sample_id'] for r in mapping}, {'0', '1'})
            self.assertEqual(len({r['target_sample_id'] for r in mapping}), 1)
            rows = csv_rows(reduced / 'GAINPAIR.pcm_projection.csv')
            self.assertEqual({r['original_sample_id'] for r in rows}, {'0', '1'})
            self.assertEqual(len({r['sample_id'] for r in rows}), 1)
            self.assertEqual(len({r['target_volume'] for r in rows}), 2)
            volume_commands = [r for r in csv_rows(reduced / 'GAINPAIR.pcm_target_commands.csv')
                               if r['kind'] == 'volume']
            self.assertEqual(len({r['value'] for r in volume_commands}), 2)
            previews = {}
            for mode, out in outputs.items():
                folder = out / '_diagnostics' / 'GAINPAIR' / 'pcm_blocks'
                manifest = json.loads((folder / 'GAINPAIR.manifest.json').read_text())
                previews[mode] = manifest
                self.assertEqual(manifest['sample_count'], 2)
                for asset in manifest['assets']:
                    data = (folder / asset['file']).read_bytes()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), manifest['owned_files'][asset['file']])
                if mode == 'similar':
                    self.assertEqual({r['binding_status'] for r in manifest['assets']},
                                     {'retained', 'represented'})
            self.assertEqual(previews['off']['owned_files'].keys(),
                             previews['similar']['owned_files'].keys())
            for name in previews['off']['owned_files']:
                if name.endswith('.wav'):
                    self.assertEqual(previews['off']['owned_files'][name],
                                     previews['similar']['owned_files'][name])


if __name__ == '__main__':
    unittest.main()
