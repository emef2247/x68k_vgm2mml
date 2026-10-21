"""Tiny authored saved-IR diagnostic export tests, without VGM conversion."""
from contextlib import redirect_stdout
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'scripts')]
from export_pcm_blocks import export_existing_pcm_blocks, load_pcm_ir, main
from pcm_block_wav import dump_pcm_block_wavs


class ExportPcmBlocksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.sample = self.folder / 'CASE.pcm_samples' / 'sample_0000.adpcm'
        self.sample.parent.mkdir()
        self.sample.write_bytes(b'\x21')
        self.write_csv('pcm_samples.csv', [dict(sample_id=0, codec='msm6258-adpcm4-low-first',
            sha256=hashlib.sha256(b'\x21').hexdigest(), byte_length=1,
            filename='CASE.pcm_samples/sample_0000.adpcm')])
        self.write_csv('pcm_segments.csv', [dict(playback_id=4, chip_instance=0, sample_id=0,
            start_vgmticks=10, end_vgmticks=30, first_source_event_id=7, last_source_event_id=9,
            rate_num=15625, rate_den=1, pan=0)])
        self.write_csv('segapcm_bank.assets.csv', [dict(sample_id=0, asset_kind='source_part', target_sample_count=2)])
        self.write_csv('segapcm_bank.events.csv', [dict(playback_id=4, native_gate_id=2, source_channel=3)])

    def write_csv(self, suffix, rows):
        with (self.folder / ('CASE.' + suffix)).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_existing_saved_ir_exports_decoded_only_without_source_mutation(self):
        before = self.sample.read_bytes()
        result = export_existing_pcm_blocks(self.folder, 'CASE')
        self.assertEqual(result['wav_count'], 1)
        self.assertEqual(result['assets'][0]['stage'], 'decoded_adpcm')
        self.assertEqual(result['assets'][0]['asset_kind'], 'source_part')
        self.assertEqual(self.sample.read_bytes(), before)
        self.assertTrue(Path(result['manifest_path']).is_file())
        with (Path(result['directory']) / result['playback_csv']).open(encoding='utf-8') as stream:
            playback = next(csv.DictReader(stream))
        self.assertEqual((playback['source_channel'], playback['native_gate_id']), ('3', '2'))
        self.assertEqual(playback['projection_status'], 'not_projected')

    def test_unowned_binary_does_not_establish_retention(self):
        pdx = self.folder / 'CASE.pdx'
        raw = bytearray(769)
        struct.pack_into('>II', raw, 0, 768, 1)
        raw[768] = 0x21
        pdx.write_bytes(raw)
        self.write_csv('pcm_bindings.csv', [dict(sample_id=0, bank=0, slot=0)])
        self.write_csv('pcm_projection.csv', [dict(playback_id=4)])
        self.assertIsNone(load_pcm_ir(self.folder, 'CASE')[1])
        assessment = dict(artifacts=dict(pdx=dict(status='generated', path=str(pdx),
            sha256=hashlib.sha256(raw).hexdigest())))
        (self.folder / 'CASE.pcm.assessment.json').write_text(json.dumps(assessment), encoding='utf-8')
        result = export_existing_pcm_blocks(self.folder, 'CASE')
        self.assertEqual(result['assets'][0]['binding_status'], 'retained')
        pdx.write_bytes(b'user changed PDX')
        self.assertIsNone(load_pcm_ir(self.folder, 'CASE')[1])

    def test_sample_path_outside_existing_folder_is_rejected(self):
        self.write_csv('pcm_samples.csv', [dict(sample_id=0, codec='msm6258-adpcm4-low-first',
            sha256='', filename='../outside.adpcm')])
        with self.assertRaisesRegex(ValueError, 'leaves'):
            load_pcm_ir(self.folder, 'CASE')

    def test_cli_uses_explicit_stem_and_separate_output(self):
        other = self.folder / 'listening'
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([str(self.folder), '--stem', 'CASE', '--outdir', str(other)])
        self.assertEqual(code, 0)
        self.assertIn('source/pre-ADPCM audio', output.getvalue())
        self.assertTrue((other / '_diagnostics/CASE/pcm_blocks/saved_ir/CASE.manifest.json').is_file())

    def test_saved_ir_export_preserves_full_conversion_pre_adpcm_outputs(self):
        item, _ = load_pcm_ir(self.folder, 'CASE')
        item.bank_waveforms = (dict(sample_id=0, view_id='source-view',
            samples=(0, 1000, -2000), rate_num=15625, rate_den=1),)
        original = dump_pcm_block_wavs(item, self.folder, 'CASE')
        root = Path(original['directory'])
        snapshot = {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}
        saved = export_existing_pcm_blocks(self.folder, 'CASE')
        self.assertEqual(Path(saved['directory']), root / 'saved_ir')
        self.assertTrue(saved['saved_ir'])
        self.assertEqual(saved['wav_count'], 1)
        self.assertTrue(all((root / name).read_bytes() == payload for name, payload in snapshot.items()))
        self.assertTrue(any('pre_adpcm' in name for name in snapshot))


if __name__ == '__main__':
    unittest.main()
