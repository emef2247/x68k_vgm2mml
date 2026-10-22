"""Bounded, explicitly lossy target sample-bank replacement.

Similarity is an acceptance test; this stage is a capacity policy. It keeps
existing assets and all events, but deliberately permits errors beyond the
similarity bounds. Native sample and playback evidence is never rewritten.
"""
from collections import Counter
from dataclasses import replace
import math


from pcm_capacity import (SLOT_LIMIT, MAX_SAMPLE_BYTES, PDX_BYTE_LIMIT,
                          PDX_TABLE_BYTES, packed_pdx_bytes)
AC_NOISE_FLOOR = 128.0


def _ac_peak(audio, np):
    return float(np.ptp(audio)) / 2 if len(audio) else 0.0


def _features(audio, np, spectrum, envelope):
    spectral, pitch = spectrum(audio, 15625, np)
    env = envelope(audio, np, bins=20)
    env /= max(float(np.linalg.norm(env)), 1)
    duration = math.log2(max(1, len(audio)))
    return np.concatenate((spectral * 2, env, [duration * .25])), pitch


def _select(distance, weights, count, np, costs=None, byte_budget=None):
    """Cover weighted demand using existing assets within slot and byte limits.

    Only feasible columns compete at each step. The first representative
    minimizes total distance; later representatives maximize coverage gain.
    Equal scores retain deterministic candidate order.
    """
    nearest = np.full(distance.shape[0], float('inf'))
    selected = []
    available = np.ones(distance.shape[1], dtype=bool)
    costs = np.asarray(costs if costs is not None else [0] * distance.shape[1])
    remaining = byte_budget if byte_budget is not None else float('inf')
    for _ in range(min(count, distance.shape[1])):
        feasible = available & (costs <= remaining)
        if not np.any(feasible):
            break
        if not selected:
            score = (distance * weights[:, None]).sum(axis=0)
            score[~feasible] = float('inf')
            choice = int(np.argmin(score))
        else:
            benefit = (np.maximum(nearest[:, None] - distance, 0) * weights[:, None]).sum(axis=0)
            benefit[~feasible] = -1
            choice = int(np.argmax(benefit))
        selected.append(choice)
        remaining -= int(costs[choice])
        available[choice] = False
        nearest = np.minimum(nearest, distance[:, choice])
    return selected


def _reserve_representative(selected, representative, samples):
    """Repair onset coverage without exceeding either target capacity."""
    selected = [sid for sid in selected if sid != representative]
    while (len(selected) >= SLOT_LIMIT or
           PDX_TABLE_BYTES + len(samples[representative].encoded_bytes) +
           sum(len(samples[sid].encoded_bytes) for sid in selected) > PDX_BYTE_LIMIT):
        if not selected:
            raise ValueError('PCM budget96 has no representative within the PDX byte limit')
        selected.pop()
    return sorted([*selected, representative])


