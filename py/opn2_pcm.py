"""YM2612 DAC -> MSM6258 ADPCM bridge for the MDX target.

The YM2612 sample channel is a DAC fed raw 8-bit PCM. Two encodings
carry it in VGM rips, and this bridge decodes both into one byte
timeline before anything is resampled:

- direct writes to register 0x2A while the DAC is enabled (0x2B bit
  7); the analysis retains them as unmodeled dac_data writes and its
  channel-6 segments carry the enable spans.
- DAC stream commands: data blocks (type 0x00, concatenated into one
  bank in order of appearance), stream setup (0x90-0x92), autonomous
  starts (0x93, frequency-driven, expanded with the same 32.32 phase
  model as py/pcm_stream.py), fast-call starts (0x95), seeks (0xE0)
  and manual play commands (0x80-0x8F, one byte each, timed by their
  own waits). A 0x95 start only arms the manual context; it does not
  auto-play. Seeks are absolute offsets into the concatenated bank
  (libvgm behavior). Some rips use seeks/plays with no setup commands
  at all; those bind to one implicit context over the same bank.
  Bytes sharing one 44.1 kHz tick collapse to the last value (finer
  timing is below the tick grid), and runs shorter than two ticks
  cannot sound and are dropped, both with counts retained.

Direct 0x2A writes outside a DAC-enabled span make no sound and are
dropped, with counts retained. Stream supplies are not gated by the
enable state: rips that encode samples as streams treat the stream
itself as the playback intent (Time Trax streams 850k bytes with the
enable bit never set), so gating them would silence the very content
the stream exists to carry. The audible byte timeline is split into playbacks
at gaps over 10 ms; each playback's bytes are held at the 44.1 kHz
source rate, resampled to the PCM profile rate with the NES bridge's
centered linear interpolation, encoded as MSM6258 ADPCM, and
deduplicated by waveform hash. Loop coordinates arrive already
expanded by the caller's loop_count=2 event pass, so second
traversals re-emit playbacks that reuse the same samples.
"""
import hashlib
import json
from array import array
from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import csv

from msm6258 import PcmAnalysis, PcmIssue, PcmPlayback, PcmSample, TransferLog
from opna_adpcm import encode_msm6258
from pcm_profiles import get_profile

# A gap longer than this between DAC bytes ends a playback (10 ms;
# the write cadence inside a playback run is far denser). Mirrors
# opn2_source.DAC_RUN_GAP_SAMPLES.
RUN_GAP_SAMPLES = 441
_ONE = 1 << 32


@dataclass(frozen=True)
class Opn2DacAnalysis(PcmAnalysis):
    source_origin: str = 'projected_msm6258_from_opn2_dac'
    pcm_profile: str = 'standard'
    dac_event_rows: tuple[dict, ...] = ()
    dac_stats: dict | None = None

    def dump(self, outdir, stem):
        super().dump(outdir, stem)
        root = Path(outdir)
        with (root / f'{stem}.opn2_dac.events.csv').open(
                'w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(self.dac_event_rows[0])
                if self.dac_event_rows else ['run_index'])
            writer.writeheader()
            writer.writerows(self.dac_event_rows)
        path = root / f'{stem}.pcm_source.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report.update(source_origin=self.source_origin,
                      consumption_origin='derived_opn2_dac_samples',
                      pcm_profile=self.pcm_profile,
                      opn2_dac=self.dac_stats)
        path.write_text(json.dumps(report, indent=2) + '\n',
                        encoding='utf-8')


def _enabled_spans(analysis):
    return [(segment.vgmticks, segment.vgmticks_end)
            for segment in analysis.segments
            if segment.ch == 5 and segment.state.dac_enabled == 1]


