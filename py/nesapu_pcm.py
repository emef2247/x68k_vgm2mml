"""NES DPCM -> MSM6258 ADPCM bridge for the MDX target.

The shared NES projection renders DPCM as 1/60 s SCC waveform slices
because the MSX standard configuration has no PCM target. The X68000
does have one (MSM6258 ADPCM via PDX), so this bridge takes the DPCM
part over from the NES analysis instead: each covered sample is
decoded once, resampled to the PCM profile rate, encoded as MSM6258
ADPCM, and every trigger becomes an independent PDX playback on the
same timeline the projection uses for the intermediate VGM. The
projection is asked to keep the slices off the SCC lane in this case
(nesapu_projection.project(..., dpcm_external=True)).

Fidelity notes, all recorded in the analysis dump:
- A sample asset is decoded from the output level of its first
  trigger with that (address, length, rate); later triggers at other
  levels reuse the asset, so the small waveform drift a retrigger at
  a different counter level would cause is not reproduced.
- Looped samples are baked: the decoded level sequence is continued
  across loop wraps (the counter state carries over) until it covers
  the audible span, capped; a capped asset falls silent early.
- The mapping balance gain for DPCM, when enabled, is baked into the
  waveform amplitude before encoding, like the PSG PCM bridge.
"""
import hashlib
import math
from array import array
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import csv
import json

from msm6258 import (PcmAnalysis, PcmIssue, PcmPlayback, PcmSample,
                     TransferLog)
from nesapu import DMC_RATE_PERIODS, _decode_dpcm, _sample_memory
from opna_adpcm import encode_msm6258
from pcm_profiles import get_profile

# DMC output level 0..127 -> signed PCM amplitude before the balance
# gain: (level - 63.5) * 200 peaks near +/-12700 of int16 full scale.
_PCM_SCALE = 200
_MAX_LOOP_REPETITIONS = 4096


@dataclass(frozen=True)
class NesDpcmAnalysis(PcmAnalysis):
    source_origin: str = 'projected_msm6258_from_nes_dpcm'
    pcm_profile: str = 'standard'
    dpcm_event_rows: tuple[dict, ...] = ()
    dpcm_stats: dict | None = None

    def dump(self, outdir, stem):
        super().dump(outdir, stem)
        root = Path(outdir)
        with (root / f'{stem}.nes_dpcm.events.csv').open(
                'w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(self.dpcm_event_rows[0])
                if self.dpcm_event_rows else ['event_index'])
            writer.writeheader()
            writer.writerows(self.dpcm_event_rows)
        path = root / f'{stem}.pcm_source.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report.update(source_origin=self.source_origin,
                      consumption_origin='derived_nes_dpcm_samples',
                      pcm_profile=self.pcm_profile,
                      nes_dpcm=self.dpcm_stats)
        path.write_text(json.dumps(report, indent=2) + '\n',
                        encoding='utf-8')


def _addresses(event):
    return [event.address + i if event.address + i <= 0xffff
            else 0x8000 + event.address + i - 0x10000
            for i in range(event.length_bytes)]


def covered_event_indexes(trace, source_raw):
    """Indexes of DPCM events whose sample range has any data coverage.

    Mirrors the projection's slice rule: an event renders when at
    least one of its sample addresses is covered by a data block.
    """
    _, covered = _sample_memory(source_raw)
    return tuple(index for index, event in enumerate(trace.dpcm_events)
                 if any(at in covered for at in _addresses(event)))


