"""Optional target-clock correction from OPM attacks; source evidence is immutable."""
from dataclasses import asdict
from types import SimpleNamespace

from note_normalization import infer_timing
from opm_mdx import mdx_tick, projected_samples, project_segments, MDX_SAMPLE_NUMERATOR, MDX_SAMPLE_DENOMINATOR


def normalize_projection(segments, original, *, loop_metadata=None):
    """Reuse MGSDRV clock fitting to nominate an actual MDX timer lattice.

    MDX controls use nearest *absolute* ticks on that lattice. We do not apply
    MGSDRV onset snapping, gate inference, phase shifts or short-state pruning.
    Every positive source interval must survive; rejection affects the whole song.
    """
    segments = tuple(segments)
    channels = {ch: [] for ch in range(8)}
    for segment in segments:
        if segment.rising_mask:
            channels[segment.ch].append(SimpleNamespace(vgmticks=segment.vgmticks, key_on_edge=True))
    plan = infer_timing(channels)
    report = dict(status='unchanged', reason='no confident shared clock',
                  source_segments_unchanged=True, source_origin_samples=0,
                  method='shared MGSDRV clock fit nominates MDX timer; absolute nearest-tick projection',
                  before=original.timing_report())
    if plan is None:
        return original, report, []
    report['fitted_clock'] = asdict(plan)
    multiplier = round(plan.samples_per_step * MDX_SAMPLE_DENOMINATOR / MDX_SAMPLE_NUMERATOR)
    report['nominated_multiplier'] = multiplier
    if not 1 <= multiplier <= 255:
        report['reason'] = 'inferred clock is outside the MDX timer range'
        return original, report, []
    candidate = project_segments(segments, end_vgmticks=original.source_end_vgmticks,
                                 sample_multiplier=multiplier)
    report['candidate'] = candidate.timing_report()
    report['correction_bound_samples'] = plan.tolerance_samples
    loop = loop_metadata or {}
    if loop.get('loop_offset') and loop.get('status') != 'valid':
        report['reason'] = 'declared source loop boundary is not valid'
        report['source_loop'] = loop
        return original, report, []
    labels = {0: {'origin'}, original.source_end_vgmticks: {'source_end'}}
    for segment in segments:
        labels.setdefault(segment.vgmticks, set()).add('segment_start')
        labels.setdefault(segment.vgmticks_end, set()).add('segment_end')
        if segment.rising_mask or segment.falling_mask:
            labels[segment.vgmticks].add('key_edge')
    for write in original.writes:
        labels.setdefault(write.source_vgmticks, set()).add('control')
    event_ids = {}
    for write in original.writes:
        event_ids.setdefault(write.source_vgmticks, []).append(write.source_event_id)
    if loop.get('status') == 'valid':
        start, end = loop['loop_start_samples'], loop['decoded_end_samples']
        if start is None or end is None or not 0 <= start < end <= original.source_end_vgmticks:
            report['reason'] = 'declared source loop has no positive bounded interval'
            report['source_loop'] = loop
            return original, report, []
        labels.setdefault(start, set()).add('loop_start')
        labels.setdefault(end, set()).add('loop_end')
    times = sorted(labels)
    ticks = {sample: mdx_tick(sample, multiplier) for sample in times}
    errors = {sample: projected_samples(ticks[sample], multiplier) - sample for sample in times}
    worst = max(times, key=lambda t: abs(errors[t]))
    report['worst_boundary'] = dict(source_samples=worst, candidate_tick=ticks[worst],
                                  error_samples=errors[worst], boundary_kinds=sorted(labels[worst]),
                                  source_event_ids=event_ids.get(worst, []))
    collisions = [dict(source_start_samples=a, source_end_samples=b, candidate_tick=ticks[a],
                       start_kinds=sorted(labels[a]), end_kinds=sorted(labels[b]),
                       start_event_ids=event_ids.get(a, []), end_event_ids=event_ids.get(b, []))
                  for a, b in zip(times, times[1:]) if ticks[a] == ticks[b]]
    report['collapsed_positive_intervals'] = len(collisions)
    report['first_collisions'] = collisions[:10]
    report['max_abs_correction_samples'] = abs(errors[worst])
    if abs(errors[worst]) > plan.tolerance_samples:
        report['reason'] = 'an actual MDX boundary correction exceeds the fitted tolerance'
    elif collisions:
        report['reason'] = 'the nominated MDX clock would collapse a positive source interval'
    else:
        report.update(status='applied', reason='all control, key, Segment, end and loop boundaries remain bounded and ordered')
    selected = candidate if report['status'] == 'applied' else original
    if loop.get('status') == 'valid':
        report['source_loop'] = dict(start_samples=start, end_samples=end,
                                    candidate_start_tick=ticks[start], candidate_end_tick=ticks[end])
    evidence = []
    for before, after in zip(original.writes, candidate.writes):
        evidence.append(dict(source_event_id=before.source_event_id,
                             source_segment_ids=list(before.source_segment_ids),
                             source_samples=before.source_vgmticks, register=before.register, data=before.data,
                             before_tick=before.mdx_tick, before_projected_samples=before.projected_vgmticks,
                             candidate_tick=after.mdx_tick, candidate_projected_samples=after.projected_vgmticks,
                             candidate_error_samples=after.projected_vgmticks - after.source_vgmticks,
                             projection_status=report['status']))
    for sample in times:
        if labels[sample].intersection({'source_end', 'loop_start', 'loop_end'}):
            evidence.append(dict(source_event_id=None, source_segment_ids=[], source_samples=sample,
                                 register=None, data=None, before_tick=original.mdx_tick(sample),
                                 before_projected_samples=original.projected_samples(original.mdx_tick(sample)),
                                 candidate_tick=ticks[sample], candidate_projected_samples=projected_samples(ticks[sample], multiplier),
                                 candidate_error_samples=errors[sample], projection_status=report['status'],
                                 boundary_kinds=sorted(labels[sample])))
    return selected, report, evidence
