"""Scoped fixed-level noise-only projection; never a waveform/phase identity.

Nominal shift rates follow MAME AY and YMFM OPM divider models. N31 is excluded
as a conservative target policy, not asserted as a settled hardware property.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class NoiseVoice:
    identity: str = 'psg_opm_noise_only'
    model: str = 'noise-only'
    algorithm: int = 7
    feedback: int = 0
    operator_muls: tuple = (1,1,1,1)
    operator_tl: tuple = (127,127,127,None)


def candidates(segments,*,end=None):
    from psg_note_units import interval_end
    return [ch for ch,rows in sorted(segments.items()) if any(
        s.mode==2 and s.volume and not s.envelope_enabled
        and s.vgmticks is not None and interval_end(rows,index,end)>s.vgmticks
        for index,s in enumerate(rows))]


def rate(clock,period,target_clock=4000000):
    if clock<=0:raise ValueError('Noise projection needs a positive effective source clock')
    source=clock/(16*max(1,period))
    choices=[(abs(math.log2((target_clock/(32*(32-n)))/source)),n,
              target_clock/(32*(32-n))) for n in range(31)]
    _,n,actual=min(choices)
    return n,source,actual,1200*math.log2(actual/source)