def enforce_budget(original, strict):
    # Imported lazily to let reduce_bank dispatch without a circular module
    # initialization dependency, and to keep <=96/disabled paths lightweight.
    from pcm_bank_reduce import (ReductionResult, ReducedPlayback, _decode,
        _envelope, _gain, _metrics, _spectrum, POLICY)
    from pcm8_volume import project_pcm8_volume

    source = {s.sample_id: s for s in original.samples}
    strict_samples = {s.sample_id: s for s in strict.analysis.samples}
    playback_rows = {r['playback_id']: dict(r) for r in strict.playback_rows}
    original_events = {p.playback_id: p for p in original.playbacks}
    referenced = {p.sample_id for p in strict.analysis.playbacks if p.sample_id is not None}
    active = Counter(p.sample_id for p in strict.analysis.playbacks
                     if p.sample_id is not None and not playback_rows[p.playback_id]['explicit_omission'])
    candidates = sorted(sid for sid in referenced
                        if len(strict_samples[sid].encoded_bytes) <= MAX_SAMPLE_BYTES)
    summary = dict(strict.summary)
    summary.update(mode='budget96', budget_limit=SLOT_LIMIT,
        budget_byte_limit=PDX_BYTE_LIMIT,
        budget_input_pdx_bytes=packed_pdx_bytes(strict_samples[sid] for sid in referenced),
        budget_input_sample_count=len(referenced), forced_sample_count=0,
        forced_playback_count=0, budget_selection_method='weighted_facility_coverage',
        slot_budget_satisfied=True, unused_sample_count=len(strict_samples) - len(referenced))
    if (len(referenced) <= SLOT_LIMIT and len(candidates) == len(referenced)
            and summary['budget_input_pdx_bytes'] <= PDX_BYTE_LIMIT):
        target = replace(strict.analysis, samples=tuple(s for s in strict.analysis.samples
                                                       if s.sample_id in referenced))
        summary.update(output_sample_count=len(target.samples),
            output_payload_bytes=sum(len(s.encoded_bytes) for s in target.samples),
            budget_output_pdx_bytes=packed_pdx_bytes(target.samples), byte_budget_satisfied=True,
            merged_sample_count=len(original.samples) - len(target.samples), forced_worst_errors={})
        rows = tuple(dict(row, target_sample_id=None, reason='unused_target_asset', output_bytes=0)
                     if row['target_sample_id'] not in referenced else row
                     for row in strict.sample_rows)
        return ReductionResult(target, rows, strict.playback_rows, summary)
    if not candidates:
        raise ValueError('PCM budget96 has no existing independently playable sample within the 65535-byte target limit')
    try:
        import numpy as np
    except ImportError as exc:
        raise ValueError('PCM budget96 requires NumPy; install numpy or use --pcm-bank-merge off') from exc

    decoded = {sid: _decode(sample.encoded_bytes, np) for sid, sample in source.items()}
    norms = {sid: float(np.linalg.norm(audio)) for sid, audio in decoded.items()}
    features, pitches = {}, {}
    for sid, audio in decoded.items():
        features[sid], pitches[sid] = _features(audio, np, _spectrum, _envelope)
    demands = sorted(referenced)
    demand_features = np.asarray([features[sid] for sid in demands])
    candidate_features = np.asarray([features[sid] for sid in candidates])
    distance = np.sqrt(np.maximum(0, ((demand_features[:, None, :] - candidate_features[None, :, :]) ** 2).sum(axis=2)))
    weights = np.asarray([max(1, active[sid]) for sid in demands], dtype=float)
    selected_indices = _select(distance, weights, SLOT_LIMIT, np,
        costs=[len(strict_samples[sid].encoded_bytes) for sid in candidates],
        byte_budget=PDX_BYTE_LIMIT - PDX_TABLE_BYTES)
    selected = sorted(candidates[index] for index in selected_indices)
    required_gates = {}
    for p in original.playbacks:
        if p.sample_id is None or playback_rows[p.playback_id]['explicit_omission']:
            continue
        count = playback_rows[p.playback_id]['checked_gate_frames']
        if _ac_peak(decoded[p.sample_id][:count], np) * _gain(getattr(p, 'target_volume', 128)) > AC_NOISE_FLOOR:
            required_gates.setdefault(p.sample_id, []).append(count)
    if required_gates:
        earliest_gate = min(min(counts) for counts in required_gates.values())
        if not any(_ac_peak(decoded[sid][:earliest_gate], np) > AC_NOISE_FLOOR for sid in selected):
            onset_candidates = [sid for sid in source if len(source[sid].encoded_bytes) <= MAX_SAMPLE_BYTES
                                and _ac_peak(decoded[sid][:earliest_gate], np) > AC_NOISE_FLOOR]
            if not onset_candidates:
                raise ValueError('PCM budget96 has no bounded representative audible within the earliest active gate')
            representative = max(onset_candidates,
                key=lambda sid: (_ac_peak(decoded[sid][:earliest_gate], np), -sid))
            selected = _reserve_representative(selected, representative, source)
    audible_candidates = [sid for sid in candidates if norms[sid] > 0]
    if audible_candidates and not any(sid in audible_candidates for sid in selected):
        representative = max(audible_candidates, key=lambda sid: (active[sid], -sid))
        selected = _reserve_representative(selected, representative, source)
    selected_set = set(selected)
    accepted_mapping = {p.sample_id: old.sample_id
        for p, old in zip(original.playbacks, strict.analysis.playbacks)
        if old.sample_id in selected_set and not playback_rows[p.playback_id]['explicit_omission']}
    target_for = {}
    for sid in source:
        # Direct original-to-final comparison below, including members of a
        # strict group whose representative lost its slot. Never compose gains
        # through an intermediate representative.
        eligible = [rep for rep in selected if norms[rep] > 0]
        if sid in required_gates:
            eligible = [rep for rep in eligible
                        if all(_ac_peak(decoded[rep][:count], np) > AC_NOISE_FLOOR
                               for count in required_gates[sid])]
            if not eligible:
                raise ValueError('PCM budget96 could not preserve an audible gate onset')
        if norms[sid] == 0 or not eligible:
            eligible = selected
        accepted = accepted_mapping.get(sid)
        target_for[sid] = (accepted if accepted in eligible else sid if sid in eligible else min(eligible,
            key=lambda rep: (float(np.linalg.norm(features[sid] - features[rep])), rep)))
    sample_rows = {row['original_sample_id']: dict(row) for row in strict.sample_rows}
    forced_ids, errors, metric_cache = set(), {}, {}
    result_events, result_rows = [], []
    for previous in strict.analysis.playbacks:
        p = original_events[previous.playback_id]
        row = playback_rows[p.playback_id]
        old_id, old_raw = p.sample_id, getattr(p, 'target_volume', 128)
        if old_id is None:
            result_events.append(previous)
            result_rows.append(row)
            continue
        # Keep already accepted strict substitution when its final asset is
        # retained. That substitution was evaluated directly from the source.
        if (previous.sample_id in selected_set and
                (old_id not in required_gates or all(
                    _ac_peak(decoded[previous.sample_id][:count], np) > AC_NOISE_FLOOR
                    for count in required_gates[old_id])) and
                (not row['explicit_omission'] or previous.sample_id == target_for[old_id])):
            rep, raw = previous.sample_id, previous.target_volume
            result_events.append(previous)
            result_rows.append(row)
            target_for[old_id] = rep
            continue
        rep = target_for[old_id]
        count = row['checked_gate_frames']
        a, b = decoded[old_id][:count], decoded[rep][:count]
        gain_before = _gain(old_raw)
        rms_a = float(np.linalg.norm(a))
        rms_b = float(np.linalg.norm(b))
        ac_a, ac_b = _ac_peak(a, np), _ac_peak(b, np)
        fitted = rms_a / rms_b if rms_b > 0 else 1.0
        desired = gain_before * fitted
        bounded = min(1.0, max(0.0, desired))
        volume = project_pcm8_volume(bounded, source_scale=1)
        raw = volume.raw_volume if volume.raw_volume is not None else 255
        effective = _gain(raw)
        audibility_lifted = ac_a * gain_before > AC_NOISE_FLOOR and ac_b * effective <= AC_NOISE_FLOOR
        if audibility_lifted:
            # Capacity priority may accept a quieter/different timbre, but a
            # DC prefix or quantization step must not erase an audible attack.
            raw, effective = 128, 1.0
        key = old_id, rep, count, old_raw, raw, p.rate_num, p.rate_den
        if key not in metric_cache:
            metric_cache[key] = _metrics(a * gain_before, b * effective, float(p.rate_hz), np)
        metrics = metric_cache[key]
        relative_gain_error = abs(effective - desired) / max(desired, 1e-12)
        forced = not row['explicit_omission']
        if forced:
            forced_ids.add(old_id)
            for name, value in dict(metrics, relative_gain_error=relative_gain_error).items():
                errors[name] = max(errors.get(name, 0), value)
        pitch_a, pitch_b = pitches[old_id], pitches[rep]
        pitch = 1200 * math.log2(pitch_b / pitch_a) if pitch_a and pitch_b else None
        diagnostics = dict(reason='budget96_closest_existing_representative' if forced else 'normalization_omitted_target_reference',
            similarity_method='forced_budget96', budget_forced=forced,
            fitted_gain=fitted, desired_gain=desired, target_effective_gain=effective,
            gain_headroom_clamped=desired > 1, relative_gain_error=relative_gain_error,
            audibility_gain_lifted=audibility_lifted,
            measured_pitch_cents=pitch,
            pitch_status='estimated_tonal_unbounded' if pitch is not None else 'unknown_noise_or_complex',
            similarity_bounds_enforced=False, **metrics)
        row.update(target_sample_id=rep, target_volume=raw, original_volume=old_raw,
            original_effective_gain=gain_before, merged=rep != old_id, **diagnostics)
        result_rows.append(row)
        result_events.append(replace(previous, sample_id=rep, target_volume=raw,
            nominal_nibbles=len(source[rep].encoded_bytes) * 2,
            original_sample_id=old_id, original_target_volume=old_raw))
        sr = sample_rows[old_id]
        for name in ('aligned_waveform_error', 'predecode_waveform_error',
                     'comparison_pitch_cents', 'comparison_alignment_samples',
                     'waveform_fitted_gain', 'temporal_spectral_error'):
            if name in sr:
                sr['similar_phase_' + name] = sr.pop(name)
        previous_errors = {name: sr.get(name, 0) for name in metrics}
        sr.update(target_sample_id=rep, output_bytes=0, **diagnostics)
        for name in metrics:
            sr[name] = max(sr[name], previous_errors[name])
    # Unused original assets keep an inspectable mapping but cannot occupy a
    # target slot. Omitted event IDs also reference an actual final sample.
    actual_mapping = {r['original_sample_id']: r['target_sample_id'] for r in result_rows
                      if r['original_sample_id'] is not None}
    for sid, row in sample_rows.items():
        rep = actual_mapping.get(sid)
        row['target_sample_id'] = rep
        row['output_bytes'] = len(source[sid].encoded_bytes) if sid in selected_set else 0
        if sid not in actual_mapping:
            row.update(reason='unused_target_asset', budget_forced=False)
    target = replace(strict.analysis, samples=tuple(source[sid] for sid in selected),
                     playbacks=tuple(result_events))
    if hasattr(target, 'target_evidence'):
        target = replace(target, target_evidence=(*target.target_evidence, dict(
            criterion='capacity', status='lossy', code='pcm_budget96_replacement',
            detail='Slot and PDX byte limits take priority over timbre, pitch, gain and tail similarity; inspect merge diagnostics',
            cause='target_projection', fallback='closest_existing_sample',
            source_value=len(referenced), projected_value=len(selected))))
    summary.update(output_sample_count=len(selected),
        output_payload_bytes=sum(len(s.encoded_bytes) for s in target.samples),
        budget_output_pdx_bytes=packed_pdx_bytes(target.samples), byte_budget_satisfied=True,
        merged_sample_count=len(source) - len(selected),
        merged_playback_count=sum(r['merged'] and not r['explicit_omission'] for r in result_rows),
        forced_sample_count=len(forced_ids),
        forced_playback_count=sum(r.get('budget_forced', False) for r in result_rows),
        forced_worst_errors=errors, budget_similarity_bounds_enforced=False,
        budget_max_sample_bytes=MAX_SAMPLE_BYTES)
    assert len(target.samples) <= SLOT_LIMIT
    assert packed_pdx_bytes(target.samples) <= PDX_BYTE_LIMIT
    assert {p.sample_id for p in target.playbacks if p.sample_id is not None} <= selected_set
    return ReductionResult(target, tuple(sample_rows.values()), tuple(result_rows), summary)
