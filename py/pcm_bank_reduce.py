"""Target-only approximate PCM bank reduction, preserving source evidence."""
from collections import Counter, defaultdict
from dataclasses import dataclass, fields, replace
from fractions import Fraction
import csv
import hashlib
import json
import math
from pathlib import Path

from msm6258 import PcmPlayback
from opna_adpcm import _msm_next
from pcm8_volume import MXDRV_PCM_LEVELS, PCM8_GAINS, project_pcm8_volume


# Experimental target policy. These figures are error bounds, not perceptual
# equivalence claims; user listening remains a separate validation step.
POLICY = dict(max_pitch_cents=100.0, max_relative_gain_error=0.20,
              max_envelope_error=0.20, max_attack_error=0.22,
              max_tail_energy=0.035, max_spectral_error=0.24,
              max_waveform_error=0.38, max_aligned_waveform_error=0.18,
              timbre_spectral_error=0.16, timbre_envelope_error=0.13,
              spectral_only_error=0.12, spectral_only_envelope_error=0.10,
              spectral_only_attack_error=0.15, temporal_spectral_error=0.18,
              long_phrase_seconds=1.0, long_phrase_waveform_error=0.08,
              comparison_alignment_samples=2)


@dataclass(frozen=True)
class ReducedPlayback(PcmPlayback):
    source_channel: int = 0
    target_volume: int = 128
    original_sample_id: int | None = None
    original_target_volume: int = 128


@dataclass(frozen=True)
class ReductionResult:
    analysis: object
    sample_rows: tuple[dict, ...]
    playback_rows: tuple[dict, ...]
    summary: dict

    def dump(self, outdir, stem):
        root = Path(outdir)
        root.mkdir(parents=True, exist_ok=True)
        for suffix, rows in (('samples', self.sample_rows), ('playbacks', self.playback_rows)):
            names = tuple(dict.fromkeys(key for row in rows for key in row))
            with (root / f'{stem}.pcm_bank_merge.{suffix}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=names or ('original_sample_id',))
                writer.writeheader()
                writer.writerows(rows)
        path = root / f'{stem}.pcm_bank_merge.json'
        path.write_text(json.dumps(dict(summary=self.summary), indent=2) + '\n', encoding='utf-8')
        return path


def _gain(raw):
    if not isinstance(raw, int) or not 128 <= raw <= 255:
        raise ValueError('PCM bank reduction requires direct MXDRV volume bytes 128..255')
    attenuation = raw & 127
    return PCM8_GAINS[MXDRV_PCM_LEVELS[attenuation]] / 80 if attenuation < len(MXDRV_PCM_LEVELS) else 0.0


def _decode(payload, np):
    audio = np.empty(2 * len(payload), dtype=np.float64)
    signal, index, position = -2, 0, 0
    for byte in payload:
        for nibble in (byte & 15, byte >> 4):
            signal, index = _msm_next(signal, index, nibble)
            audio[position] = signal * 64
            position += 1
    return audio


def _envelope(audio, np, bins=40):
    bounds = np.linspace(0, len(audio), bins + 1).astype(int)
    return np.array([math.sqrt(float(np.mean(audio[a:b] ** 2))) if b > a else 0.0
                     for a, b in zip(bounds, bounds[1:])])


def _relative(a, b, np):
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(a), 1.0))


