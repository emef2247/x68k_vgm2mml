"""SN76489 (DCSG) Segments -> rendered waveform -> MSM6258 bridge (S4).

The OPN2 route's companion chip has no FM home on the OPM: FM takes
six of the eight channels and the DCSG wants three tone lanes plus
noise. S4 therefore renders the DCSG to the PCM side. This module
synthesizes the mix from the dcsg module's control Segments — the
analysis layer deliberately holds no oscillator phase, so phase is
rebuilt here, per channel, running continuously across sounding
segments. When a tone channel returns from silence its phase
restarts at zero: a square wave's absolute phase is not audible,
and canonical run starts let identical phrases deduplicate to one
sample, as repeated DAC runs do on the S3 bridge.

- Tones: square wave at the segment's frequency, amplitude from the
  SN76489 attenuation law (2 dB per step, so 10 ** (-att / 10)).
- Noise: the LFSR with the header-declared feedback mask and shift
  width, clocked at the segment's noise shift rate (which already
  encodes the tone-2-coupled mode); white vs periodic follows the
  noise control bit, and the register's noise resets re-seed it.
- Stereo masks fold to mono: a segment enabled on either side
  renders at full amplitude (the MSM6258 side is mono).

Slicing, resampling, ADPCM encoding and playback construction
mirror the DAC bridge (opn2_pcm.project_dac): the rendered waveform
is split at silence gaps over 10 ms and at the replayed song-loop
boundary, each run is resampled to the PCM profile rate with the
same centered linear interpolation, encoded as MSM6258 ADPCM and
deduplicated by waveform hash.
"""
import hashlib
import json
from array import array
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import csv

from msm6258 import PcmAnalysis, PcmPlayback, PcmSample, TransferLog
from opna_adpcm import encode_msm6258
from pcm_profiles import get_profile

RUN_GAP_SAMPLES = 441
_BASE_AMPLITUDE = 24576


@dataclass(frozen=True)
class Opn2DcsgAnalysis(PcmAnalysis):
    source_origin: str = 'projected_msm6258_from_opn2_dcsg'
    pcm_profile: str = 'standard'
    dcsg_event_rows: tuple[dict, ...] = ()
    dcsg_stats: dict | None = None

    def dump(self, outdir, stem):
        super().dump(outdir, stem)
        root = Path(outdir)
        with (root / f'{stem}.opn2_dcsg.events.csv').open(
                'w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(self.dcsg_event_rows[0])
                if self.dcsg_event_rows else ['run_index'])
            writer.writeheader()
            writer.writerows(self.dcsg_event_rows)
        path = root / f'{stem}.pcm_source.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report.update(source_origin=self.source_origin,
                      consumption_origin='rendered_sn76489_segments',
                      pcm_profile=self.pcm_profile,
                      opn2_dcsg=self.dcsg_stats)
        path.write_text(json.dumps(report, indent=2) + '\n',
                        encoding='utf-8')


def _amplitude(attenuation):
    return round(_BASE_AMPLITUDE * 10 ** (-attenuation / 10))


def render_dcsg_wave(analysis, source_end):
    """Render the instance-0 DCSG mix to a 44.1 kHz int16 waveform.

    Returns (wave, stats). Only segments the analysis marks audible
    sound; spans whose state is unknown stay silent, as the analysis
    records them.
    """
    mix = array('i', bytes(4 * source_end))
    stats = dict(audible_samples=0, clipped_samples=0,
                 stereo_folded_segments=0, dual_chip_audible_samples=0,
                 noise_unrenderable_samples=0)
    config = analysis.config
    by_channel = {}
    for segment in analysis.segments:
        if segment.chip_instance != 0:
            if segment.audible:
                stats['dual_chip_audible_samples'] += segment.length_samples
            continue
        by_channel.setdefault(segment.ch, []).append(segment)
    for channel, segments in by_channel.items():
        segments.sort(key=lambda s: s.start_sample)
        if channel < 3:
            _render_tone_channel(mix, segments, stats)
        else:
            _render_noise_channel(mix, segments, config, stats)
    wave = array('h', bytes(2 * source_end))
    clipped = 0
    for index, value in enumerate(mix):
        if value > 32767:
            wave[index] = 32767
            clipped += 1
        elif value < -32768:
            wave[index] = -32768
            clipped += 1
        else:
            wave[index] = value
    stats['clipped_samples'] = clipped
    return wave, stats


