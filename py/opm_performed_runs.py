"""Canonical positive held-note runs, separate from native OPM evidence.

Like the MSX performed-note grouping, harmless source partitioning does not
change equality. Ordered controls are barriers, not disposable short states.
"""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class HeldRun:
    start_tick: int
    end_tick: int
    state: object
    commands: tuple = ()
    actions: tuple = ()
    source_event_ids: tuple = ()

    @property
    def key(self):
        return self.end_tick - self.start_tick, self.state, self.actions


def coalesce(runs):
    """Join equal adjacent positive states only when no new action intervenes."""
    result, membership, sources = [], [], []
    for run in runs:
        if run.end_tick <= run.start_tick:
            raise ValueError('Performed held runs must have positive duration')
        merged = bool(result and result[-1].end_tick == run.start_tick
                      and result[-1].state == run.state and not run.actions
                      and not run.commands)
        if merged:
            previous = result[-1]
            result[-1] = replace(previous, end_tick=run.end_tick)
            sources[-1].extend(run.source_event_ids)
        else:
            result.append(run)
            sources.append(list(run.source_event_ids))
        membership.append((len(result) - 1, merged))
    return tuple(replace(run,source_event_ids=tuple(ids)) for run,ids in zip(result,sources)), tuple(membership)