def _spectrum(audio, rate, np):
    size = min(32768, max(256, len(audio)))
    positions = (np.linspace(0, len(audio) - size, min(4, 1 + len(audio) // size)).astype(int)
                 if len(audio) > size else [0])
    power = np.zeros(size // 2 + 1)
    for start in positions:
        power += abs(np.fft.rfft(audio[start:start + size], n=size)) ** 2
    frequency = np.fft.rfftfreq(size, 1 / rate)
    edges = np.geomspace(max(rate / size, 15), rate / 2 + 1, 65)
    bands = np.array([math.sqrt(float(power[(frequency >= lo) & (frequency < hi)].sum()))
                      for lo, hi in zip(edges, edges[1:])])
    # A hard log-band boundary must not turn a tiny detune into two unrelated
    # instruments. Tonal pitch is bounded separately before group acceptance.
    bands = np.convolve(bands, (0.25, 0.5, 0.25), mode='same')
    bands /= max(float(np.linalg.norm(bands)), 1.0)
    peak = int(np.argmax(power[1:])) + 1
    tonal = float(power[max(1, peak - 1):peak + 2].sum()) / max(float(power[1:].sum()), 1.0) > 0.32
    center = float(peak)
    if 0 < peak < len(power) - 1 and min(power[peak - 1:peak + 2]) > 0:
        a, b, c = np.log(power[peak - 1:peak + 2])
        denominator = a - 2 * b + c
        if denominator:
            center += float(np.clip(0.5 * (a - c) / denominator, -0.5, 0.5))
    return bands, (center * rate / size if tonal else None)


def _padded(audio, count, np):
    result = np.zeros(count)
    result[:min(count, len(audio))] = audio[:count]
    return result


def _metrics(original, representative, rate, np):
    count = max(len(original), len(representative), 1)
    x, y = _padded(original, count, np), _padded(representative, count, np)
    energy = max(float(x @ x), 1.0)
    env_x, env_y = _envelope(x, np), _envelope(y, np)
    spectrum_x, _ = _spectrum(x, rate, np)
    spectrum_y, _ = _spectrum(y, rate, np)
    attack = min(count, max(1, round(rate * 0.025)))
    return dict(waveform_error=_relative(x, y, np),
                spectral_error=float(np.linalg.norm(spectrum_x - spectrum_y)),
                envelope_error=_relative(env_x, env_y, np),
                attack_error=_relative(_envelope(x[:attack], np, 8), _envelope(y[:attack], np, 8), np),
                missing_tail_energy=float((x[len(representative):] ** 2).sum() / energy),
                extra_tail_energy=float((y[len(original):] ** 2).sum() / energy))


def _temporal_spectrum(original, representative, rate, np):
    count = max(len(original), len(representative), 1)
    x, y = _padded(original, count, np), _padded(representative, count, np)
    total = max(float(x @ x), float(y @ y), 1)
    boundaries = np.linspace(0, count, 5).astype(int)
    intervals = list(zip(boundaries, boundaries[1:]))
    intervals.append((0, min(count, max(1, round(rate * 0.025)))))
    worst = 0.0
    for start, stop in intervals:
        if stop <= start or max(float(x[start:stop] @ x[start:stop]),
                                float(y[start:stop] @ y[start:stop])) < total * 0.02:
            continue
        spec_x, _ = _spectrum(x[start:stop], rate, np)
        spec_y, _ = _spectrum(y[start:stop], rate, np)
        worst = max(worst, float(np.linalg.norm(spec_x - spec_y)))
    return worst


def _source_rates(analysis):
    """Use source rate ratios only for unambiguous equal-ROM source families."""
    candidates = defaultdict(set)
    for row in getattr(analysis, 'bank_assets', ()):
        identity = row
        if row.get('identity_json'):
            try:
                identity = json.loads(row['identity_json'])
            except (TypeError, ValueError):
                continue
        required = ('source_bytes_sha256', 'address_fixed', 'end_address_fixed', 'delta')
        if not all(key in identity for key in required):
            continue
        try:
            rate = (Fraction(identity['source_rate']) if 'source_rate' in identity else
                    Fraction(identity['source_rate_num'], identity['source_rate_den']))
            rate = rate * identity['delta'] / 256
            if rate <= 0:
                continue
            family = (identity['source_bytes_sha256'], identity['address_fixed'], identity['end_address_fixed'])
            candidates[row['sample_id']].add((family, rate))
        except (TypeError, ValueError, KeyError, ZeroDivisionError):
            continue
    return {sid: next(iter(values)) for sid, values in candidates.items() if len(values) == 1}


def _fit(original, representative, np, max_lag):
    """Discovery only: comparison offsets/warps never change output playback."""
    count = max(len(original), len(representative))
    positions = np.linspace(0, count - 1, min(count, 4096))
    x = np.interp(positions, np.arange(len(original)), original, left=0, right=0)
    energy = max(float(x @ x), 1.0)
    best = None
    for cents in (0, -25, 25, -50, 50, -75, 75, -100, 100):
        ratio = 2 ** (cents / 1200)
        for lag in range(-max_lag, max_lag + 1):
            y = np.interp((positions - lag) * ratio, np.arange(len(representative)),
                          representative, left=0, right=0)
            gain = max(0.0, float(x @ y) / max(float(y @ y), 1.0))
            error = math.sqrt(float(((x - y * gain) ** 2).sum()) / energy)
            candidate = error, abs(cents), abs(lag), gain, cents, lag
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    return dict(aligned_waveform_error=best[0], fitted_gain=best[3],
                comparison_pitch_cents=best[4], comparison_alignment_samples=best[5])


def _validate(analysis):
    samples = {s.sample_id: s for s in analysis.samples}
    if len(samples) != len(analysis.samples):
        raise ValueError('PCM reduction received duplicate sample IDs')
    if len({p.playback_id for p in analysis.playbacks}) != len(analysis.playbacks):
        raise ValueError('PCM reduction received duplicate playback IDs')
    for sample in analysis.samples:
        if sample.codec != 'msm6258-adpcm4-low-first':
            raise ValueError('PCM bank reduction requires MSM6258 low-nibble-first assets')
        if hashlib.sha256(sample.encoded_bytes).hexdigest() != sample.sha256:
            raise ValueError('PCM bank reduction received a sample hash mismatch')
        if not 1 <= len(sample.encoded_bytes) <= 0xffffff:
            raise ValueError('PCM bank reduction received an invalid encoded sample length')
    for p in analysis.playbacks:
        if p.sample_id is not None and p.sample_id not in samples:
            raise ValueError('PCM reduction received an unknown playback sample')
        if p.rate_num <= 0 or p.rate_den <= 0:
            raise ValueError('PCM bank reduction requires positive playback rates')
        _gain(getattr(p, 'target_volume', 128))


def _rejection(metrics, fit, seconds, *, spectral_only=False):
    if max(metrics['missing_tail_energy'], metrics['extra_tail_energy']) > POLICY['max_tail_energy']:
        return 'tail_energy'
    if metrics['envelope_error'] > POLICY['max_envelope_error']:
        return 'envelope'
    if metrics['attack_error'] > POLICY['max_attack_error']:
        return 'attack'
    if seconds > POLICY['long_phrase_seconds']:
        return 'long_phrase_waveform' if metrics['waveform_error'] > POLICY['long_phrase_waveform_error'] else None
    if metrics['spectral_error'] > POLICY['max_spectral_error']:
        return 'spectrum'
    if spectral_only:
        if not (metrics['spectral_error'] <= POLICY['spectral_only_error'] and
                metrics['envelope_error'] <= POLICY['spectral_only_envelope_error'] and
                metrics['attack_error'] <= POLICY['spectral_only_attack_error'] and
                metrics.get('temporal_spectral_error', float('inf')) <= POLICY['temporal_spectral_error']):
            return 'spectral_envelope'
        return None
    if metrics['waveform_error'] > POLICY['max_waveform_error']:
        if not (metrics['spectral_error'] <= POLICY['timbre_spectral_error'] and
                metrics['envelope_error'] <= POLICY['timbre_envelope_error'] and
                fit['aligned_waveform_error'] <= POLICY['max_aligned_waveform_error']):
            return 'decoded_waveform'
    return None


def reduce_bank(analysis, *, mode='budget96', omit_playback_ids=(), normalization_ms=8,
                tick_mapper=None, sample_multiplier=None):
    """Reduce a separate post-clock target view before slot/voice allocation.

    All representatives are existing immutable ADPCM assets. Every member is
    compared directly to its representative (no transitive clustering), and
    actual unshifted, unwarped decoded output with quantized gain is checked for
    every distinct affected gate/gain condition, including missing/extra tails.
    """
    if mode == 'budget96':
        strict = reduce_bank(analysis, mode='similar', omit_playback_ids=omit_playback_ids,
            normalization_ms=normalization_ms, tick_mapper=tick_mapper,
            sample_multiplier=sample_multiplier)
        from pcm_bank_budget import enforce_budget
        return enforce_budget(analysis, strict)
    if mode not in ('similar', 'off'):
        raise ValueError('PCM bank merge mode must be budget96, similar or off')
    if not math.isfinite(normalization_ms) or normalization_ms < 0:
        raise ValueError('PCM bank merge normalization bound must be finite and nonnegative')
    if sample_multiplier is not None:
        if not isinstance(sample_multiplier, int) or not 1 <= sample_multiplier <= 255:
            raise ValueError('PCM bank merge sample multiplier must be an integer 1..255')
        if tick_mapper is None:
            from opm_mdx import mdx_tick
            tick_mapper = lambda time: mdx_tick(time, sample_multiplier)
    elif tick_mapper is not None:
        raise ValueError('PCM bank merge tick mapper requires its MDX sample multiplier')
    _validate(analysis)
    samples = {s.sample_id: s for s in analysis.samples}
    requested_omissions = set(omit_playback_ids)
    omission_bound = int(Fraction(str(normalization_ms)) * Fraction(441, 10))
    omitted = {p.playback_id for p in analysis.playbacks if p.playback_id in requested_omissions
               and 0 < p.end_vgmticks - p.start_vgmticks <= omission_bound}

    def gate_frames(playback):
        if tick_mapper is None:
            count = Fraction(playback.end_vgmticks - playback.start_vgmticks, 44100) * playback.rate_hz
        else:
            ticks = tick_mapper(playback.end_vgmticks) - tick_mapper(playback.start_vgmticks)
            count = Fraction(ticks * sample_multiplier * 256, 1000000) * playback.rate_hz
        return max(0, -(-count.numerator // count.denominator))

    by_sample = defaultdict(list)
    for p in analysis.playbacks:
        if p.sample_id is not None and p.playback_id not in omitted:
            by_sample[p.sample_id].append(p)
    mapping = {sid: sid for sid in samples}
    volumes = {p.playback_id: getattr(p, 'target_volume', 128) for p in analysis.playbacks}
    decisions = {sid: dict(original_sample_id=sid, target_sample_id=sid,
        reason='disabled' if mode == 'off' else 'distinct_or_unmatched',
        use_count=len(by_sample[sid]), input_bytes=len(s.encoded_bytes),
        output_bytes=len(s.encoded_bytes), fitted_gain=1.0, comparison_pitch_cents=0,
        pitch_status='unchanged', comparison_alignment_samples=0) for sid, s in samples.items()}
    rejections, comparisons = Counter(), 0
    if mode == 'similar' and len(samples) > 1:
        try:
            import numpy as np
        except ImportError as exc:
            raise ValueError('Similar PCM bank reduction requires NumPy; install numpy or use --pcm-bank-merge off') from exc
        decoded = {sid: _decode(s.encoded_bytes, np) for sid, s in samples.items()}
        raw_waveforms = {}
        for row in getattr(analysis, 'bank_waveforms', ()):
            sid = row['sample_id']
            if sid in samples and sid not in raw_waveforms and len(row['samples']) == len(decoded[sid]):
                raw_waveforms[sid] = np.asarray(row['samples'], dtype=np.float64)
        original = {sid: raw_waveforms.get(sid, audio) for sid, audio in decoded.items()}
        known_source_rates = _source_rates(analysis)
        rates, descriptors = {}, {}
        for sid, audio in decoded.items():
            sample_rates = {p.rate_hz for p in by_sample[sid]}
            if len(sample_rates) != 1 or len(audio) < 8 or float(audio @ audio) < len(audio) * 64 ** 2:
                continue
            rate = float(next(iter(sample_rates)))
            rates[sid] = rate
            env = _envelope(audio, np)
            env /= max(float(np.linalg.norm(env)), 1)
            spectral, pitch = _spectrum(audio, rate, np)
            descriptors[sid] = env, spectral, pitch
        rank = sorted(rates, key=lambda sid: (-round(float(np.sqrt(np.mean(original[sid] ** 2))), -1),
                      -len(by_sample[sid]), len(samples[sid].encoded_bytes), sid))
        groups = {}
        for representative in rank:
            if mapping[representative] != representative:
                continue
            group_cents = groups[representative] = [0.0]
            for sid in rank:
                if sid == representative or mapping[sid] != sid or rates[sid] != rates[representative] or sid in groups:
                    continue
                a, b = decoded[sid], decoded[representative]
                if max(len(a), len(b)) / min(len(a), len(b)) > 1.15:
                    rejections['duration_screen'] += 1
                    continue
                env_a, spec_a, tone_a = descriptors[sid]
                env_b, spec_b, tone_b = descriptors[representative]
                if float(np.linalg.norm(env_a - env_b)) > 0.40 or float(np.linalg.norm(spec_a - spec_b)) > 0.55:
                    rejections['feature_screen'] += 1
                    continue
                comparisons += 1
                lag = min(POLICY['comparison_alignment_samples'], int(rates[sid] * normalization_ms / 1000))
                fit = _fit(original[sid], original[representative], np, lag)
                fit['predecode_waveform_error'] = fit['aligned_waveform_error'] if sid in raw_waveforms and representative in raw_waveforms else None
                native_a, native_b = known_source_rates.get(sid), known_source_rates.get(representative)
                known_family = native_a is not None and native_b is not None and native_a[0] == native_b[0]
                pitch = (1200 * math.log2(float(native_b[1] / native_a[1])) if known_family else
                         1200 * math.log2(tone_b / tone_a) if tone_a and tone_b else None)
                if pitch is not None and abs(pitch) > POLICY['max_pitch_cents'] + 1:
                    rejections['pitch'] += 1
                    continue
                cents = float(pitch if pitch is not None else fit['comparison_pitch_cents'])
                if max(*group_cents, cents) - min(*group_cents, cents) > POLICY['max_pitch_cents']:
                    rejections['group_pitch_spread'] += 1
                    continue
                gain = fit['fitted_gain']
                spectral_only = (fit['aligned_waveform_error'] > POLICY['max_aligned_waveform_error'] and
                                 max(len(a), len(b)) / rates[sid] <= POLICY['long_phrase_seconds'])
                if spectral_only:
                    # Correlation gain collapses toward zero for independent
                    # noise phases. Compare their energy ratio, then require
                    # stricter actual attack/envelope/temporal spectra below.
                    fit['waveform_fitted_gain'] = gain
                    gain = float(np.linalg.norm(original[sid]) / max(np.linalg.norm(original[representative]), 1))
                    fit['fitted_gain'] = gain
                fit['similarity_method'] = 'spectral_envelope' if spectral_only else 'waveform_gain_rate'
                if not gain > 0:
                    rejections['nonpositive_gain'] += 1
                    continue
                updates, worst, condition_cache, reason = {}, {}, {}, None
                for p in by_sample[sid]:
                    old = _gain(getattr(p, 'target_volume', 128))
                    desired = old * gain
                    if desired <= 0:
                        reason = 'silent_playback'
                        break
                    if desired > 1:
                        reason = 'gain_headroom'
                        break
                    volume = project_pcm8_volume(desired, source_scale=1)
                    gain_error = abs(volume.effective_gain - desired) / desired
                    if gain_error > POLICY['max_relative_gain_error']:
                        reason = 'gain_quantization'
                        break
                    count = gate_frames(p)
                    key = count, old, volume.raw_volume
                    if key not in condition_cache:
                        x, y = a[:count] * old, b[:count] * volume.effective_gain
                        condition_cache[key] = _metrics(x, y, rates[sid], np)
                        if spectral_only:
                            # Only candidates passing inexpensive actual metrics
                            # merit the additional short-window FFT evaluation.
                            preliminary = condition_cache[key]
                            if (preliminary['spectral_error'] <= POLICY['spectral_only_error'] and
                                    preliminary['envelope_error'] <= POLICY['spectral_only_envelope_error'] and
                                    preliminary['attack_error'] <= POLICY['spectral_only_attack_error'] and
                                    max(preliminary['missing_tail_energy'], preliminary['extra_tail_energy']) <= POLICY['max_tail_energy']):
                                preliminary['temporal_spectral_error'] = _temporal_spectrum(x, y, rates[sid], np)
                    metrics = condition_cache[key]
                    metrics['relative_gain_error'] = gain_error
                    for name, value in metrics.items():
                        worst[name] = max(worst.get(name, 0), abs(value))
                    reason = _rejection(metrics, fit, max(len(a), len(b)) / rates[sid], spectral_only=spectral_only)
                    if reason:
                        break
                    updates[p.playback_id] = volume.raw_volume
                if reason:
                    rejections[reason] += 1
                    continue
                mapping[sid] = representative
                volumes.update(updates)
                group_cents.append(cents)
                decisions[sid].update(target_sample_id=representative, reason='similar_existing_representative',
                    output_bytes=0, **fit, **worst, measured_pitch_cents=pitch,
                    pitch_status=('known_source_rate' if known_family else 'estimated_tonal' if pitch is not None else 'unknown_noise_or_complex'))
    result_playbacks, playback_rows = [], []
    for p in analysis.playbacks:
        old_id = p.sample_id
        target_id, raw = mapping.get(old_id, old_id), volumes[p.playback_id]
        if p.playback_id in omitted and target_id != old_id:
            # No omitted event may force an unvalidated gain. Preserve its asset
            # as needed; the downstream stage owns the actual omission.
            target_id = old_id
        values = {f.name: getattr(p, f.name) for f in fields(PcmPlayback)}
        values['sample_id'] = target_id
        if target_id != old_id:
            values['nominal_nibbles'] = 2 * len(samples[target_id].encoded_bytes)
        result_playbacks.append(ReducedPlayback(**values, source_channel=getattr(p, 'source_channel', 0),
            target_volume=raw, original_sample_id=old_id,
            original_target_volume=getattr(p, 'target_volume', 128)))
        playback_rows.append(dict(playback_id=p.playback_id, original_sample_id=old_id,
            target_sample_id=target_id, original_volume=getattr(p, 'target_volume', 128), target_volume=raw,
            original_effective_gain=_gain(getattr(p, 'target_volume', 128)),
            target_effective_gain=_gain(raw),
            desired_gain=(_gain(getattr(p, 'target_volume', 128)) * decisions[old_id]['fitted_gain']
                          if target_id != old_id else _gain(raw)),
            start_vgmticks=p.start_vgmticks, end_vgmticks=p.end_vgmticks,
            rate_num=p.rate_num, rate_den=p.rate_den, explicit_omission=p.playback_id in omitted,
            checked_gate_frames=gate_frames(p),
            merged=target_id != old_id))
    ids = set(mapping.values()) | {p.sample_id for p in result_playbacks if p.sample_id is not None}
    retained = tuple(s for s in analysis.samples if s.sample_id in ids)
    changed = sum(row['merged'] for row in playback_rows if not row['explicit_omission'])
    summary = dict(mode=mode, input_sample_count=len(samples), output_sample_count=len(retained),
        input_payload_bytes=sum(len(s.encoded_bytes) for s in analysis.samples),
        output_payload_bytes=sum(len(s.encoded_bytes) for s in retained),
        merged_sample_count=len(samples) - len(retained), merged_playback_count=changed,
        recovered_playback_count=None, final_capacity_evaluated=False,
        comparison_count=comparisons, rejection_counts=dict(rejections), policy=dict(POLICY),
        native_evidence_modified=False, playback_timing_modified=False,
        comparison_offsets_applied_to_output=False,
        gate_duration_basis='projected_mdx_clock' if tick_mapper is not None else 'source_time',
        sample_multiplier=sample_multiplier)
    error_names = ('waveform_error', 'spectral_error', 'envelope_error', 'attack_error',
                   'missing_tail_energy', 'extra_tail_energy', 'relative_gain_error',
                   'temporal_spectral_error')
    merged_rows = [row for row in decisions.values() if row['target_sample_id'] != row['original_sample_id']]
    summary['worst_errors'] = {name: max((row.get(name, 0) for row in merged_rows), default=0)
                               for name in error_names}
    summary['usage_weighted_errors'] = {name: (sum(row.get(name, 0) * row['use_count'] for row in merged_rows)
        / max(sum(row['use_count'] for row in merged_rows), 1)) for name in error_names}
    summary['similarity_methods'] = dict(Counter(row.get('similarity_method', 'unchanged') for row in merged_rows))
    target = replace(analysis, samples=retained, playbacks=tuple(result_playbacks))
    if changed and hasattr(analysis, 'target_evidence'):
        evidence = dict(criterion='transcoding', status='lossy', code='pcm_similar_bank_reduction',
            detail='Existing sample representatives share quantized onset gains; approximate waveform/timbre projection',
            cause='target_projection', fallback='explicit_similar_bank_projection',
            source_value=len(samples), projected_value=len(retained))
        target = replace(target, target_evidence=(*analysis.target_evidence, evidence))
    return ReductionResult(target, tuple(decisions.values()), tuple(playback_rows), summary)
