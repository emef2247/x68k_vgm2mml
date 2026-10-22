"""Export listening WAVs from existing encoded PCM IR; no VGM reconversion.

Reads saved PCM samples/segments and optional bank metadata. WAVs decode the
transcoded MSM6258 assets; pre-ADPCM waveforms cannot be recovered from this IR.
Playback volume/pan are reported separately and are not baked into these WAVs.
"""
import argparse
import csv
from fractions import Fraction
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from msm6258 import PcmSample
from pcm_assessment import generated_binary_artifacts
from pcm_block_wav import dump_pcm_block_wavs


def _rows(path, *, required=False):
    if not path.is_file() and not required:
        return []
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def _object(path):
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected JSON object: {path.name}')
    return value


def _integer(value):
    return None if value in (None, '', 'None') else int(value)


def load_pcm_ir(folder, stem):
    """Load candidate assets without rewriting source IR or trusting adjacent PDXs."""
    folder = Path(folder).resolve()
    if Path(stem).name != stem or stem in ('', '.', '..'):
        raise ValueError('PCM stem must be a file name')
    samples = []
    ids = set()
    for row in _rows(folder / f'{stem}.pcm_samples.csv', required=True):
        sample_id = int(row['sample_id'])
        if sample_id in ids:
            raise ValueError(f'Duplicate PCM sample ID: {sample_id}')
        ids.add(sample_id)
        relative = Path(row['filename'])
        path = (folder / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(folder):
            raise ValueError('PCM sample filename leaves the existing song-output folder')
        encoded = path.read_bytes()
        if row.get('byte_length') and int(row['byte_length']) != len(encoded):
            raise ValueError(f'PCM sample {sample_id} byte length disagrees with saved IR')
        samples.append(PcmSample(sample_id, row['codec'], encoded, row['sha256']))
    playbacks = []
    for row in _rows(folder / f'{stem}.pcm_segments.csv', required=True):
        sample_id = _integer(row['sample_id'])
        if sample_id is not None and sample_id not in ids:
            raise ValueError(f'PCM playback references an unavailable sample: {sample_id}')
        rate_num, rate_den = int(row['rate_num']), int(row['rate_den'])
        rate = Fraction(rate_num, rate_den)
        playbacks.append(SimpleNamespace(playback_id=int(row['playback_id']),
            sample_id=sample_id, chip_instance=int(row['chip_instance']),
            rate_num=rate_num, rate_den=rate_den, rate_hz=rate,
            start_vgmticks=Fraction(row['start_vgmticks']),
            end_vgmticks=Fraction(row['end_vgmticks']),
            first_source_event_id=_integer(row['first_source_event_id']),
            last_source_event_id=_integer(row['last_source_event_id']), pan=_integer(row['pan'])))
    assets = []
    for row in _rows(folder / f'{stem}.segapcm_bank.assets.csv'):
        asset = dict(row, sample_id=int(row['sample_id']))
        if row.get('target_sample_count'):
            asset['target_sample_count'] = int(row['target_sample_count'])
        assets.append(asset)
    events = []
    for row in _rows(folder / f'{stem}.segapcm_bank.events.csv'):
        event = dict(row, playback_id=int(row['playback_id']))
        for key in ('native_gate_id', 'source_channel', 'source_event_id', 'end_source_event_id'):
            if key in event:
                event[key] = _integer(event[key])
        events.append(event)
    event_by_id = {e['playback_id']: e for e in events}
    for playback in playbacks:
        event = event_by_id.get(playback.playback_id, {})
        playback.source_channel = event.get('source_channel')
        playback.target_volume = _integer(event.get('target_volume'))
    source = _object(folder / f'{stem}.pcm_source.json')
    analysis = SimpleNamespace(samples=tuple(samples), playbacks=tuple(playbacks),
        bank_assets=tuple(assets), bank_events=tuple(events), bank_waveforms=(),
        source_origin=source.get('source_origin', 'saved_encoded_pcm_ir'),
        pcm_profile=source.get('pcm_profile'))
    plan = None
    pdx = folder / f'{stem}.pdx'
    if (pdx in generated_binary_artifacts(folder, stem)
            and (folder / f'{stem}.pcm_bindings.csv').is_file()
            and (folder / f'{stem}.pcm_projection.csv').is_file()):
        capacity = _object(folder / f'{stem}.pcm.force_capacity.json')
        plan = SimpleNamespace(bindings=tuple(SimpleNamespace(sample_id=int(r['sample_id']))
            for r in _rows(folder / f'{stem}.pcm_bindings.csv')),
            rows=tuple(_rows(folder / f'{stem}.pcm_projection.csv')),
            omitted_playbacks=tuple(_rows(folder / f'{stem}.pcm_omitted_playbacks.csv')),
            force_capacity=SimpleNamespace(rows=capacity.get('rows', ())))
    return analysis, plan


def export_existing_pcm_blocks(folder, stem, *, outdir=None):
    analysis, plan = load_pcm_ir(folder, stem)
    return dump_pcm_block_wavs(analysis, Path(outdir) if outdir is not None else folder,
                               stem, plan=plan, saved_ir=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path, help='Existing song-output folder containing saved PCM IR CSVs')
    parser.add_argument('--stem', required=True, help='Exact filename stem of the saved PCM IR')
    parser.add_argument('--outdir', type=Path, help='Diagnostic output root; default: existing song-output folder')
    args = parser.parse_args(argv)
    try:
        result = export_existing_pcm_blocks(args.folder, args.stem, outdir=args.outdir)
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as error:
        parser.error(str(error))
    print(f"PCM IR listening WAVs: {result['wav_count']} files / {result['sample_count']} candidate samples")
    print('Decoded transcoded ADPCM assets; source/pre-ADPCM audio and final playback are not reconstructed.')
    print(f"Manifest: {result['manifest_path']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