def _render_tone_channel(mix, segments, stats):
    phase = 0.0
    sounding = False
    for segment in segments:
        length = segment.length_samples
        if length <= 0:
            continue
        frequency = segment.frequency_hz
        if frequency is None:
            sounding = False
            continue
        step = frequency / 44100.0
        start = segment.start_sample
        if not segment.audible or segment.attenuation is None:
            sounding = False
            continue
        if not sounding:
            phase = 0.0
            stats['phase_resets'] = stats.get('phase_resets', 0) + 1
        sounding = True
        if segment.stereo_left != segment.stereo_right:
            stats['stereo_folded_segments'] += 1
        stats['audible_samples'] += length
        amplitude = _amplitude(segment.attenuation)
        for offset in range(length):
            mix[start + offset] += amplitude if phase % 1.0 < 0.5 else -amplitude
            phase += step


def _render_noise_channel(mix, segments, config, stats):
    width = config.shift_width
    seed = 1 << (width - 1)
    lfsr = seed
    shift_phase = 0.0
    previous_resets = None
    for segment in segments:
        length = segment.length_samples
        if length <= 0:
            continue
        if previous_resets is None or segment.noise_reset_count != previous_resets:
            lfsr = seed
            shift_phase = 0.0
        previous_resets = segment.noise_reset_count
        rate = segment.noise_shift_hz
        if rate is None or segment.noise_control is None:
            if segment.audible:
                stats['noise_unrenderable_samples'] += length
            continue
        if not segment.audible or segment.attenuation is None:
            continue
        if segment.stereo_left != segment.stereo_right:
            stats['stereo_folded_segments'] += 1
        stats['audible_samples'] += length
        amplitude = _amplitude(segment.attenuation)
        white = bool(segment.noise_control & 0x04)
        step = rate / 44100.0
        start = segment.start_sample
        for offset in range(length):
            mix[start + offset] += amplitude if lfsr & 1 else -amplitude
            shift_phase += step
            while shift_phase >= 1.0:
                shift_phase -= 1.0
                if white:
                    feedback = bin(lfsr & config.feedback).count('1') & 1
                else:
                    feedback = lfsr & 1
                lfsr = (lfsr >> 1) | (feedback << (width - 1))


def _event_id_lookup(dcsg_analysis):
    spans = sorted((s.start_sample, s.end_sample, s.source_event_id)
                   for s in dcsg_analysis.segments
                   if s.source_event_id is not None)

    def lookup(tick):
        result = 0
        for start, end, event_id in spans:
            if start > tick:
                break
            if start <= tick < end:
                result = event_id
        return result

    return lookup


def _slice_runs(wave, source_end, loop_start):
    """Nonzero spans of a rendered wave, split at silence gaps over
    RUN_GAP_SAMPLES and at the replayed song-loop boundary."""
    runs = []
    index = 0
    while index < source_end:
        if wave[index] == 0:
            index += 1
            continue
        start = index
        last_nonzero = index
        index += 1
        while index < source_end:
            if loop_start is not None and start < loop_start <= index:
                break
            if wave[index] != 0:
                last_nonzero = index
            elif index - last_nonzero > RUN_GAP_SAMPLES:
                break
            index += 1
        runs.append((start, last_nonzero + 1))
    return runs


