"""Native YM2612 (OPN2) FM Segments -> exact-sample projected OPM -> MDX path.

The projection follows py/opna_opm.py (the vgm-conv OPNToOPMConverter
shape): operator registers are re-laid out field by field, committed
FNUM/BLOCK goes through the existing 4 MHz OPM pitch helper, and the
output is an intermediate VGM of pure OPM writes consumed by the
ordinary OPM conversion. YM2612 differences from YM2608: no SSG,
no prescaler (divisor fixed at 6), no 0x29 channel-enable gate, and
the DAC channel in place of ADPCM-B. While the DAC is enabled,
channel 6 FM output is gated (the hardware disconnects it); the DAC
sample stream itself is a later stage (S3), as is the companion
SN76489 (S4) — both are explicit --force omissions until then.
"""
import csv
import json
import struct
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from psg_scc_opm import opm_pitch
from opn2 import Opn2UnmodeledWrite
from opn2_source import build_analysis
from vgm_io import read_vgm_bytes
from vgm_loop import read_loop_metadata
from vgm_timing import command_times


TARGET_CLOCK = 4000000
REFERENCE = '780a20ed505e23eb21aa9c6ce3f349029718b5a0'


def _unmapped_operator_slot(write):
    # Operator registers with channel bits 3 select no channel on the
    # hardware; drivers that upload padded voice rows write them anyway.
    return (write.domain == 'uninterpreted' and write.chip_instance == 0
            and write.port in (0, 1)
            and 0x30 <= write.register <= 0x9f and write.register & 3 == 3)


def dump_fm_omissions(analysis, outdir, stem, *, force):
    omissions = [dict(asdict(w),
                      reason='unmapped_fm_operator_slot' if _unmapped_operator_slot(w) else
                             'unsupported_register_effect:' + w.domain,
                      action='omit_write_from_target')
                 for w in analysis.unmodeled_writes
                 if force and w.domain != 'dac_data']
    out = Path(outdir)
    csv_name = stem + '.opn2_fm.omissions.csv'
    columns = [*Opn2UnmodeledWrite.__dataclass_fields__, 'reason', 'action']
    with (out / csv_name).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(omissions)
    summary = dict(enabled=force, scope='unsupported_fm_and_nonprojected_controls',
                   omitted_writes=len(omissions), source_ir_unchanged=True,
                   sample_rate_hz=44100, writes_csv=csv_name, omissions=omissions)
    (out / (stem + '.opn2_fm.omissions.json')).write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


