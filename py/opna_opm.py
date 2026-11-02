"""Native OPNA FM/SSG Segments -> exact-sample projected OPM -> existing MDX path.

The register/channel mapping is derived from the two chips' register
layouts and this project's own ymfm-based audit (field semantics,
EG-rate law, LFO depth/rate laws are stated where they are used).
Native committed 11-bit pitch uses the existing 4 MHz OPM pitch helper.
Source evidence is never rewritten as target convenience.
"""
import csv
import json
import struct
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from psg_scc_opm import opm_pitch
from opna import OpnaUnmodeledWrite, dump_unmodeled_writes
from opna_force import fm_mute_reasons
from vgm_reader import parse_vgm
from vgm_io import read_vgm_bytes
from vgm_timing import command_times


TARGET_CLOCK = 4000000
NON_FM = {'ssg', 'rhythm', 'adpcm_b', 'irq_flag_control'}

# LFO rate mapping, derived from the chip models in ymfm (and
# corroborated by Nuked-OPN2's die-derived divider counts): the OPN
# LFO advances its 7-bit value when the counter's low byte reaches
# {109, 78, 72, 68, 63, 45, 9, 6}[rate] at the FM sample clock
# (OPNA 7,987,200/144 = 55.5 kHz), while the OPM rate byte is a 4.4
# float step giving Hz = 62,500 * ((0x10 | (b & 0xf)) << (b >> 4))
# / 2**30. Each entry is the OPM byte nearest in Hz to the source
# rate (4.01/5.63/6.10/6.47/6.99/9.85/54.1/86.4 Hz). Source rate 7
# exceeds the OPM maximum of 59.1 Hz and saturates at 0xff.
# Derivation script: opna_opm_voice study, lfo_rate_map.py.
_LFO_RATE_TO_OPM = (0xc1, 0xc8, 0xca, 0xcb, 0xcd, 0xd5, 0xfc, 0xff)

# EG rate conversion. The OPN and OPM envelope cores share one
# design (EG clock = sample rate / 3, effective rate = 2R + the
# key-scale term, R = 0 frozen); only the sample rate differs
# (OPNA 7,987,200/144 = 55.5 kHz at prescaler 6, OPM 4,000,000/64
# = 62.5 kHz). At prescaler 6 the nearest OPM rate is the source
# rate itself (residual -11% time), but prescaler 3/2 sources run
# their envelopes 1.78x/2.67x faster and need +2/+3 rate steps to
# hold envelope times on OPM. Derived in the opna_opm_voice study
# (eg_rate_map.csv); the shift is additive in the 5-bit rate space
# and therefore independent of the key-scale term.
_EG_PRESCALE_SHIFT = {6: 0, 3: 2, 2: 3}


def _eg_rate(rate, divisor):
    if not rate:
        return rate
    return min(31, rate + _EG_PRESCALE_SHIFT.get(divisor, 0))


def _eg_release(rr, divisor):
    # In effective-rate units the release rate is 4*RR+2 on both
    # chips (ymfm's OPN and OPM cores agree), so the prescaler
    # correction of +3.3/+5.7 effective-rate units is under one
    # RR step in both cases and rounds to +1.
    if not rr or divisor == 6:
        return rr
    return min(15, rr + 1)


def _unmapped_operator_slot(write):
    return (write.domain == 'uninterpreted' and write.chip_type == 'YM2608'
            and write.chip_instance == 0 and write.port in (0, 1)
            and 0x30 <= write.register <= 0x9f and write.register & 3 == 3)


def dump_fm_omissions(analysis, outdir, stem, *, force):
    omissions = [dict(asdict(w),
                      reason='unmapped_fm_operator_slot' if _unmapped_operator_slot(w) else
                             'unsupported_register_effect:' + w.domain,
                      action='omit_write_from_target')
                 for w in analysis.unmodeled_writes
                 if force and w.domain not in ('ssg', 'adpcm_b')]
    out = Path(outdir)
    csv_name = stem + '.opna_fm.omissions.csv'
    columns = [*OpnaUnmodeledWrite.__dataclass_fields__, 'reason', 'action']
    with (out / csv_name).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(omissions)
    summary = dict(enabled=force, scope='unsupported_fm_and_nonprojected_controls',
                   omitted_writes=len(omissions), source_ir_unchanged=True,
                   sample_rate_hz=44100, writes_csv=csv_name, omissions=omissions)
    (out / (stem + '.opna_fm.omissions.json')).write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