def _bridge_from_wave(wave, *, source_end, loop_start, pcm_profile, lookup):
    """Slice a rendered wave into ADPCM samples and playbacks.

    Mirrors opn2_pcm.project_dac's per-run construction: centered
    linear resampling to the profile rate, MSM6258 encoding, and
    deduplication by waveform hash.
    """
    profile = get_profile(pcm_profile)
    stats = dict(runs=0, playbacks=0, unique_samples=0,
                 subsample_runs_dropped=0)
    runs = _slice_runs(wave, source_end, loop_start)
    stats['runs'] = len(runs)
    samples = []
    sample_ids = {}
    playbacks = []
    event_rows = []
    for run_index, (start, stop) in enumerate(runs):
        if stop - start < 2:
            stats['subsample_runs_dropped'] += 1
            event_rows.append(dict(
                run_index=run_index, start_vgmticks=start, end_vgmticks=stop,
                first_source_event_id=lookup(start),
                last_source_event_id=lookup(stop - 1), sample_id='',
                termination='subsample_dropped'))
            continue
        run_wave = wave[start:stop]
        count = max(2, 2 * round(Fraction(len(run_wave), 1) / 44100
                                 * profile.rate / 2))
        resampled = array('h')
        ratio = Fraction(44100, 1) / profile.rate
        for position_index in range(count):
            position = max(Fraction(0),
                           Fraction(2 * position_index + 1, 2) * ratio
                           - Fraction(1, 2))
            low = min(len(run_wave) - 1,
                      position.numerator // position.denominator)
            high = min(len(run_wave) - 1, low + 1)
            fraction = position - position.numerator // position.denominator
            resampled.append(round(run_wave[low] * (1 - fraction)
                                   + run_wave[high] * fraction))
        key = hashlib.sha256(resampled.tobytes()).hexdigest()
        if key not in sample_ids:
            encoded, _error = encode_msm6258(resampled)
            sample_ids[key] = len(samples)
            samples.append(PcmSample(len(samples), 'msm6258-adpcm4-low-first',
                                     encoded,
                                     hashlib.sha256(encoded).hexdigest()))
        sample_id = sample_ids[key]
        consumed = min(count, round(Fraction(stop - start, 44100)
                                     * profile.rate))
        termination = ('song_end' if run_index == len(runs) - 1
                       and stop >= source_end else 'gap')
        playbacks.append(PcmPlayback(
            len(playbacks), 0, sample_id, start, stop,
            lookup(start), lookup(stop - 1), 0, 0, 0,
            profile.mdx_clock_hz, profile.mdx_divider,
            profile.rate.numerator, profile.rate.denominator,
            0, False, True,
            'projected_independent_pdx_decoder_assumption',
            termination, True, True, count, consumed, (), ()))
        event_rows.append(dict(
            run_index=run_index, start_vgmticks=start, end_vgmticks=stop,
            first_source_event_id=lookup(start),
            last_source_event_id=lookup(stop - 1), sample_id=sample_id,
            termination=termination))
    stats['playbacks'] = len(playbacks)
    stats['unique_samples'] = len(samples)
    return profile, samples, playbacks, event_rows, stats


def project_dcsg(raw, dcsg_analysis, *, source_end, loop_start=None,
                 loop_count=1, pcm_profile='standard', dcsg_gain=0.145):
    """Build the MSM6258 analysis for a song's SN76489 (DCSG) traffic.

    The DCSG waveform is rendered from the native Segments and split
    into playbacks at silence gaps over 10 ms; runs also split at the
    replayed song-loop boundary, matching the DAC bridge.
    ``dcsg_gain`` is the mapping-stage bridge balance, the same
    factor the combined DAC+DCSG bridge applies to its DCSG element.
    """
    wave, stats = render_dcsg_wave(dcsg_analysis, source_end)
    if dcsg_gain != 1.0:
        wave = [max(-32768, min(32767, round(value * dcsg_gain)))
                for value in wave]
    profile, samples, playbacks, event_rows, bridge_stats = _bridge_from_wave(
        wave, source_end=source_end, loop_start=loop_start,
        pcm_profile=pcm_profile, lookup=_event_id_lookup(dcsg_analysis))
    stats.update(bridge_stats, profile=pcm_profile, dcsg_gain=dcsg_gain)
    return Opn2DcsgAnalysis(
        source_end, tuple(samples), tuple(playbacks), (), (),
        TransferLog(b''), (), bytes(raw), profile.mdx_clock_hz, 4,
        'rendered SN76489 segments; native evidence retained in the '
        'DCSG analysis dump', loop_start, (),
        observations=(), loop_count=loop_count, pcm_profile=profile.name,
        dcsg_event_rows=tuple(event_rows), dcsg_stats=stats)


@dataclass(frozen=True)
class Opn2CombinedAnalysis(PcmAnalysis):
    source_origin: str = 'projected_msm6258_from_opn2_dac_dcsg'
    pcm_profile: str = 'standard'
    dcsg_event_rows: tuple[dict, ...] = ()
    dcsg_stats: dict | None = None
    dac_stats: dict | None = None

    def dump(self, outdir, stem):
        super().dump(outdir, stem)
        root = Path(outdir)
        with (root / f'{stem}.opn2_dcsg.events.csv').open(
                'w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(self.dcsg_event_rows[0])
                if self.dcsg_event_rows else ['run_index'])
            writer.writeheader()
            writer.writerows(self.dcsg_event_rows)
        path = root / f'{stem}.pcm_source.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report.update(source_origin=self.source_origin,
                      consumption_origin='mixed_opn2_dac_and_sn76489_segments',
                      pcm_profile=self.pcm_profile,
                      opn2_dac=self.dac_stats,
                      opn2_dcsg=self.dcsg_stats)
        path.write_text(json.dumps(report, indent=2) + '\n',
                        encoding='utf-8')


