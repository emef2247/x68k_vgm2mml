"""Onset amplitude projection for the inspected MXDRV/PCM8 compatibility profile.

The direct MDX volume byte is an attenuation index, not linear amplitude.
Tables were checked against MXDRV2.06+17 Rel.X5-S PCMVolumeTable and
X68Sound PCM8VOLTBL; this profile is code-derived, not hardware calibration.
Held-note volume changes require a separate target capability.
"""
from dataclasses import dataclass
from fractions import Fraction
import math


COMPATIBILITY_PROFILE = 'mxdrv206_17_x5s_x68sound_pcm8'
PCM8_GAINS = (2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80)
MXDRV_PCM_LEVELS = (
    15, 15, 15, 14, 14, 14, 13, 13, 13, 12, 12, 11, 11, 11, 10, 10,
    10, 9, 9, 8, 8, 8, 7, 7, 7, 6, 6, 5, 5, 5, 4, 4,
    4, 3, 3, 2, 2, 2, 1, 1, 1, 0, 0,
)


@dataclass(frozen=True)
class Pcm8Volume:
    source_level: float
    source_scale: float
    desired_gain: float
    effective_gain: float
    gain_error: float
    absolute_gain_error: float
    raw_volume: int | None
    pcm8_level: int | None
    attenuation: int | None
    silent: bool
    compatibility_profile: str = COMPATIBILITY_PROFILE


def project_pcm8_volume(source_level, *, source_scale=128):
    """Quantize an onset gain, retaining a shared scale across reusable assets.

    Zero returns ``silent=True`` with no volume byte: the caller must omit or
    explicitly mute that playback, then restore routing for the next attack.
    PCM8 level zero itself has nonzero gain (2/80). Positive values choose the
    nearest nonzero gain, with a quieter tie-break. No implicit clipping occurs.
    """
    try:
        finite = math.isfinite(source_level) and math.isfinite(source_scale)
        level, scale = Fraction(source_level), Fraction(source_scale)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError('PCM8 source level and scale must be finite numbers') from exc
    if not finite or scale <= 0 or level < 0 or level > scale:
        raise ValueError('PCM8 source level must be between zero and a positive finite scale')
    desired = level / scale
    if level == 0:
        return Pcm8Volume(float(level), float(scale), 0.0, 0.0, 0.0, 0.0,
                          None, None, None, True)
    index = min(range(len(PCM8_GAINS)),
                key=lambda i: (abs(Fraction(PCM8_GAINS[i], 80) - desired), PCM8_GAINS[i]))
    effective = Fraction(PCM8_GAINS[index], 80)
    attenuation = MXDRV_PCM_LEVELS.index(index)
    error = effective - desired
    return Pcm8Volume(float(level), float(scale), float(desired), float(effective),
                      float(error), float(abs(error)), 128 | attenuation, index,
                      attenuation, False)