def project(analysis, *, clock_raw, pitch_policy='clamp', channel_map=None, force=False):
    """Return target write rows plus explicit losses, retaining source identities."""
    clock_hz = clock_raw & 0x3fffffff
    if not 0 < clock_hz < 0x40000000:
        raise ValueError('OPN2 FM projection requires one positive-clock YM2612')
    if pitch_policy not in ('clamp', 'error'):
        raise ValueError('OPM pitch policy must be clamp or error')
    channel_map = ({ch: ch + (1 if ch >= 3 else 0) for ch in range(6)}
                   if channel_map is None else dict(channel_map))
    if (any(type(ch) is not int or not 0 <= ch < 6 for ch in channel_map)
            or any(type(ch) is not int or not 0 <= ch < 8 for ch in channel_map.values())
            or len(set(channel_map.values())) != len(channel_map)):
        raise ValueError('OPN2 FM channel mapping must use distinct OPM channels')
    if analysis.csm_observed and not force:
        raise ValueError('OPN2 CSM timer-generated key events cannot project to ordinary OPM FM')
    # DAC data written while the DAC is disabled makes no sound; only
    # writes inside an enabled span are sample playback.
    enabled_spans = [(s.vgmticks, s.vgmticks_end) for s in analysis.segments
                     if s.ch == 5 and s.state.dac_enabled == 1]
    dac_live = sum(1 for w in analysis.unmodeled_writes if w.domain == 'dac_data'
                   and any(start <= w.vgmticks < end for start, end in enabled_spans))
    dac_inert = sum(1 for w in analysis.unmodeled_writes if w.domain == 'dac_data') - dac_live
    if dac_live and not force:
        raise ValueError('YM2612 DAC sample playback is not projected yet (S3); '
                         'use --force to omit the DAC channel')
    slots = [w for w in analysis.unmodeled_writes if _unmapped_operator_slot(w)]
    unknown = [w for w in analysis.unmodeled_writes
               if w.domain != 'dac_data' and not _unmapped_operator_slot(w)]
    if unknown and not force:
        raise ValueError('OPN2 FM projection encountered an unknown register effect')
    losses = Counter()
    if dac_inert:
        losses['dac_data_writes_while_disabled_ignored'] = dac_inert
    if slots:
        losses['unmapped_operator_slot_writes_ignored'] = len(slots)
    if force:
        if dac_live:
            losses['dac_data_writes_omitted'] = dac_live
        if unknown:
            losses['forced_unmodeled_register_writes'] = len(unknown)
    rows, cache, groups = [], {}, {}
    for s in analysis.segments:
        if s.chip_instance or s.clock_raw != clock_raw:
            raise ValueError('OPN2 FM projection requires one unflagged YM2612 clock')
        if s.state.channel3_special_enabled and not force:
            raise ValueError('OPN2 CH3 special operator frequencies are not supported by OPM projection')
        if s.state.channel3_special_enabled:
            losses['ch3_special_frequencies_not_projected'] += 1
        if s.ch == 5 and s.state.dac_enabled == 1 and s.state.key_mask:
            losses['dac_enabled_ch6_fm_output_gated'] += 1
        if s.source_event_id is not None:
            groups.setdefault(s.source_event_id, []).append(s)

    def emit(s, register, data, reason, *, frequency=None, actual=None):
        # Preserve every Key request and repeated operator edge ordering.
        if register != 8 and cache.get(register) == data:
            return
        cache[register] = data
        rows.append(dict(write_id=len(rows), state_origin='projected_opm', source_chip='opn2_fm',
            source_event_id=s.source_event_id if s else None,
            source_segment_id=s.segment_id if s else None,
            original_event_id=s.original_event_id if s else None,
            loop_iteration=s.loop_iteration if s else 0,
            source_vgmticks=s.vgmticks if s else 0,
            source_ch=s.ch if s else None, source_register=s.register if s else None,
            source_data=s.data if s else None, target_register=register, target_data=data,
            reason=reason, source_frequency_hz=frequency, target_frequency_hz=actual,
            target_ch=channel_map.get(s.ch) if s and register != 0x18 else None,
            source_row=None, inferred_key=False, synthetic_phase=None))

    emit(None, 0x18, 0xc2, 'vgm-conv initial LFO frequency')

    def target_channel(s):
        return channel_map.get(s.ch)  # Same map as the OPNA route: OPM 0..2/4..6.

    def channel_control(s):
        state = s.state
        pan = (state.left_enabled or 0) << 6 | (state.right_enabled or 0) << 7
        if s.ch == 5 and state.dac_enabled == 1:
            pan = 0  # The DAC owns channel 6 output while enabled.
        return pan | (state.feedback or 0) << 3 | (state.algorithm or 0)

    def pitch(s):
        state, ch = s.state, target_channel(s)
        if ch is None:
            return
        if state.fnum is None or state.block is None:
            losses['unknown_pitch_target_reset_zero_assumption'] += 1
            fnum = state.fnum_low_raw or 0
            block = 0
        else:
            fnum, block = state.fnum, state.block
        frequency = fnum * clock_hz * (6 / state.fm_prescale_divisor) / (144 * 2 ** (20 - block))
        if frequency:
            try:
                kc, kf, actual = opm_pitch(frequency, TARGET_CLOCK)
            except ValueError:
                if pitch_policy == 'error':
                    raise
                kc, kf, actual = opm_pitch(frequency, TARGET_CLOCK, clamp=True)
                losses['pitch_range_clamped'] += 1
        else:
            kc = kf = 0
            actual = None
            losses['zero_frequency_target_minimum_pitch'] += 1
        emit(s, 0x28 + ch, kc, 'committed native FNUM/BLOCK to 4MHz KC', frequency=frequency, actual=actual)
        emit(s, 0x30 + ch, kf, 'committed native FNUM/BLOCK to KF', frequency=frequency, actual=actual)

    for _, segments in sorted(groups.items()):
        s = segments[0]
        state, reg, ch = s.state, s.register, target_channel(s)
        if ch is None and not (s.port == 0 and reg in (0x22, 0x24, 0x25, 0x26, 0x27, 0x2b)):
            continue
        if 0x30 <= reg <= 0x8f:
            bank = (reg >> 2) & 3
            op = state.operators[bank]
            data = {0x30: lambda: op.dt << 4 | op.mul,
                    0x40: lambda: op.tl,
                    0x50: lambda: op.ks << 6 | op.ar,
                    0x60: lambda: op.am_enabled << 7 | op.d1r,
                    0x70: lambda: op.d2r, 0x80: lambda: op.sl << 4 | op.rr}[reg & 0xf0]()
            emit(s, 0x40 + ((reg & 0xf0) - 0x30) * 2 + bank * 8 + ch,
                 data, 'vgm-conv operator bank mapping; DT2 reset zero')
        elif 0x90 <= reg <= 0x9f:
            if state.operators[(reg >> 2) & 3].ssg_eg_enabled:
                losses['ssg_eg_not_available_on_opm'] += 1
            if force:
                emit(s, 0x20 + ch, channel_control(s), 'forced FM SSG-EG output gate')
        elif 0xb0 <= reg <= 0xb2 or 0xb4 <= reg <= 0xb6:
            # Target-only reset assumptions for unwritten counterpart controls.
            emit(s, 0x20 + ch, channel_control(s),
                 'vgm-conv RL swap and FB/algorithm')
            if reg >= 0xb4:
                emit(s, 0x38 + ch, state.pms << 4 | state.ams, 'vgm-conv PMS/AMS mapping')
        elif 0xa0 <= reg <= 0xa2:
            pitch(s)
        elif s.port == 0 and reg == 0x28:
            emit(s, 8, state.key_mask << 3 | ch, 'vgm-conv operator key mask')
        elif s.port == 0 and reg == 0x2b:
            for item in segments:
                if target_channel(item) is not None:
                    emit(item, 0x20 + target_channel(item), channel_control(item),
                         'DAC enable as channel-6 output gate; FM state retained')
        elif s.port == 0 and reg == 0x22:
            emit(s, 0x18, (0xc2, 0xc9, 0xcb, 0xcd, 0xcf, 0xd6, 0xfb, 0xff)[state.lfo_rate],
                 'vgm-conv approximate LFO frequency')
            if state.lfo_enabled:
                losses['lfo_depth_waveform_and_speed_not_equivalent'] += 1
        elif s.port == 0 and reg in (0x24, 0x25, 0x26, 0x27):
            losses['source_timer_controls_not_projected'] += 1
            if force and reg == 0x27:
                for item in segments:
                    if item.ch == 2 and target_channel(item) is not None:
                        emit(item, 0x20 + target_channel(item), channel_control(item),
                             'forced CH3/CSM output gate; ordinary keys retained')
        # High FNUM writes affect source latches; forced CH3 modes stay output-gated.
    return rows, dict(losses)


