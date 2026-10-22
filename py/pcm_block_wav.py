"""Diagnostic listening WAVs of all candidate PCM IR assets, before capacity loss.

These decode the transcoded MSM6258 bytes with an independent-note reset
assumption. They are not source ROM audio or a reconstruction of final playback
volume, pan, gate duration, mixing or driver interpolation.
"""
from collections import defaultdict
import csv
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import struct
import wave

from opna_adpcm import _msm_next
from pcm_profiles import get_profile


GENERATOR = 'x68k_vgm2mml.pcm_block_wav.v1'
CODEC = 'msm6258-adpcm4-low-first'
RESET = 'independent note assumption: predictor=-2, step_index=0; low nibble first; PCM16 scale=64'


def _csv_bytes(rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def _wav_bytes(encoded, rate):
    signal, index = -2, 0
    pcm = bytearray()
    for byte in encoded:
        for nibble in (byte & 15, byte >> 4):
            signal, index = _msm_next(signal, index, nibble)
            pcm.extend(struct.pack('<h', signal * 64))
    return _pcm_wav_bytes(pcm, rate)


def _pcm_wav_bytes(pcm, rate):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return stream.getvalue()


def _name(root, name):
    if not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..'):
        raise ValueError('PCM block manifest contains an unsafe file name')
    target = root / name
    if target.is_symlink() or target.resolve().parent != root.resolve():
        raise ValueError('PCM block output leaves the diagnostic directory')
    return target


def _hash(payload):
    return hashlib.sha256(payload).hexdigest()


def dump_pcm_block_wavs(analysis, outdir, stem, *, plan=None, saved_ir=False):
    """Save every candidate asset plus rate/use/retention CSVs and an ownership manifest.

    Call with the original analysis, not a capacity-pruned view. The optional
    final target plan contributes retained/omitted status without pruning WAVs.
    Unknown/unreferenced rates use the explicitly named target profile, if any.
    Existing modified or unowned outputs cause a failure before any replacement.
    Saved-IR exports use a separate namespace because they cannot regenerate
    pre-ADPCM waveforms from a preceding full conversion.
    """
    if Path(stem).name != stem or stem in ('', '.', '..'):
        raise ValueError('PCM block stem must be a file name')
    root = Path(outdir) / '_diagnostics' / stem / 'pcm_blocks'
    if saved_ir:
        root /= 'saved_ir'
    if root.is_symlink() or not root.resolve().is_relative_to(Path(outdir).resolve()):
        raise ValueError('PCM block diagnostic directory must not be a symbolic link')
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = _name(root, stem + '.manifest.json')
    old = {}
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding='utf-8'))
        if (previous.get('generator') != GENERATOR or previous.get('stem') != stem
                or not isinstance(previous.get('owned_files'), dict)):
            raise ValueError('Refusing to replace an unowned PCM block manifest')
        old = previous['owned_files']
    uses = defaultdict(list)
    for playback in analysis.playbacks:
        if playback.sample_id is not None:
            uses[playback.sample_id].append(playback)
    asset_metadata = defaultdict(list)
    for asset in getattr(analysis, 'bank_assets', ()):
        asset_metadata[asset['sample_id']].append(asset)
    retained = {binding.sample_id for binding in plan.bindings} if plan is not None else set()
    projection = {int(row['playback_id']): row for row in plan.rows} if plan is not None else {}
    projected = set(projection)

    def target_sample(playback):
        if playback.playback_id not in projection:
            return None
        value = projection[playback.playback_id].get('sample_id')
        return playback.sample_id if value in (None, '') else int(value)

    def association(sample_id, playbacks, *, view_specific=False):
        same = any(target_sample(p) == sample_id for p in playbacks)
        represented = any(target_sample(p) is not None and target_sample(p) != sample_id for p in playbacks)
        if same or (not view_specific and sample_id in retained):
            return 'retained'
        if represented:
            return 'represented'
        if playbacks and all(p.playback_id in omitted for p in playbacks):
            return 'omitted'
        return 'unbound' if plan is not None else 'not_projected'

    def representation(playbacks):
        return dict(target_sample_ids=json.dumps(sorted({target_sample(p) for p in playbacks
                                                        if target_sample(p) is not None})),
            represented_playback_count=sum(target_sample(p) is not None and target_sample(p) != p.sample_id
                                           for p in playbacks))
    omitted = defaultdict(list)
    if plan is not None:
        rows = list(getattr(plan, 'omitted_playbacks', ()))
        capacity = getattr(plan, 'force_capacity', None)
        rows.extend(getattr(capacity, 'rows', ()))
        for row in rows:
            if row.get('playback_id') is None:
                continue
            if row.get('action') in (None, 'omit', 'omit_normalization'):
                reason = row.get('reason') or row.get('cap_kind') or row.get('action') or 'omitted'
                key = int(row['playback_id'])
                if str(reason) not in omitted[key]:
                    omitted[key].append(str(reason))
    events = {int(row['playback_id']): row for row in getattr(analysis, 'bank_events', ())}
    files, rows, playback_rows = {}, [], []
    for sample in analysis.samples:
        if not isinstance(sample.sample_id, int) or sample.sample_id < 0:
            raise ValueError('PCM diagnostic sample ID must be a nonnegative integer')
        if sample.codec != CODEC:
            raise ValueError(f'PCM listening WAV codec is unsupported: {sample.codec}')
        digest = _hash(sample.encoded_bytes)
        if digest != sample.sha256:
            raise ValueError(f'PCM sample {sample.sample_id} encoded hash disagrees with source IR')
        sample_uses = uses[sample.sample_id]
        rates = sorted({Fraction(p.rate_hz) for p in sample_uses})
        rate_origin = 'playback_rate'
        if not rates:
            profile = getattr(analysis, 'pcm_profile', None)
            if profile is None:
                raise ValueError(f'PCM sample {sample.sample_id} has no playback rate or explicit target profile')
            rates = [get_profile(profile).rate]
            rate_origin = 'target_profile_unreferenced_asset'
        metadata = asset_metadata[sample.sample_id]
        kinds = sorted({str(a.get('asset_kind', a.get('kind', 'finite_rom_view'))) for a in metadata})
        if not kinds:
            kinds = ['rendered_mix' if getattr(analysis, 'source_origin', '') ==
                     'projected_msm6258_from_segapcm' else 'encoded_pcm_ir']
        logical_counts = sorted({int(a['target_sample_count']) for a in metadata if a.get('target_sample_count') is not None})
        status = association(sample.sample_id, sample_uses)
        for rate in rates:
            header_rate = round(rate)
            if rate <= 0 or not 0 < header_rate <= 0xffffffff:
                raise ValueError('PCM WAV rate is not a positive representable integer rate')
            filename = f'{stem}.sample_{sample.sample_id:03}.{rate.numerator}_{rate.denominator}Hz.{digest[:16]}.wav'
            files[filename] = _wav_bytes(sample.encoded_bytes, header_rate)
            matching = [p for p in sample_uses if p.rate_hz == rate]
            frame_count = len(sample.encoded_bytes) * 2
            rows.append(dict(sample_id=sample.sample_id, file=filename, codec=sample.codec,
                stage='decoded_adpcm', source_view_id='',
                encoded_sha256=digest, encoded_bytes=len(sample.encoded_bytes),
                frame_count=frame_count, logical_sample_counts=json.dumps(logical_counts),
                duration_seconds=float(Fraction(frame_count, 1) / rate),
                wav_duration_seconds=frame_count / header_rate,
                rate_num=rate.numerator, rate_den=rate.denominator,
                wav_rate_hz=header_rate, wav_rate_error_hz=float(header_rate - rate),
                rate_origin=rate_origin, decoder_reset_assumption=RESET,
                frame_scope='all encoded nibbles, including any encoder padding',
                asset_kind=';'.join(kinds), usage_scope='encoded_sample', usage_count=len(matching),
                playback_ids=json.dumps([p.playback_id for p in matching]),
                retained_playback_count=sum(p.playback_id in projected for p in matching),
                omitted_playback_count=sum(p.playback_id in omitted for p in matching),
                **representation(matching),
                binding_status=status, amplitude='decoded asset scale; no normalization or playback gain'))
        for playback in sample_uses:
            event = events.get(playback.playback_id, {})
            playback_rows.append(dict(playback_id=playback.playback_id, sample_id=sample.sample_id,
                chip_instance=playback.chip_instance,
                source_channel=getattr(playback, 'source_channel', event.get('source_channel')),
                native_gate_id=event.get('native_gate_id'),
                part_id=event.get('part_id'), view_id=event.get('view_id'),
                asset_kind=event.get('asset_kind'), volume_baked=event.get('volume_baked'),
                start_vgmticks=playback.start_vgmticks, end_vgmticks=playback.end_vgmticks,
                source_event_id=playback.first_source_event_id,
                last_source_event_id=playback.last_source_event_id,
                rate_num=playback.rate_num, rate_den=playback.rate_den,
                pan=playback.pan, target_volume=getattr(playback, 'target_volume', None),
                target_sample_id=target_sample(playback),
                projected_target_volume=projection.get(playback.playback_id, {}).get('target_volume'),
                projection_status=association(sample.sample_id, [playback], view_specific=True),
                omission_reasons=';'.join(omitted.get(playback.playback_id, ()))))
    # Optional inspectable waveform before the lossy ADPCM transcode. It is
    # already source-derived/resampled asset audio, not unprocessed ROM bytes.
    for waveform in getattr(analysis, 'bank_waveforms', ()):
        rate = Fraction(waveform['rate_num'], waveform['rate_den'])
        matching = [r for r in rows if r['sample_id'] == waveform['sample_id']
                    and r['stage'] == 'decoded_adpcm'
                    and Fraction(r['rate_num'], r['rate_den']) == rate]
        if not matching:
            raise ValueError('Pre-ADPCM waveform has no matching candidate asset/rate')
        pcm = bytearray()
        for value in waveform['samples']:
            if not isinstance(value, int) or not -32768 <= value <= 32767:
                raise ValueError('Pre-ADPCM waveform must contain unnormalized signed PCM16 values')
            pcm.extend(struct.pack('<h', value))
        fingerprint = _hash(pcm)
        view = str(waveform['view_id'])
        view_key = _hash(view.encode('utf-8'))[:16]
        row = dict(matching[0])
        view_uses = [p for p in uses[waveform['sample_id']] if p.rate_hz == rate]
        # Byte deduplication can bind several source views to one encoded asset.
        # Claim view-specific uses only when every candidate use has a view ID.
        mapped = bool(view_uses) and all(events.get(p.playback_id, {}).get('view_id')
                                       for p in view_uses)
        if mapped:
            view_uses = [p for p in view_uses
                         if str(events[p.playback_id]['view_id']) == view]
        filename = (f'{stem}.sample_{waveform["sample_id"]:03}.pre_adpcm.'
                    f'{view_key}.{rate.numerator}_{rate.denominator}Hz.{fingerprint[:16]}.wav')
        files[filename] = _pcm_wav_bytes(pcm, row['wav_rate_hz'])
        row.update(file=filename, stage='pre_adpcm', source_view_id=view,
                   codec='pcm16-source-derived-before-adpcm', frame_count=len(pcm) // 2,
                   duration_seconds=float(Fraction(len(pcm) // 2, 1) / rate),
                   wav_duration_seconds=(len(pcm) // 2) / row['wav_rate_hz'],
                   decoder_reset_assumption='none; source-derived resampled waveform before ADPCM encoding',
                   frame_scope='provided pre-ADPCM asset samples; no encoder padding',
                   amplitude='source-derived resampled asset at common scale128; no normalization or onset gain',
                   usage_scope='source_view' if mapped else 'encoded_sample',
                   usage_count=len(view_uses), playback_ids=json.dumps([p.playback_id for p in view_uses]),
                   retained_playback_count=sum(p.playback_id in projected for p in view_uses),
                   omitted_playback_count=sum(p.playback_id in omitted for p in view_uses),
                   **representation(view_uses))
        if mapped and plan is not None:
            row['binding_status'] = association(waveform['sample_id'], view_uses, view_specific=True)
        rows.append(row)
    fields = tuple(rows[0]) if rows else ('sample_id', 'file')
    playback_fields = tuple(playback_rows[0]) if playback_rows else ('playback_id', 'sample_id')
    files[stem + '.assets.csv'] = _csv_bytes(rows, fields)
    files[stem + '.playbacks.csv'] = _csv_bytes(playback_rows, playback_fields)
    # Validate all replacements and removals before writing, including metadata CSVs.
    for name in set(old) | set(files):
        target = _name(root, name)
        if target.exists() and (name not in old or _hash(target.read_bytes()) != old[name]):
            raise ValueError(f'Refusing to replace modified or unowned PCM block output: {target}')
    result = dict(schema_version=1, generator=GENERATOR, stem=stem,
        saved_ir=bool(saved_ir),
        directory=str(root), manifest_path=str(manifest_path),
        source_origin=getattr(analysis, 'source_origin', 'native_msm6258'),
        listening_scope='decoded candidate PCM IR assets, not final MDX playback or native source audio',
        sample_count=len(analysis.samples), wav_count=len(rows), assets=rows,
        playback_count=len(playback_rows), playback_csv=stem + '.playbacks.csv',
        assets_csv=stem + '.assets.csv',
        owned_files={name: _hash(payload) for name, payload in files.items()})
    for name, payload in files.items():
        _name(root, name).write_bytes(payload)
    for name in set(old) - set(files):
        _name(root, name).unlink(missing_ok=True)
    manifest_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result