def _decode_stream_bytes(raw, events):
    """Expand DAC stream commands into (tick, byte, event_id) supplies.

    Returns (supplies, issues, stats). Supplies are autonomous-start
    expansions plus manual 0x80-0x8F plays, in event order.
    """
    bank = bytearray()
    blocks = []          # (bank_offset, length) per type-0 block
    streams = {}         # sid -> state dict
    quick = None         # stream state armed by 0x95 for 0x8n/0xE0
    implicit = None      # fallback context for setup-less seek/play use
    supplies = []
    issues = []
    stats = dict(stream_setup_commands=0, stream_starts=0,
                 stream_fast_starts=0, seek_commands=0, play_commands=0,
                 autonomous_bytes=0, manual_bytes=0, data_blocks=0,
                 data_block_bytes=0, implicit_stream=False)
    cursor = 0           # autonomous expansion frontier (vgmticks)

    def bind_quick(event_id, tick):
        """Resolve the manual play/seek context, implicitly if needed.

        Some rips drive 0xE0/0x8n with no stream setup commands at
        all; the only consistent reading is a single context over the
        concatenated DAC bank, positioned by the seeks.
        """
        nonlocal quick, implicit
        if quick is not None:
            return quick
        candidates = [s for s in streams.values() if s.get('valid')]
        if len(candidates) == 1:
            quick = candidates[0]
            return quick
        if implicit is None:
            implicit = dict(offset=None, index=0, step=1)
            stats['implicit_stream'] = True
            issue('opn2_dac_implicit_stream_context', event_id, tick,
                  'DAC seek/play commands appear with no stream setup; '
                  'binding them to the concatenated type-0 data bank')
        quick = implicit
        return quick

    def issue(code, event_id, tick, detail):
        issues.append(PcmIssue(code, event_id, tick, detail))

    def advance(end):
        """Emit autonomous supplies with tick < end, libvgm phase model."""
        nonlocal cursor
        ready = []
        for order, (sid, stream) in enumerate(streams.items()):
            if not stream.get('running'):
                continue
            frequency = stream['frequency']
            increment = (frequency * _ONE + 22050) // 44100
            local = cursor
            while local < end and stream['running']:
                steps = max(1, (_ONE - stream['phase'] + increment - 1) // increment)
                if steps > end - local:
                    stream['phase'] += (end - local) * increment
                    break
                stream['phase'] += steps * increment - _ONE
                tick = local + steps - 1
                bank_offset = stream['offset'] + stream['index'] * stream['step']
                if not 0 <= bank_offset < len(bank):
                    issue('opn2_dac_stream_out_of_bank', stream['start_event'], tick,
                          f'Stream {sid} left its data bank during autonomous playback')
                    stream['running'] = False
                    break
                ready.append((tick, order, stream['start_event'], bank[bank_offset]))
                stream['index'] += 1
                if stream['index'] == stream['count']:
                    stream['running'] = False
                local += steps
        ready.sort(key=lambda item: item[:2])
        supplies.extend((tick, byte, event_id) for tick, _, event_id, byte in ready)
        stats['autonomous_bytes'] += len(ready)
        cursor = end

    for event_id, event in enumerate(events):
        advance(event.vgmticks)
        cmd, pos, tick = event.command, event.address, event.vgmticks
        if cmd == 0x67:
            if event.loop_iteration:
                continue
            kind = raw[pos + 2]
            size = int.from_bytes(raw[pos + 3:pos + 7], 'little') & 0x7fffffff
            if kind == 0:
                blocks.append((len(bank), size))
                bank.extend(raw[pos + 7:pos + 7 + size])
                stats['data_blocks'] += 1
                stats['data_block_bytes'] += size
            continue
        if cmd in (0x52, 0x53, 0xa2, 0xa3):
            continue
        if 0x90 <= cmd <= 0x95:
            sid = raw[pos + 1]
            if sid == 255:
                if cmd == 0x94:
                    for stream in streams.values():
                        stream['running'] = False
                continue
            if cmd == 0x90:
                target, port, reg = raw[pos + 2:pos + 5]
                stream = streams.setdefault(sid, dict(
                    bank=None, step=None, base=None, frequency=None,
                    offset=None, count=None, phase=0, index=0, running=False))
                stream.update(valid=(target & 0x7f) == 2 and reg == 0x2a,
                              instance=bool(target & 0x80))
                stats['stream_setup_commands'] += 1
                if not stream['valid']:
                    issue('opn2_dac_stream_unsupported_target', event_id, tick,
                          f'Stream {sid} target {target:#x} port {port} register {reg:#x} '
                          'is not the YM2612 DAC register')
                continue
            stream = streams.get(sid)
            if stream is None:
                issue('opn2_dac_stream_configuration_incomplete', event_id, tick,
                      f'Stream {sid} has no setup command')
                continue
            if cmd == 0x91:
                bank_id, step, base = raw[pos + 2:pos + 5]
                stream.update(bank=bank_id, step=step or 1, base=base)
                if bank_id != 0:
                    issue('opn2_dac_stream_unsupported_bank', event_id, tick,
                          f'Stream {sid} selects data bank {bank_id:#x}; only the '
                          'YM2612 DAC bank (type 0x00) is decoded')
                    stream['usable'] = False
                else:
                    stream['usable'] = True
            elif cmd == 0x92:
                stream['frequency'] = int.from_bytes(raw[pos + 2:pos + 6], 'little')
            elif cmd == 0x94:
                stream['running'] = False
            elif cmd in (0x93, 0x95):
                stream['running'] = False
                if not stream.get('valid') or not stream.get('usable', True):
                    continue
                if cmd == 0x95:
                    block_index = int.from_bytes(raw[pos + 2:pos + 4], 'little')
                    flags = raw[pos + 4]
                    stats['stream_fast_starts'] += 1
                    if flags:
                        issue('opn2_dac_stream_flags_unsupported', event_id, tick,
                              f'Stream {sid} fast start flags {flags:#x} are not '
                              'modeled; the start position is still used')
                    if block_index >= len(blocks):
                        issue('opn2_dac_stream_out_of_bank', event_id, tick,
                              f'Stream {sid} fast start block {block_index} is not present')
                        continue
                    offset, _length = blocks[block_index]
                    stream.update(offset=offset + (stream['base'] or 0), index=0)
                    quick = stream
                else:
                    stats['stream_starts'] += 1
                    if any(stream[key] is None for key in ('bank', 'frequency')):
                        issue('opn2_dac_stream_configuration_incomplete', event_id, tick,
                              f'Stream {sid} start requires data and frequency configuration')
                        continue
                    if not stream['frequency'] or stream['frequency'] > 44100:
                        issue('opn2_dac_stream_frequency_unsupported', event_id, tick,
                              f'Stream {sid} frequency {stream["frequency"]} cannot be '
                              'scheduled on the 44.1 kHz tick grid')
                        continue
                    offset = int.from_bytes(raw[pos + 2:pos + 6], 'little')
                    mode = raw[pos + 6]
                    length = int.from_bytes(raw[pos + 7:pos + 11], 'little')
                    if offset == 0xffffffff:
                        if stream['offset'] is None:
                            issue('opn2_dac_stream_configuration_incomplete', event_id, tick,
                                  f'Stream {sid} has no previous start offset')
                            continue
                        offset = stream['offset']
                    step = stream['step'] or 1
                    if mode == 1:
                        count = length
                    elif mode == 3:
                        count = max(0, (len(bank) - offset - (stream['base'] or 0)) // step)
                    else:
                        issue('opn2_dac_stream_length_mode_unsupported', event_id, tick,
                              f'Stream {sid} length mode {mode:#x} is not implemented')
                        continue
                    start = offset + (stream['base'] or 0)
                    if count <= 0 or not 0 <= start < len(bank):
                        issue('opn2_dac_stream_out_of_bank', event_id, tick,
                              f'Stream {sid} start/count exceeds the available bank bytes')
                        continue
                    increment = (stream['frequency'] * _ONE + 22050) // 44100
                    stream.update(offset=start, count=count, index=0, running=True,
                                  phase=_ONE - increment, start_event=event_id,
                                  step=step)
            continue
        if cmd == 0xe0:
            stats['seek_commands'] += 1
            offset = int.from_bytes(raw[pos + 1:pos + 5], 'little')
            context = bind_quick(event_id, tick)
            context['offset'] = offset
            context['index'] = 0
            continue
        if 0x80 <= cmd <= 0x8f:
            stats['play_commands'] += 1
            context = bind_quick(event_id, tick)
            if context.get('offset') is None:
                issue('opn2_dac_play_without_stream', event_id, tick,
                      'DAC play command has no positioned stream')
                continue
            quick = context
            bank_offset = quick['offset'] + quick['index'] * (quick['step'] or 1)
            if not 0 <= bank_offset < len(bank):
                issue('opn2_dac_stream_out_of_bank', event_id, tick,
                      'DAC play command left the data bank')
                continue
            supplies.append((tick, bank[bank_offset], event_id))
            stats['manual_bytes'] += 1
            quick['index'] += 1
            continue
    advance(1 << 62)
    return supplies, issues, stats


def dac_timeline(raw, events, analysis):
    """Merge 0x2A writes and stream supplies into one audible timeline.

    Returns (timeline, issues, stats); timeline rows are
    (vgmticks, byte, source_event_id, origin) sorted by tick, with
    bytes outside DAC-enabled spans removed and counted.
    """
    spans = _enabled_spans(analysis)
    span_starts = [start for start, _ in spans]

    def audible(tick):
        index = bisect_right(span_starts, tick) - 1
        return index >= 0 and tick < spans[index][1]

    timeline = []
    stats = dict(write_bytes=0, write_bytes_dropped_disabled=0,
                 stream_bytes_dropped_disabled=0)
    for write in analysis.unmodeled_writes:
        if write.domain != 'dac_data':
            continue
        if audible(write.vgmticks):
            timeline.append((write.vgmticks, write.data, write.source_event_id, 'write'))
            stats['write_bytes'] += 1
        else:
            stats['write_bytes_dropped_disabled'] += 1
    stream_supplies, issues, stream_stats = _decode_stream_bytes(raw, events)
    for tick, byte, event_id in stream_supplies:
        timeline.append((tick, byte, event_id, 'stream'))
    if stream_supplies and not any(
            start <= stream_supplies[0][0] < end for start, end in spans):
        issues.append(PcmIssue(
            'opn2_dac_stream_without_enable_span', stream_supplies[0][2],
            stream_supplies[0][0],
            'DAC stream bytes play with no DAC-enabled span in the FM '
            'analysis; stream supplies are retained ungated because the '
            'stream mechanism carries its own playback intent'))
    timeline.sort(key=lambda row: (row[0], row[2], row[3]))
    collapsed = 0
    audible_timeline = []
    for row in timeline:
        if audible_timeline and audible_timeline[-1][0] == row[0]:
            audible_timeline[-1] = row
            collapsed += 1
        else:
            audible_timeline.append(row)
    stats.update(stream_stats)
    stats['collapsed_same_tick_bytes'] = collapsed
    stats['timeline_bytes'] = len(audible_timeline)
    return audible_timeline, issues, stats


def project_dac(raw, events, analysis, *, loop_start=None, loop_count=1,
                pcm_profile='standard'):
    """Build the MSM6258 analysis for a song's YM2612 DAC traffic.

    ``events`` must be the caller's command_times pass in the same
    (possibly loop-expanded) coordinates as ``analysis``; loop_start
    is the replayed loop boundary in those coordinates, matching the
    FM projection's declared loop point.
    """
    profile = get_profile(pcm_profile)
    timeline, issues, stats = dac_timeline(raw, events, analysis)
    source_end = analysis.source_end_vgmticks
    stats.update(runs=0, playbacks=0, unique_samples=0, profile=pcm_profile,
                 subsample_runs_dropped=0)
    # Split into runs at gaps; a run's last byte holds for the run's
    # median positive byte gap (one sample for a lone byte). Runs
    # also split at the replayed song-loop boundary: a PDX playback
    # may not continue across it (the planner restarts playbacks
    # there), so the sounding span becomes two playbacks.
    runs = []
    for row in timeline:
        crosses_loop = (loop_start is not None and runs
                        and runs[-1][0][0] < loop_start <= row[0])
        if runs and not crosses_loop and row[0] - runs[-1][-1][0] <= RUN_GAP_SAMPLES:
            runs[-1].append(row)
        else:
            runs.append([row])
    stats['runs'] = len(runs)
    samples = []
    sample_ids = {}
    playbacks = []
    event_rows = []
    for run_index, run in enumerate(runs):
        gaps = sorted(b - a for (a, *_), (b, *_) in zip(run, run[1:]) if b > a)
        hold = gaps[len(gaps) // 2] if gaps else 1
        start = run[0][0]
        stop = min(run[-1][0] + hold, source_end)
        if run_index + 1 < len(runs):
            stop = min(stop, runs[run_index + 1][0][0])
        if stop - start < 2:
            stats['subsample_runs_dropped'] += 1
            event_rows.append(dict(
                run_index=run_index, start_vgmticks=start, end_vgmticks=stop,
                bytes=len(run), origins=','.join(sorted({row[3] for row in run})),
                first_source_event_id=run[0][2], last_source_event_id=run[-1][2],
                sample_id='', termination='subsample_dropped'))
            continue
        wave = array('h', bytes(2 * (stop - start)))
        for (tick, byte, _event_id, _origin), (next_tick, *_rest) in zip(
                run, run[1:] + [(stop, 0, 0, '')]):
            amplitude = (byte - 128) * 256
            wave[tick - start:next_tick - start] = \
                array('h', [amplitude]) * (next_tick - tick)
        count = max(2, 2 * round(Fraction(len(wave), 1) / 44100
                                 * profile.rate / 2))
        resampled = array('h')
        ratio = Fraction(44100, 1) / profile.rate
        for index in range(count):
            position = max(Fraction(0),
                           Fraction(2 * index + 1, 2) * ratio - Fraction(1, 2))
            low = min(len(wave) - 1, position.numerator // position.denominator)
            high = min(len(wave) - 1, low + 1)
            fraction = position - position.numerator // position.denominator
            resampled.append(round(wave[low] * (1 - fraction)
                                   + wave[high] * fraction))
        key = hashlib.sha256(resampled.tobytes()).hexdigest()
        if key not in sample_ids:
            encoded, _error = encode_msm6258(resampled)
            sample_ids[key] = len(samples)
            samples.append(PcmSample(len(samples), 'msm6258-adpcm4-low-first',
                                     encoded, hashlib.sha256(encoded).hexdigest()))
        sample_id = sample_ids[key]
        consumed = min(count, round(Fraction(stop - start, 44100) * profile.rate))
        termination = 'song_end' if run_index == len(runs) - 1 and stop >= source_end else 'gap'
        playbacks.append(PcmPlayback(
            len(playbacks), 0, sample_id, start, stop,
            run[0][2], run[-1][2], 0, 0, 0,
            profile.mdx_clock_hz, profile.mdx_divider,
            profile.rate.numerator, profile.rate.denominator,
            0, False, True,
            'projected_independent_pdx_decoder_assumption',
            termination, True, True, count, consumed, (), ()))
        event_rows.append(dict(
            run_index=run_index, start_vgmticks=start, end_vgmticks=stop,
            bytes=len(run), origins=','.join(sorted({row[3] for row in run})),
            first_source_event_id=run[0][2], last_source_event_id=run[-1][2],
            sample_id=sample_id, termination=termination))
    stats['playbacks'] = len(playbacks)
    stats['unique_samples'] = len(samples)
    # Decode diagnostics ride in observations, not issues: the PCM
    # planner treats any issue as "source not representable", while a
    # derived bridge's partial-decode notes are evidence to record.
    # A wholly undecodable stream is gated by opn2_opm.convert, which
    # reads the stats (manual/autonomous byte counts) itself.
    return Opn2DacAnalysis(
        source_end, tuple(samples), tuple(playbacks), (), (),
        TransferLog(b''), (), bytes(raw), profile.mdx_clock_hz, 4,
        'derived YM2612 DAC samples; native evidence retained in the '
        'OPN2 analysis dump', loop_start, (),
        observations=tuple(issues),
        loop_count=loop_count, pcm_profile=profile.name,
        dac_event_rows=tuple(event_rows), dac_stats=stats)