def write_vgm(rows, path, *, end, loop_start=None, loop_event_id=None):
    """Serialize exact source samples; MDX quantization belongs downstream."""
    commands, cursor, loop_address = bytearray(), 0, None
    if not 0 <= end <= 0xffffffff or (loop_start is not None and not 0 <= loop_start < end):
        raise ValueError('Projected OPN2 duration/loop is outside the VGM field range')
    def wait(gap):
        while gap:
            count = min(gap, 65535)
            commands.extend(b'\x61' + struct.pack('<H', count))
            gap -= count
    def advance(sample, source_event_id=None, *, final=False):
        nonlocal cursor, loop_address
        if sample < cursor:
            raise ValueError('OPN2 projection writes are not in source sample order')
        at_loop = (loop_event_id is None or final or sample > (loop_start or 0)
                   or source_event_id is not None and source_event_id >= loop_event_id)
        if loop_start is not None and loop_address is None and cursor <= loop_start <= sample and at_loop:
            wait(loop_start - cursor)
            cursor = loop_start
            loop_address = 0x40 + len(commands)
        wait(sample - cursor)
        cursor = sample
    for row in rows:
        advance(row['source_vgmticks'], row['source_event_id'])
        row['target_command_address'] = 0x40 + len(commands)
        commands.extend((0x54, row['target_register'], row['target_data']))
    advance(end, final=True)
    commands.append(0x66)
    raw = bytearray(0x40) + commands
    raw[:4] = b'Vgm '
    for offset, value in ((4, len(raw)-4), (8, 0x171), (0x18, end), (0x30, TARGET_CLOCK)):
        struct.pack_into('<I', raw, offset, value)
    if loop_address is not None:
        struct.pack_into('<I', raw, 0x1c, loop_address-0x1c)
        struct.pack_into('<I', raw, 0x20, end-loop_start)
    identities = {e.address: i for i, e in enumerate(command_times(raw)) if e.command == 0x54}
    for row in rows:
        row['target_source_event_id'] = identities[row['target_command_address']]
    Path(path).write_bytes(raw)


