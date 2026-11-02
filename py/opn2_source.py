"""Native YM2612 (OPN2) source analysis for the MDX route.

S1 stage: builds the register-evidence CSV the ported opn2 state
machine consumes, dumps its state/segment/unmodeled evidence into
the song directory, and measures the two questions the later stages
depend on: how DAC traffic is encoded (0x2A write runs vs DAC
stream controls) and how busy the companion SN76489 (DCSG) is.
No target projection happens in this module.
"""
from collections import Counter
import csv
from pathlib import Path

from vgm_io import read_vgm_bytes, read_vgm_header
from vgm_timing import command_times
import opn2

WRITE_COMMANDS = {0x52: (0, 0), 0x53: (0, 1), 0xa2: (1, 0), 0xa3: (1, 1)}
TRACE_FIELDS = ('event_id', 'source_event_id', 'original_event_id', 'address',
                'command', 'chip_instance', 'chip_type', 'clock_hz', 'clock_raw',
                'ch', 'register', 'data', 'vgmticks', 'loop_iteration',
                'original_vgmticks', 'port')
# A gap longer than this between DAC data writes ends a measured run
# (10 ms; the write cadence inside a playback run is far denser).
DAC_RUN_GAP_SAMPLES = 441


def _trace_csv(raw, events, clock_raw, path):
    clock = clock_raw & 0x3fffffff
    with open(path, 'w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=TRACE_FIELDS, lineterminator='\n')
        writer.writeheader()
        for event_id, event in enumerate(events):
            spec = WRITE_COMMANDS.get(event.command)
            if spec is None:
                continue
            instance, port = spec
            pos = event.address
            register, value = raw[pos + 1], raw[pos + 2]
            channel = opn2.register_channel(register, value, port)
            writer.writerow(dict(
                event_id=event_id, source_event_id=event.source_event_id,
                original_event_id=event.source_event_id, address=pos,
                command=event.command, chip_instance=instance, chip_type='YM2612',
                clock_hz=clock, clock_raw=clock_raw,
                ch='' if channel is None else channel, register=register, data=value,
                vgmticks=event.vgmticks, loop_iteration=event.loop_iteration,
                original_vgmticks=event.original_vgmticks, port=port))


def _dac_measurements(analysis):
    data = [write for write in analysis.unmodeled_writes if write.domain == 'dac_data']
    runs = []
    for write in data:
        if runs and write.vgmticks - runs[-1][1] <= DAC_RUN_GAP_SAMPLES:
            runs[-1][1] = write.vgmticks
            runs[-1][2] += 1
        else:
            runs.append([write.vgmticks, write.vgmticks, 1])
    gaps = []
    previous = None
    for write in data:
        if previous is not None and write.vgmticks - previous <= DAC_RUN_GAP_SAMPLES:
            gaps.append(write.vgmticks - previous)
        previous = write.vgmticks
    positive = sorted(gap for gap in gaps if gap > 0)
    enabled = sum(segment.duration_samples for segment in analysis.segments
                  if segment.ch == 5 and segment.state.dac_enabled == 1)
    return dict(data_writes=len(data), runs=len(runs),
                run_bytes=[run[2] for run in runs],
                median_write_gap_samples=positive[len(positive) // 2] if positive else None,
                dac_enabled_samples=enabled)


def _dcsg_measurements(raw, source_end):
    from dcsg import analyze
    analysis = analyze(raw)
    channels = {}
    for segment in analysis.segments:
        entry = channels.setdefault(f'{segment.chip_instance}:{segment.ch}', dict(
            audible_samples=0, tone2_coupled_segments=0))
        if segment.audible:
            entry['audible_samples'] += segment.length_samples
        if segment.noise_tone2_coupled:
            entry['tone2_coupled_segments'] += 1
    for entry in channels.values():
        entry['duty'] = (entry['audible_samples'] / source_end) if source_end else 0.0
    return dict(channels=channels, issues=list(analysis.issues))


def build_analysis(source, trace_path, *, loop_count=1):
    """Build the OPN2 analysis for ``source``, writing its register trace.

    Returns (analysis, clock_raw, source_end_vgmticks, events); the
    events are the full command_times list the trace event ids index.
    """
    raw = read_vgm_bytes(source)
    header = read_vgm_header(raw)
    clock_raw = int.from_bytes(raw[0x2c:0x30], 'little') if header['version'] >= 0x150 else 0
    events = tuple(command_times(raw, loop_count=loop_count))
    source_end = max((event.vgmticks + event.wait_samples for event in events), default=0)
    _trace_csv(raw, events, clock_raw, trace_path)
    analysis = opn2.build_segments(trace_path, end_vgmticks=source_end)
    return analysis, clock_raw, source_end, events


def analyze_opn2_source(source, outdir, stem, usage):
    """Run the OPN2 state machine and retain its evidence in ``outdir``.

    ``usage`` is the frontend inventory (conversion_config.inspect_source);
    its stream-control and data-block records feed the DAC encoding
    measurement. Returns a JSON-ready summary for the conversion report.
    """
    root = Path(outdir)
    root.mkdir(parents=True, exist_ok=True)
    raw = read_vgm_bytes(source)
    trace_path = root / f'{stem}.native.opn2.registers.csv'
    analysis, clock_raw, source_end, events = build_analysis(source, trace_path)
    opn2.dump_analysis(analysis,
                       state_csv=root / f'{stem}.native.opn2.states.csv',
                       segments_csv=root / f'{stem}.native.opn2.segments.csv')
    opn2.dump_unmodeled_writes(analysis,
                               csv_path=root / f'{stem}.native.opn2.unmodeled.csv')
    stream_controls = usage.get('dac_stream_controls', [])
    summary = dict(
        clock_hz=clock_raw & 0x3fffffff, clock_raw=clock_raw,
        source_end_vgmticks=source_end,
        events=len(analysis.events), segments=len(analysis.segments),
        key_counts=opn2.key_counts(analysis),
        csm_observed=analysis.csm_observed,
        issues=list(analysis.issues),
        unmodeled_counts=dict(Counter(write.domain for write in analysis.unmodeled_writes)),
        dac=dict(_dac_measurements(analysis),
                 stream_controls=len(stream_controls),
                 stream_ids=sorted({item['stream_id'] for item in stream_controls}),
                 data_blocks=dict(Counter(block['bank_type'] for block in usage.get('data_blocks', [])))),
        dcsg=_dcsg_measurements(raw, source_end) if 'dcsg' in usage['used_chips'] else None)
    return summary