def project(analysis, *, clock_hz, pitch_policy='clamp', channel_map=None, force=False):
    """Return target write rows plus explicit losses, retaining source identities."""
    if not 0 < clock_hz < 0x40000000:
        raise ValueError('OPNA FM projection requires one positive-clock YM2608')
    if pitch_policy not in ('clamp', 'error'):
        raise ValueError('OPM pitch policy must be clamp or error')
    channel_map = ({ch: ch + (1 if ch >= 3 else 0) for ch in range(6)}
                   if channel_map is None else dict(channel_map))
    if (any(type(ch) is not int or not 0 <= ch < 6 for ch in channel_map)
            or any(type(ch) is not int or not 0 <= ch < 8 for ch in channel_map.values())
            or len(set(channel_map.values())) != len(channel_map)):
        raise ValueError('OPNA FM channel mapping must use distinct OPM channels')
    if analysis.csm_observed and not force:
        raise ValueError('OPNA CSM timer-generated key events cannot project to ordinary OPM FM')
    if not force and any(w.domain not in NON_FM for w in analysis.unmodeled_writes):
        raise ValueError('OPNA FM projection encountered an unknown register effect')
    losses = Counter(w.domain for w in analysis.unmodeled_writes)
    if force:
        omitted = sum(w.domain not in NON_FM for w in analysis.unmodeled_writes)
        if omitted:
            losses['forced_unmodeled_register_writes'] = omitted
    rows, cache, groups = [], {}, {}
    for s in analysis.segments:
        if s.chip_instance or s.clock_raw != clock_hz:
            raise ValueError('OPNA FM projection requires one unflagged YM2608 clock')
        if s.state.channel3_special_enabled and not force:
            raise ValueError('OPNA CH3 special operator frequencies are not supported by OPM projection')
        if s.source_event_id is not None:
            groups.setdefault(s.source_event_id, []).append(s)

    def emit(s, register, data, reason, *, frequency=None, actual=None):
        # Preserve every Key request and repeated operator edge ordering.
        if register != 8 and cache.get(register) == data:
            return
        cache[register] = data
        rows.append(dict(write_id=len(rows), state_origin='projected_opm', source_chip='opna_fm',
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

    emit(None, 0x18, _LFO_RATE_TO_OPM[0], 'initial LFO frequency')

    # Hardware LFO bridge: the source LFO waveform is a fixed triangle
    # and its depths live in the per-channel PMS/AMS steps, while OPM
    # scales those steps by the global PMD/AMD latches. PMD 86 makes
    # the OPM PMS steps 3.4 * 2^k cents (the OPN series) for PMS 1..3
    # and keeps 4..7 within +25%/-38%; AMD 16 makes the OPM AMS steps
    # 0/3.0/6.0/12.0 dB against the source 0/1.4/5.9/11.8 dB. The
    # depths are emitted once per span in which the source LFO is
    # enabled and some channel has nonzero sensitivity, and zeroed
    # when that span ends; rate and sensitivities already flow as
    # 0x18/0x38 writes.
    lfo = {'enabled': False, 'on': False, 'sensitivities': {}}

    def lfo_bridge(s):
        active = lfo['enabled'] and any(
            pms or ams for pms, ams in lfo['sensitivities'].values())
        if active and not lfo['on']:
            emit(s, 0x1b, 0x02, 'OPN fixed triangle as OPM LFO waveform')
            emit(s, 0x19, 0x80 | 86, 'OPM PMD scaled to OPN PMS depth steps')
            emit(s, 0x19, 16, 'OPM AMD scaled to OPN AMS depth steps')
            losses['lfo_depths_bridged'] += 1
            lfo['on'] = True
        elif not active and lfo['on']:
            emit(s, 0x19, 0x80, 'LFO bridge span ended: PM depth zero')
            emit(s, 0x19, 0, 'LFO bridge span ended: AM depth zero')
            lfo['on'] = False

    def target_channel(s):
        return channel_map.get(s.ch)  # Default map: OPM 0..2/4..6 (OPM ch3 reserved).

    def channel_control(s):
        state = s.state
        pan = (state.left_enabled or 0) << 6 | (state.right_enabled or 0) << 7
        if s.ch >= 3 and state.six_channel_enabled == 0:
            pan = 0  # Output gate, not a synthetic key/envelope restart.
        if force and fm_mute_reasons(s):
            pan = 0  # Keep ordinary keys/controls underneath the explicit output gate.
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
        # Hardware pitch: the OPN phase counter is 20 bits and the block
        # scales FNUM by 2**(block-1), so Hz = fnum * clock / (144 *
        # 2**(21-block)) at prescale 6 (YM2608/YM3438 manual formula;
        # ymfm's Nuked-verified phase generator agrees). The
        # 2**(20-block) form used here before played every note one
        # octave high.
        frequency = fnum * clock_hz * (6 / state.fm_prescale_divisor) / (144 * 2 ** (21 - block))
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
        if ch is None and not (s.port == 0 and reg in (0x22, 0x24, 0x25, 0x26, 0x27,
                                                       0x29, 0x2d, 0x2e, 0x2f)):
            continue
        if 0x30 <= reg <= 0x8f:
            bank = (reg >> 2) & 3
            op = state.operators[bank]
            divisor = state.fm_prescale_divisor
            plain = {0x30: lambda: op.dt << 4 | op.mul,
                     0x40: lambda: op.tl,
                     0x50: lambda: op.ks << 6 | op.ar,
                     0x60: lambda: op.am_enabled << 7 | op.d1r,
                     0x70: lambda: op.d2r,
                     0x80: lambda: op.sl << 4 | op.rr}[reg & 0xf0]()
            data = plain
            if divisor != 6:
                data = {0x50: lambda: op.ks << 6 | _eg_rate(op.ar, divisor),
                        0x60: lambda: op.am_enabled << 7 | _eg_rate(op.d1r, divisor),
                        0x70: lambda: _eg_rate(op.d2r, divisor),
                        0x80: lambda: op.sl << 4 | _eg_release(op.rr, divisor)
                        }.get(reg & 0xf0, lambda: plain)()
                if data != plain:
                    losses['eg_rate_prescaler_adjustments'] += 1
            emit(s, 0x40 + ((reg & 0xf0) - 0x30) * 2 + bank * 8 + ch,
                 data, 'operator bank mapping; DT2 reset zero')
        elif 0x90 <= reg <= 0x9f:
            if state.operators[(reg >> 2) & 3].ssg_eg_enabled:
                losses['ssg_eg_not_available_on_opm'] += 1
            if force:
                emit(s, 0x20 + ch, channel_control(s), 'forced FM SSG-EG output gate')
        elif 0xb0 <= reg <= 0xb2 or 0xb4 <= reg <= 0xb6:
            # Target-only reset assumptions for unwritten counterpart controls.
            emit(s, 0x20 + ch, channel_control(s),
                 'RL swap and FB/algorithm')
            if reg >= 0xb4:
                emit(s, 0x38 + ch, state.pms << 4 | state.ams, 'PMS/AMS mapping')
                lfo['sensitivities'][s.ch] = (state.pms or 0, state.ams or 0)
                lfo_bridge(s)
        elif 0xa0 <= reg <= 0xa2:
            pitch(s)
        elif s.port == 0 and reg == 0x28:
            if s.ch >= 3 and state.six_channel_enabled is None:
                losses['unknown_output_enable_target_enabled_assumption'] += 1
            emit(s, 8, state.key_mask << 3 | ch, 'operator key mask')
        elif s.port == 0 and reg == 0x29:
            for item in segments:
                if item.ch >= 3 and target_channel(item) is not None:
                    emit(item, 0x20 + target_channel(item), channel_control(item),
                         'OPNA six-channel output enable as RL gate; held keys preserved')
        elif s.port == 0 and reg in (0x2d, 0x2e, 0x2f):
            for item in segments:
                if item.state.fnum is not None:
                    pitch(item)
        elif s.port == 0 and reg == 0x22:
            emit(s, 0x18, _LFO_RATE_TO_OPM[state.lfo_rate],
                 'approximate LFO frequency (derived rate table)')
            lfo['enabled'] = bool(state.lfo_enabled)
            lfo_bridge(s)
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
        raise ValueError('Projected OPNA duration/loop is outside the VGM field range')
    def wait(gap):
        while gap:
            count = min(gap, 65535)
            commands.extend(b'\x61' + struct.pack('<H', count))
            gap -= count
    def advance(sample, source_event_id=None, *, final=False):
        nonlocal cursor, loop_address
        if sample < cursor:
            raise ValueError('OPNA projection writes are not in source sample order')
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


def convert(source, outdir, *, dump_passes=False, song_loop=True, force=False, **options):
    """Reconstruct native Segments, project FM, reuse canonical OPM conversion."""
    from opm_conversion import convert as convert_opm
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for suffix in ('.mdx.mml', '.opna-opm.json', '.mdx.normalization.json',
                   '.mdx.normalization.csv', '.mdx.before.normalize.mml',
                   '.opna_ssg.omissions.csv', '.opna_ssg.omissions.json',
                   '.opna_fm.omissions.csv', '.opna_fm.omissions.json', '.opna.unmodeled.csv',
                   '.opna_force.skipped_registers.csv', '.opna_force.skipped_registers.json'):
        artifact = outdir / (source.stem + suffix)
        if artifact.resolve() == source.resolve() or not artifact.resolve().is_relative_to(outdir.resolve()):
            raise ValueError('OPNA conversion output would replace or leave its source/output boundary')
        artifact.unlink(missing_ok=True)
    with TemporaryDirectory(prefix='opna-opm-') as temporary:
        work = outdir if dump_passes else Path(temporary)
        metadata, source_loop, pcm_metadata = {}, {}, {}
        parse_vgm(str(source), str(work), opna_metadata=metadata, dump_opna_segments=True,
                  opna_pcm_metadata=pcm_metadata,
                  loop_metadata=source_loop, dump_loop=dump_passes, loop_count=2 if song_loop else 1)
        from opna_adpcm import project_msm6258
        native_pcm = pcm_metadata['analysis']
        native_pcm.dump(outdir, source.stem)
        from opna_force_pcm import prepare as prepare_forced_pcm
        projection_pcm, pcm_omissions = prepare_forced_pcm(native_pcm, force=force)
        # A control slice is not a fresh decoder. Keep the existing independent
        # route, but reconstruct the whole epoch when live controls are present.
        continuous_pcm = any(s.continuation_index or
            'controls_during_decoder_epoch' in s.issues or
            (s.rate_num == 0 and native_pcm.clock_hz > 0) for s in projection_pcm.segments)
        if any(row['domain'] != 'adpcm_b_data_block' for row in metadata['auxiliary_commands']):
            raise ValueError('Unexpanded OPNA DAC streams may affect FM; projection refused')
        analysis = metadata['analysis']
        if analysis is None or not metadata['write_count']:
            raise ValueError('Input has no OPNA register evidence')
        from opna_ssg import build_segments as build_ssg
        from opna_ssg_opm import allocate, dump_allocation, dump_omissions, merge, project as project_ssg
        ssg = build_ssg(metadata['csv_path'], end_vgmticks=analysis.source_end_vgmticks)
        if dump_passes or force:
            ssg.dump(outdir, source.stem)
        if force:
            dump_unmodeled_writes(analysis, csv_path=outdir / (source.stem + '.opna.unmodeled.csv'))
        fm_map, ssg_map, allocation = allocate(analysis, ssg)
        allocation_summary = dump_allocation(allocation, outdir, source.stem)
        rows, losses = project(analysis, clock_hz=metadata['clock_raw'],
                               pitch_policy=options.get('pitch_policy', 'clamp'),
                               channel_map=fm_map, force=force)
        fm_force = dump_fm_omissions(analysis, outdir, source.stem, force=force)
        losses.pop('ssg', None)  # SSG writes now enter their own target projection.
        folder = work / 'projected_opm'
        folder.mkdir(exist_ok=True)
        target = folder / (source.stem + '.vgm')
        if target.resolve() == source.resolve():
            raise ValueError('Projected OPM output must not replace its OPNA source')
        loop_start = (source_loop['replay_start_samples']
                      if song_loop and source_loop.get('status') == 'valid' else None)
        ssg_rows, ssg_baseline, ssg_performance = project_ssg(ssg, ssg_map,
            loop_start=loop_start, pitch_policy=options.get('pitch_policy', 'clamp'), force=force)
        force_summary = dump_omissions(ssg_baseline.settings['forced_omissions'],
                                      outdir, source.stem, force=force)
        force_summary.update(scope='opna_partial_hw_projection',
                             fm_omitted_writes=fm_force['omitted_writes'],
                             fm_writes_csv=fm_force['writes_csv'], fm_omissions=fm_force['omissions'],
                             pcm_part_omitted=bool(pcm_omissions))
        from opna_force import collect as collect_force, dump as dump_force
        decisions = collect_force(analysis, ssg, ssg_baseline.settings['forced_omissions'],
                                  fm_force['omissions'], pcm_omissions=pcm_omissions,
                                  dropped_ssg=allocation_summary['dropped_ssg'], force=force)
        register_report = dump_force(decisions, outdir, source.stem, force=force)
        force_summary.update(skipped_registers=register_report['skipped_registers'],
                             registers_csv=register_report['registers_csv'],
                             decision_count=register_report['decision_count'])
        if force_summary['omitted_intervals']:
            losses['forced_ssg_intervals_muted'] = force_summary['omitted_intervals']
        if dump_passes:
            ssg_baseline.dump(outdir, source.stem + '.ssg')
            ssg_performance.dump(outdir, source.stem + '.ssg')
        if allocation_summary['dropped_ssg']:
            losses['ssg_channels_dropped_for_opm_capacity'] = len(allocation_summary['dropped_ssg'])
        if ssg_map:
            losses['ssg_inferred_gate_and_fm_timbre_approximation'] = len(ssg_map)
        rows = merge(rows, ssg_rows)
        write_vgm(rows, target, end=analysis.source_end_vgmticks, loop_start=loop_start,
                  loop_event_id=source_loop.get('replay_start_event_id'))
        from opna_pcm_bank import project as project_pcm_bank
        pcm_bridge = project_pcm_bank(projection_pcm, source_raw=read_vgm_bytes(source),
            loop_start=loop_start, pcm_profile=options.get('pcm_profile', 'standard'),
            pdx_format=options.get('pdx_format', 'ex-pdx'))
        finite_pcm_bank = pcm_bridge is not None
        if finite_pcm_bank:
            pcm_bridge.dump(outdir, source.stem)
        elif continuous_pcm:
            from opna_adpcm_waveform import project as project_continuous_pcm
            pcm_bridge = project_continuous_pcm(projection_pcm,
                source_raw=read_vgm_bytes(source), loop_start=loop_start,
                pcm_profile=options.get('pcm_profile','standard'))
            pcm_bridge.native.dump(outdir, source.stem)
            pcm_bridge.dump(outdir, source.stem)
        else:
            from opna_pcm import adapt
            target_pcm = project_msm6258(projection_pcm, pcm_profile=options.get('pcm_profile','standard'))
            target_pcm.dump(outdir, source.stem)
            pcm_bridge = adapt(projection_pcm, target_pcm, source_raw=read_vgm_bytes(source),
                               loop_start=loop_start,pcm_profile=options.get('pcm_profile','standard'))
            pcm_bridge.dump_bridge(outdir, source.stem)
        mapping = folder / (source.stem + '.source_map.csv')
        with mapping.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        settings = dict(state_origin='projected_opm', source_chip='YM2608', target_chip='YM2151',
            source_clock_hz=metadata['clock_hz'], target_clock_hz=TARGET_CLOCK,
            mapping='register-layout mapping derived from ymfm-based audit',
            channel_allocation=allocation_summary, force_projection=force_summary,
            ssg_projection=dict(model='existing PSG FM AL4/FB7', channels=len(ssg_map),
                inferred_attacks=sum(w.inferred_key and bool(w.data & 0x78) for w in ssg_performance.writes),
                noise_and_hardware_envelope=('unsupported intervals muted by explicit --force'
                    if force else 'same explicit rejection as existing PSG target'),
                clock='per Segment master/4, master/2 or master; exact source samples before MDX',
                source_provenance='opna_ssg; baseline/performance reuse generic PSG model'),
            source_end_vgmticks=analysis.source_end_vgmticks, excluded_or_approximated=losses,
            pitch='committed 11-bit FNUM; existing nominal OPM KC/KF projection',
            target_only_assumptions='unwritten counterpart controls/pitch use reset zero',
            limitations='FM EG rates follow the prescaler-aware nearest-rate law (identity at prescaler 6); DT identity per the shared detune table; HW LFO bridged with fixed OPM PMD/AMD depth scaling (PMS/AMS identity, triangle waveform); ADPCM-B transcoding is approximate; no acoustic equivalence',
            pcm_ir=dict(pcm_profile=options.get('pcm_profile','standard'),source_codec='ym2608-adpcm-b', target_codec='msm6258-adpcm4',
                        native_segments=len(native_pcm.segments), target_samples=len(pcm_bridge.samples),
                        eligible_playbacks=sum(p.independently_playable for p in pcm_bridge.playbacks),
                        ineligible_playbacks=sum(not p.independently_playable for p in pcm_bridge.playbacks),
                        continuous_decoder_epochs=continuous_pcm,
                        finite_sample_bank=finite_pcm_bank,
                        native_issues=[issue.code for issue in native_pcm.issues],
                        candidate_pdx_samples=len(pcm_bridge.samples), pdx_distinct_samples=None,
                        policy=options.get('pcm_policy', 'auto'),
                        integration='transcoded MSM6258 IR to shared-clock MDX P track and external PDX packer'),
            source_loop=source_loop, passes_retained=dump_passes,
            source_map=str(Path('projected_opm') / mapping.name) if dump_passes else None)
        (folder / 'provenance.json').write_text(json.dumps(settings, indent=2)+'\n', encoding='utf-8')
        (outdir / (source.stem + '.opna-opm.json')).write_text(
            json.dumps(settings, indent=2)+'\n', encoding='utf-8')
        result, _, _ = convert_opm(target, outdir, dump_passes=dump_passes,
            pcm_analysis_override=pcm_bridge, source_passes_outdir=folder,
            song_loop=song_loop, replayed_song_loop=True, force=force,
            normalization_source_times={r['target_source_event_id']: r['source_vgmticks'] for r in rows}, **options)
        timing_path = outdir / (source.stem + '.pcm.timing.json')
        final_pcm = json.loads(timing_path.read_text(encoding='utf-8')) if timing_path.is_file() else {}
        settings['pcm_ir']['pdx_distinct_samples'] = final_pcm.get('pcm_sample_count', 0)
        (folder / 'provenance.json').write_text(json.dumps(settings, indent=2)+'\n', encoding='utf-8')
        (outdir / (source.stem + '.opna-opm.json')).write_text(
            json.dumps(settings, indent=2)+'\n', encoding='utf-8')
    return result, settings