def convert(source, outdir, *, dump_passes=False, song_loop=True, force=False,
            dcsg_present=False, dac_stream=None, **options):
    """Reconstruct native Segments, project FM, reuse canonical OPM conversion."""
    from opm_conversion import convert as convert_opm
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    dac_stream = dac_stream or {}
    if dac_stream.get('play_commands'):
        if not force:
            raise ValueError('YM2612 DAC stream playback is not projected yet (S3); '
                             'use --force to omit the DAC stream channel')
    for suffix in ('.mdx.mml', '.opn2-opm.json', '.mdx.normalization.json',
                   '.mdx.normalization.csv', '.mdx.before.normalize.mml',
                   '.opn2_fm.omissions.csv', '.opn2_fm.omissions.json'):
        artifact = outdir / (source.stem + suffix)
        if artifact.resolve() == source.resolve() or not artifact.resolve().is_relative_to(outdir.resolve()):
            raise ValueError('OPN2 conversion output would replace or leave its source/output boundary')
        artifact.unlink(missing_ok=True)
    raw = read_vgm_bytes(source)
    loop_meta = read_loop_metadata(raw)
    if song_loop and loop_meta['status'] not in ('no_loop', 'valid'):
        raise ValueError('Cannot project an invalid declared OPN2 song loop')
    repeating = song_loop and loop_meta['status'] == 'valid'
    omitted = []
    if dcsg_present:
        from dcsg import analyze as analyze_dcsg
        dcsg = analyze_dcsg(raw)
        audible = sum(s.length_samples for s in dcsg.segments if s.audible)
        if audible:
            if not force:
                raise ValueError('SN76489 (DCSG) projection is not implemented yet (S4); '
                                 'use --force to omit the DCSG channels')
            omitted.append(dict(part='DEFG', source_chip='dcsg', action='omit_source_engine',
                                reason='dcsg_stage_not_implemented',
                                audible_samples=audible))
    if dac_stream.get('play_commands'):
        omitted.append(dict(part='J', source_chip='opn2_dac_stream', action='omit_source_engine',
                            reason='dac_stream_stage_not_implemented',
                            play_commands=dac_stream['play_commands'],
                            seek_commands=dac_stream.get('seek_commands', 0)))
    with TemporaryDirectory(prefix='opn2-opm-') as temporary:
        work = outdir if dump_passes else Path(temporary)
        folder = work / 'projected_opm'
        folder.mkdir(parents=True, exist_ok=True)
        analysis, clock_raw, source_end, events = build_analysis(
            source, folder / (source.stem + '.native.opn2.registers.csv'),
            loop_count=2 if repeating else 1)
        if not analysis.events:
            raise ValueError('Input has no OPN2 register evidence')
        clock_hz = clock_raw & 0x3fffffff
        rows, losses = project(analysis, clock_raw=clock_raw,
                               pitch_policy=options.get('pitch_policy', 'clamp'), force=force)
        fm_force = dump_fm_omissions(analysis, outdir, source.stem, force=force)
        target = folder / (source.stem + '.vgm')
        if target.resolve() == source.resolve():
            raise ValueError('Projected OPM output must not replace its OPN2 source')
        loop_start = loop_meta['decoded_end_samples'] if repeating else None
        loop_event_id = (next((i for i, e in enumerate(events) if e.loop_iteration == 1), None)
                         if repeating else None)
        write_vgm(rows, target, end=analysis.source_end_vgmticks, loop_start=loop_start,
                  loop_event_id=loop_event_id)
        mapping = folder / (source.stem + '.source_map.csv')
        with mapping.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        settings = dict(state_origin='projected_opm', source_chip='YM2612', target_chip='YM2151',
            source_clock_hz=clock_hz, target_clock_hz=TARGET_CLOCK,
            mapping='vgm-conv OPNToOPMConverter', reference_revision=REFERENCE,
            channel_allocation=dict(model='OPNA route map: FM ch0-2 -> OPM 0-2, FM ch3-5 -> OPM 4-6; OPM ch3 reserved'),
            force_projection=dict(omitted=omitted, fm_omitted_writes=fm_force['omitted_writes'],
                                  fm_writes_csv=fm_force['writes_csv'], fm_omissions=fm_force['omissions']),
            source_end_vgmticks=analysis.source_end_vgmticks, excluded_or_approximated=losses,
            pitch='committed 11-bit FNUM; existing nominal OPM KC/KF projection',
            target_only_assumptions='unwritten counterpart controls/pitch use reset zero',
            limitations='FM EG/DT rates unretimed; DAC (S3) and DCSG (S4) not projected; no acoustic equivalence',
            source_loop=loop_meta, passes_retained=dump_passes,
            source_map=str(Path('projected_opm') / mapping.name) if dump_passes else None)
        (folder / 'provenance.json').write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')
        (outdir / (source.stem + '.opn2-opm.json')).write_text(
            json.dumps(settings, indent=2) + '\n', encoding='utf-8')
        result, _, _ = convert_opm(target, outdir, dump_passes=dump_passes,
            song_loop=song_loop, replayed_song_loop=True, force=force,
            normalization_source_times={r['target_source_event_id']: r['source_vgmticks'] for r in rows},
            **options)
    return result, settings
