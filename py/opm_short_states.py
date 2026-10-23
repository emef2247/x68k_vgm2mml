"""MSX short-state selection adapted to ordinary OPM pitch/carrier-level runs.

Native evidence and key/control operations remain untouched. Unsupported state
changes are explicit barriers, rather than treated as disposable transients.
"""
from dataclasses import dataclass, replace
from fm_state_runs import select_state_runs, FM_SHORT_STATE_SAMPLES
from opm_performed_runs import HeldRun


@dataclass(frozen=True)
class PreparedStates:
    runs: tuple
    terminal_writes: tuple = ()


def prepare(writes, onset, off, state_at, tick, *, threshold=FM_SHORT_STATE_SAMPLES):
    from opm_mdx_music import tone_and_level, level_for_tone
    groups=[]
    for w in writes[onset:off]:
        if not groups or groups[-1][0].source_vgmticks != w.source_vgmticks:
            groups.append([])
        groups[-1].append(w)
    if not groups:
        return None, ()
    states=[state_at(group[-1]).state for group in groups]
    origin=tone_and_level(states[0])
    if origin is None:
        return None, ()
    tone=origin[0]
    first=states[0]
    def fixed(state):
        value=tone_and_level(state)
        return (value[0] if value else None,state.key_mask,state.left_enabled,
                state.right_enabled,state.pms,state.ams,state.shared_registers)
    reason=''
    for index,(group,state) in enumerate(zip(groups,states)):
        allowed={0x28+state_at(group[-1]).ch,0x30+state_at(group[-1]).ch}
        if fixed(state)!=fixed(first) or level_for_tone(state,tone) is None:
            reason='protected_tone_pan_or_nonuniform_level';break
        if any(w.register not in allowed and not 0x60<=w.register<0x80
               and not(index==0 and w is writes[onset]) for w in group):
            reason='protected_ordered_register_operation';break
    intervals=tuple((g[0].source_vgmticks,
        groups[i+1][0].source_vgmticks if i+1<len(groups) else writes[off].source_vgmticks,s)
        for i,(g,s) in enumerate(zip(groups,states)))
    if any(b==a for a,b,_ in intervals):
        reason='protected_zero_time_operation'
    protected=set(range(len(intervals))) if reason else {len(intervals)-1}
    keep,drop=select_state_runs(intervals,threshold,protected=protected)
    rows=tuple(dict(run_index=i,source_start_samples=a,source_end_samples=b,
        source_event_ids=tuple(w.source_event_id for w in groups[i]),
        action='omit_short_state' if i in drop else 'retain',
        reason=reason or ('source_duration_at_most_threshold' if i in drop else
            'release_tail_state' if i==len(intervals)-1 else 'retained_state'),
        threshold_samples=threshold,register='',data='',target_tick='',write_origin='')
        for i,(a,b,_) in enumerate(intervals)
        if b-a<=threshold or i in drop)
    if not drop:
        return None,rows
    result=[];level=None;terminal=[];terminal_rows=[]
    for n,i in enumerate(keep):
        a=intervals[0][0] if n==0 else intervals[i][0]
        b=intervals[keep[n+1]][0] if n+1<len(keep) else writes[off].source_vgmticks
        start,end=tick(a),tick(b)
        if end<=start:
            if i==keep[-1]:
                # Retain every original write at the release target tick. A
                # removed earlier state may also own a value absent from this
                # tail, so restore any remaining allowed-register differences.
                observed=dict(result[-1].state.channel_registers) if result else {}
                for w in writes[onset+1:off]:
                    if tick(w.source_vgmticks)!=end:
                        continue
                    terminal.append((w.register,w.data))
                    observed[w.register]=w.data
                    terminal_rows.append(dict(run_index=i,source_start_samples=w.source_vgmticks,
                        source_end_samples=w.source_vgmticks,source_event_ids=(w.source_event_id,),
                        action='retain_terminal_write',reason='release_state_at_zero_target_duration',
                        threshold_samples=threshold,register=w.register,data=w.data,
                        target_tick=end,write_origin='source_write'))
                ch=state_at(groups[-1][-1]).ch
                for reg,value in states[-1].channel_registers:
                    if (reg in (0x28+ch,0x30+ch) or 0x60<=reg<0x80) and observed.get(reg)!=value:
                        terminal.append((reg,value));observed[reg]=value
                        terminal_rows.append(dict(run_index=i,source_start_samples=writes[off].source_vgmticks,
                            source_end_samples=writes[off].source_vgmticks,
                            source_event_ids=tuple(w.source_event_id for w in writes[onset:off] if w.register==reg)[-1:],
                            action='restore_terminal_state',reason='omitted_state_value_needed_for_release',
                            threshold_samples=threshold,register=reg,data=value,
                            target_tick=end,write_origin='inferred_target_restore'))
            continue
        state=intervals[i][2];value=level_for_tone(state,tone)
        commands=() if not result or value==level else (f'@v{127-value}',)
        actions=() if not commands else (('volume',value),)
        result.append(HeldRun(start,end,state,commands,actions,
                             tuple(w.source_event_id for w in groups[i])))
        level=value
    if not result:
        return None,tuple(dict(row,action='not_applied',reason='no_positive_target_run')
                          if row['action']=='omit_short_state' else row for row in rows)
    # The original complete attack/release endpoints remain authoritative.
    result[0]=replace(result[0],start_tick=writes[onset].mdx_tick)
    result[-1]=replace(result[-1],end_tick=writes[off].mdx_tick)
    return PreparedStates(tuple(result),tuple(terminal)),rows+tuple(terminal_rows)