def project(trace, *, source_raw, loop_point=None, loop_start=None,
            expanded_end=None, loop_count=1, pcm_profile='standard',
            gain=1.0):
    """Build the ADPCM analysis for a NES trace's DPCM part.

    Loop coordinates follow the downstream replayed timeline:
    loop_point is the first-traversal loop start in the trace's own
    ticks, loop_start is where the replay begins in the expanded
    timeline (it becomes source_loop_vgmticks), and expanded_end is
    the expanded source end. All three are None for an unlooped song.
    """
    if not math.isfinite(gain) or gain <= 0:
        raise ValueError('NES DPCM gain must be positive and finite')
    profile = get_profile(pcm_profile)
    memory, covered = _sample_memory(source_raw)
    events = trace.dpcm_events
    disables = sorted(w.vgmticks for w in trace.writes
                      if w.register == 21 and not w.value & 16)
    end = trace.source_end_vgmticks
    covered_indexes = set(covered_event_indexes(trace, source_raw))

    decoded = {}
    assets = {}
    samples = []
    playbacks = []
    event_rows = []
    issues = []
    stats = dict(events=len(events), covered_events=len(covered_indexes),
                 uncovered_events=len(events) - len(covered_indexes),
                 playbacks=0, unique_samples=0, loop_repetitions_capped=0,
                 gain=gain, profile=pcm_profile)

    def asset_for(event, repetitions):
        key = (event.address, event.length_bytes, event.level,
               event.rate_index, repetitions)
        if key in assets:
            return assets[key]
        decode_key = (event.address, event.length_bytes, event.level)
        if decode_key not in decoded:
            data = bytes(memory.get(at, 0) for at in _addresses(event))
            decoded[decode_key] = _decode_dpcm(data, event.level)
        levels = decoded[decode_key]
        wave = array('h')
        level = event.level
        sequence = levels
        for pass_index in range(repetitions):
            if pass_index:
                data = bytes(memory.get(at, 0)
                             for at in _addresses(event))
                sequence = _decode_dpcm(data, level)
            for value in sequence:
                level = value
                amplitude = round((value - 63.5) * _PCM_SCALE * gain)
                wave.append(max(-32768, min(32767, amplitude)))
        rate = Fraction(trace.clock_hz,
                        DMC_RATE_PERIODS[event.rate_index])
        count = max(2, 2 * round(Fraction(len(wave), 1) / rate
                                 * profile.rate / 2))
        resampled = array('h')
        ratio = rate / profile.rate
        for index in range(count):
            position = max(Fraction(0),
                           Fraction(2 * index + 1, 2) * ratio
                           - Fraction(1, 2))
            low = min(len(wave) - 1,
                      position.numerator // position.denominator)
            high = min(len(wave) - 1, low + 1)
            fraction = position - position.numerator // position.denominator
            resampled.append(round(wave[low] * (1 - fraction)
                                   + wave[high] * fraction))
        encoded, _error = encode_msm6258(resampled)
        sample_id = len(samples)
        samples.append(PcmSample(sample_id, 'msm6258-adpcm4-low-first',
                                 encoded,
                                 hashlib.sha256(encoded).hexdigest()))
        assets[key] = (sample_id, count)
        return assets[key]

    indexed = list(enumerate(events))
    passes = [(0, indexed, disables)]
    total_end = end
    if (loop_point is not None and loop_start is not None
            and expanded_end is not None and loop_count > 1
            and expanded_end > end and loop_start > loop_point):
        offset = loop_start - loop_point
        passes.append((offset,
                       [(i, e) for i, e in indexed
                        if e.vgmticks >= loop_point],
                       tuple(t for t in disables if t >= loop_point)))
        total_end = expanded_end

    for offset, pass_events, pass_disables in passes:
        for position, (index, event) in enumerate(pass_events):
            start = event.vgmticks + offset
            rate_hz = Fraction(trace.clock_hz,
                               DMC_RATE_PERIODS[event.rate_index])
            total_bits = event.length_bytes * 8
            natural_end = start + round(
                Fraction(total_bits * 44100, 1) / rate_hz)
            cut = end + offset
            termination = 'song_end'
            if position + 1 < len(pass_events):
                next_start = (pass_events[position + 1][1].vgmticks
                              + offset)
                if next_start < cut:
                    cut, termination = next_start, 'retrigger'
            for at in pass_disables:
                if start < at + offset < cut:
                    cut, termination = at + offset, 'disabled'
                    break
            stop = cut if event.loop else min(natural_end, cut)
            if not event.loop and natural_end <= cut:
                termination = 'sample_end'
            if stop <= start:
                continue
            if index not in covered_indexes:
                event_rows.append(dict(
                    event_index=index, pass_offset=offset,
                    start_vgmticks=start, end_vgmticks=stop,
                    sample_id='', termination=termination,
                    covered=False, repetitions=0))
                continue
            repetitions = 1
            if event.loop:
                natural_ticks = max(1, natural_end - start)
                repetitions = min(
                    _MAX_LOOP_REPETITIONS,
                    max(1, math.ceil((stop - start) / natural_ticks)))
                if repetitions == _MAX_LOOP_REPETITIONS:
                    stats['loop_repetitions_capped'] += 1
            sample_id, count = asset_for(event, repetitions)
            consumed = min(count, round(
                Fraction(stop - start, 44100) * profile.rate))
            playbacks.append(PcmPlayback(
                len(playbacks), 0, sample_id, start, stop,
                index, index, 0, 0, 0,
                profile.mdx_clock_hz, profile.mdx_divider,
                profile.rate.numerator, profile.rate.denominator,
                0, False, True,
                'projected_independent_pdx_decoder_assumption',
                termination, True, True, count, consumed, (), ()))
            event_rows.append(dict(
                event_index=index, pass_offset=offset,
                start_vgmticks=start, end_vgmticks=stop,
                sample_id=sample_id, termination=termination,
                covered=True, repetitions=repetitions))
    stats['playbacks'] = len(playbacks)
    stats['unique_samples'] = len(samples)
    if stats['uncovered_events']:
        issues.append(PcmIssue(
            'nes_dpcm_trigger_without_sample_data', None, 0,
            f"{stats['uncovered_events']} DPCM trigger(s) have no "
            'sample data coverage; they stay silent, as in the slice '
            'rendering'))
    if stats['loop_repetitions_capped']:
        issues.append(PcmIssue(
            'nes_dpcm_loop_repetitions_capped', None, 0,
            'a looped DPCM sample hit the repetition cap and will '
            'fall silent before its gate ends'))
    return NesDpcmAnalysis(
        total_end, tuple(samples), tuple(playbacks), (), tuple(issues),
        TransferLog(b''), (), bytes(source_raw), profile.mdx_clock_hz, 4,
        'derived NES DPCM samples; native evidence retained in the '
        'NES analysis dump', loop_start, (),
        loop_count=loop_count, pcm_profile=profile.name,
        dpcm_event_rows=tuple(event_rows), dpcm_stats=stats)