def project_combined(raw, events, analysis, dcsg_analysis, *,
                     loop_start=None, loop_count=1, pcm_profile='standard',
                     dac_gain=0.5, dcsg_gain=0.145):
    """Build one MSM6258 analysis for DAC playback mixed with DCSG.

    The MSM6258 side has a single stream, and in real Mega Drive
    material the DAC and the DCSG sound together most of the time,
    so neither can simply win the channel: the decoded DAC waveform
    and the rendered DCSG mix are summed first (the gains are the
    mapping-stage balance), and the mix is sliced and encoded once.
    """
    from opn2_pcm import dac_waveform
    source_end = analysis.source_end_vgmticks
    dac_wave, issues, dac_stats, dac_spans = dac_waveform(
        raw, events, analysis, loop_start=loop_start)
    dcsg_wave, render_stats = render_dcsg_wave(dcsg_analysis, source_end)
    wave = array('h', bytes(2 * source_end))
    clipped = 0
    for index in range(source_end):
        value = round(dac_wave[index] * dac_gain
                      + dcsg_wave[index] * dcsg_gain)
        if value > 32767:
            wave[index] = 32767
            clipped += 1
        elif value < -32768:
            wave[index] = -32768
            clipped += 1
        else:
            wave[index] = value
    segment_lookup = _event_id_lookup(dcsg_analysis)
    span_starts = [span[0] for span in dac_spans]

    def lookup(tick):
        from bisect import bisect_right
        index = bisect_right(span_starts, tick) - 1
        if index >= 0 and dac_spans[index][0] <= tick < dac_spans[index][1]:
            span = dac_spans[index]
            return span[2] if tick - span[0] <= span[1] - tick else span[3]
        return segment_lookup(tick)

    profile, samples, playbacks, event_rows, bridge_stats = _bridge_from_wave(
        wave, source_end=source_end, loop_start=loop_start,
        pcm_profile=pcm_profile, lookup=lookup)
    dac_stats = dict(dac_stats, combined_playbacks=bridge_stats['playbacks'],
                     combined_unique_samples=bridge_stats['unique_samples'])
    dcsg_stats = dict(render_stats, **bridge_stats, profile=pcm_profile,
                      dac_gain=dac_gain, dcsg_gain=dcsg_gain,
                      mix_clipped_samples=clipped, combined=True)
    return Opn2CombinedAnalysis(
        source_end, tuple(samples), tuple(playbacks), (), (),
        TransferLog(b''), (), bytes(raw), profile.mdx_clock_hz, 4,
        'mixed YM2612 DAC waveform and rendered SN76489 segments; '
        'native evidence retained in the source analyses',
        loop_start, (), observations=tuple(issues),
        loop_count=loop_count, pcm_profile=profile.name,
        dcsg_event_rows=tuple(event_rows), dcsg_stats=dcsg_stats,
        dac_stats=dac_stats)
