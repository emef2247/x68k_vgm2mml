"""Bounded, non-normalized A/B WAVs of target-only PCM bank approximation."""
import csv
from fractions import Fraction
import io
import json
import math
from pathlib import Path
import struct

from opna_adpcm import _msm_next
from pcm_bank_reduce import _gain
from pcm_block_wav import _hash, _name, _pcm_wav_bytes


GENERATOR = 'x68k_vgm2mml.pcm_merge_preview.v1'
MAX_HALF_SECONDS = 16
GAP_SECONDS = Fraction(1, 5)


def _decode(payload, limit=None):
    signal, index = -2, 0
    samples = []
    for byte in payload if limit is None else payload[:(limit + 1) // 2]:
        for nibble in (byte & 15, byte >> 4):
            signal, index = _msm_next(signal, index, nibble)
            samples.append(signal * 64)
    return samples if limit is None else samples[:limit]


def dump_merge_previews(original_analysis, reduction, outdir, stem, *, plan=None, max_pairs=24):
    """Write original then projected decoded sound, with quantized onset gains.

    Each half has the reduction's checked target gate, capped at 16 seconds.
    Legacy reductions without checked frames use the source gate duration. This
    diagnostic does not emulate driver interpolation, pan or a final mix.
    Existing source samples and the original diagnostic WAVs are never edited.
    """
    if Path(stem).name != stem or stem in ('', '.', '..'):
        raise ValueError('PCM merge preview stem must be a file name')
    if not isinstance(max_pairs, int) or isinstance(max_pairs, bool) or max_pairs < 0:
        raise ValueError('PCM merge preview pair limit must be a nonnegative integer')
    root = Path(outdir) / '_diagnostics' / stem / 'pcm_merge'
    if root.is_symlink() or not root.resolve().is_relative_to(Path(outdir).resolve()):
        raise ValueError('PCM merge preview directory must not leave the output directory')
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = _name(root, stem + '.manifest.json')
    old = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if (manifest.get('generator') != GENERATOR or manifest.get('stem') != stem
                or not isinstance(manifest.get('owned_files'), dict)):
            raise ValueError('Refusing to replace an unowned PCM merge manifest')
        old = manifest['owned_files']
    source_samples = {s.sample_id: s for s in original_analysis.samples}
    target_samples = {s.sample_id: s for s in reduction.analysis.samples}
    native_events = {p.playback_id: p for p in original_analysis.playbacks}
    final = {int(row['playback_id']): row for row in plan.rows} if plan is not None else {}
    members = {}
    for row in reduction.playback_rows:
        if (row['target_sample_id'] is not None and not row.get('explicit_omission')
                and row['original_sample_id'] != row['target_sample_id']):
            members.setdefault(row['original_sample_id'], []).append(row)
    diagnostics = {r['original_sample_id']: r for r in reduction.sample_rows}
    # Show worst accepted waveform errors first; deterministic ID breaks ties.
    order = sorted(members, key=lambda sid: (
        -float(diagnostics.get(sid, {}).get('waveform_error', 0)), -len(members[sid]), sid))
    files, rows, decoded = {}, [], {}

    def audio(sample, count):
        key = sample.sha256, count
        if key not in decoded:
            if sample.codec != 'msm6258-adpcm4-low-first' or _hash(sample.encoded_bytes) != sample.sha256:
                raise ValueError('PCM merge preview requires valid immutable MSM6258 assets')
            # Neither a huge source asset nor many representative groups may
            # turn this optional listening report into an unbounded capture.
            if len(decoded) >= 2:
                decoded.pop(next(iter(decoded)))
            decoded[key] = _decode(sample.encoded_bytes, count)
        return decoded[key]

    for sid in order[:max_pairs]:
        # Prefer an event that survived final capacity projection when known.
        event = min(members[sid], key=lambda r: (r['playback_id'] not in final, r['playback_id']))
        pid, target_id = event['playback_id'], event['target_sample_id']
        native = native_events[pid]
        projected = final.get(pid)
        status = 'not_projected' if plan is None else ('retained' if projected is not None else 'omitted')
        if projected is not None and (int(projected['sample_id']) != target_id
                or int(projected['target_volume']) != event['target_volume']):
            raise ValueError('PCM merge preview mapping disagrees with final projection')
        rate = Fraction(event['rate_num'], event['rate_den'])
        header_rate = round(rate)
        if rate <= 0 or not 0 < header_rate <= 192000:
            raise ValueError('PCM merge preview rate is not a supported positive audio rate')
        duration = Fraction(event['end_vgmticks'] - event['start_vgmticks'], 44100)
        if duration <= 0:
            raise ValueError('PCM merge preview event must have a positive gate duration')
        source_gate_frames = math.ceil(duration * rate)
        gate_frames = event.get('checked_gate_frames', source_gate_frames)
        if not isinstance(gate_frames, int) or isinstance(gate_frames, bool) or gate_frames < 0:
            raise ValueError('PCM merge preview checked gate frames must be a nonnegative integer')
        gate_origin = 'checked_target_gate' if 'checked_gate_frames' in event else 'source_gate_legacy_fallback'
        target_duration = Fraction(gate_frames, 1) / rate
        frames = min(gate_frames, math.ceil(MAX_HALF_SECONDS * rate))
        gap_frames = round(GAP_SECONDS * rate)
        old_gain, new_gain = _gain(event['original_volume']), _gain(event['target_volume'])
        first, second = audio(source_samples[sid], frames), audio(target_samples[target_id], frames)
        pcm = bytearray()
        for half, (samples, gain) in enumerate(((first, old_gain), (second, new_gain))):
            if half:
                pcm.extend(b'\0\0' * gap_frames)
            for index in range(frames):
                value = round(samples[index] * gain) if index < len(samples) else 0
                pcm.extend(struct.pack('<h', min(32767, max(-32768, value))))
        filename = f'{stem}.group_{target_id:03}.member_{sid:03}.pid_{pid}.wav'
        files[filename] = _pcm_wav_bytes(pcm, header_rate)
        rows.append(dict(original_sample_id=sid, target_sample_id=target_id, playback_id=pid,
            source_channel=getattr(native, 'source_channel', None),
            first_source_event_id=native.first_source_event_id,
            start_vgmticks=event['start_vgmticks'], end_vgmticks=event['end_vgmticks'],
            original_volume=event['original_volume'], target_volume=event['target_volume'],
            original_effective_gain=old_gain, target_effective_gain=new_gain,
            projection_status=status, use_count=len(members[sid]),
            rate_num=rate.numerator, rate_den=rate.denominator, wav_rate_hz=header_rate,
            wav_rate_error_hz=float(header_rate - rate),
            gate_frames=gate_frames, half_frames=frames, gap_frames=gap_frames,
            gate_frame_origin=gate_origin, source_gate_frames=source_gate_frames,
            source_gate_seconds=float(duration), target_gate_seconds=float(target_duration),
            clipped_to_preview_duration=frames < gate_frames,
            wav_half_seconds=frames / header_rate,
            wav_gate_error_seconds=float(Fraction(frames, header_rate) - target_duration),
            wav_source_gate_error_seconds=float(Fraction(frames, header_rate) - duration),
            sequence='original_decoded_then_silence_then_representative_decoded',
            amplitude='effective quantized onset gain; no normalization', file=filename,
            original_sha256=source_samples[sid].sha256, target_sha256=target_samples[target_id].sha256))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]) if rows else ('original_sample_id', 'target_sample_id'),
                            lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    files[stem + '.pairs.csv'] = stream.getvalue().encode('utf-8')
    # Validate ownership for every replacement/removal before mutating anything.
    for name in set(old) | set(files):
        path = _name(root, name)
        if path.exists() and (name not in old or _hash(path.read_bytes()) != old[name]):
            raise ValueError(f'Refusing to replace modified or unowned PCM merge output: {path}')
    result = dict(generator=GENERATOR, stem=stem, schema_version=1,
        directory=str(root), manifest_path=str(manifest_path), wav_count=len(rows),
        candidate_pair_count=len(order), omitted_preview_count=len(order) - len(rows), max_pairs=max_pairs,
        max_half_seconds=MAX_HALF_SECONDS, gap_seconds=float(GAP_SECONDS),
        listening_scope='A/B decoded target assets and quantized gains; not native audio or final driver playback',
        decoder_reset_assumption='predictor=-2, step_index=0, low nibble first, PCM16 scale64',
        selection='worst accepted waveform error, use count, sample ID; prefer retained event',
        pairs=rows, owned_files={name: _hash(data) for name, data in files.items()})
    for name, data in files.items():
        _name(root, name).write_bytes(data)
    for name in set(old) - set(files):
        _name(root, name).unlink(missing_ok=True)
    manifest_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result
