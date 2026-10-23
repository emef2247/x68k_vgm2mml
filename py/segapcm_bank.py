"""Finite SegaPCM source views -> reusable MDX assets and parallel playbacks.

Native trace/runtime evidence is never rewritten. Unsupported capabilities are
distinct from malformed input so automatic fallback cannot conceal other errors.
"""
from dataclasses import asdict, dataclass, fields
from array import array
from fractions import Fraction
import csv
import hashlib
import json
from pathlib import Path

from msm6258 import PcmAnalysis, PcmPlayback, PcmSample, TransferLog
from opna_adpcm import encode_msm6258
from pcm_profiles import get_profile
from pcm_capacity import sample_byte_limit
from segapcm_playback import _Rom
from pcm8_volume import project_pcm8_volume


class BankUnsupported(ValueError):
    """A valid source requires capabilities outside the finite bank route."""

    def __init__(self, code, detail, gate_id=None):
        super().__init__(detail)
        self.reason = dict(code=code, detail=detail, gate_id=gate_id)


@dataclass(frozen=True)
class BankPlayback(PcmPlayback):
    source_channel: int = 0
    target_volume: int = 128


@dataclass(frozen=True)
class BankAnalysis(PcmAnalysis):
    parallel_playbacks: bool = True
    source_origin: str = 'projected_msm6258_from_segapcm_bank'
    normalization_omission_safe: bool = False
    pcm_profile: str = 'standard'
    target_evidence: tuple[dict, ...] = ()
    bank_assets: tuple[dict, ...] = ()
    bank_events: tuple[dict, ...] = ()
    bank_parts: tuple[dict, ...] = ()
    bank_stats: dict | None = None
    bank_waveforms: tuple[dict, ...] = ()

    def dump(self, outdir, stem):
        # The inherited CSV contract has fixed native playback columns.
        values = {f.name: getattr(self, f.name) for f in fields(PcmAnalysis)}
        values['playbacks'] = tuple(PcmPlayback(**{f.name: getattr(p, f.name)
            for f in fields(PcmPlayback)}) for p in self.playbacks)
        PcmAnalysis(**values).dump(outdir, stem)
        root = Path(outdir)
        for name, rows in (('assets', self.bank_assets), ('events', self.bank_events),
                           ('parts', self.bank_parts)):
            with (root / f'{stem}.segapcm_bank.{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]) if rows else ('sample_id',))
                writer.writeheader()
                writer.writerows(rows)
        path = root / f'{stem}.pcm_source.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report.update(source_origin=self.source_origin, consumption_origin='derived_finite_rom_view',
            parallel_playbacks=True, asset_clock_alignment='immutable; only events use shared MDX clock',
            sample_amplitude_scale=128, pcm_profile=self.pcm_profile,
            target_evidence=self.target_evidence)
        path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def _project_finite(trace, native, *, source_raw, loop_start=None, loop_count=1, pcm_profile='standard', pdx_format='ex-pdx'):
    """Convert complete finite views once, independently of each gate duration."""
    maximum = sample_byte_limit(pdx_format)
    profile = get_profile(pcm_profile)
    starts = {e.source.event_id: e for e in trace.state_events}
    cursors = {e.event_id: e for e in native.runtime_events if e.kind == 'control_write'}
    writes = {}
    source_ids = {w.source.event_id: w.source.source_event_id for w in trace.writes}
    for write in trace.writes:
        writes.setdefault((write.source.chip_instance, write.channel), []).append(write)
    assets, events, samples, playbacks, waveforms = [], [], [], [], []
    views, payloads, rom_cache = {}, {}, {}
    shift = trace.interface_raw & 255
    mask = ((trace.interface_raw >> 16) & 255) or 0x70
    source_rate = native.sample_rate

    def unsupported(code, detail, gate):
        raise BankUnsupported(code, detail, gate.gate_id)

    for gate in native.gates:
        if gate.end_vgmticks <= gate.start_vgmticks:
            continue
        if loop_start is not None and (gate.start_vgmticks < loop_start < gate.end_vgmticks or
                gate.end_vgmticks == native.source_end_vgmticks and gate.termination == 'source_end'):
            unsupported('song_loop_held_gate', 'A bank playback crosses the song-loop seam', gate)
        state = starts[gate.start_event_id].state
        reg = tuple(255 if v is None else v for v in state.registers)
        left, right, _, _, end_page, delta, _, _, control = reg
        left, right = left & 127, right & 127
        if not control & 2:
            unsupported('sample_loop', 'Source sample loops require the mixed-waveform route', gate)
        if not delta:
            unsupported('zero_delta', 'A stationary source address is not a finite bank sample', gate)
        for write in writes.get((gate.chip_instance, gate.channel), ()):
            if write.source.event_id <= gate.start_event_id:
                continue
            if gate.end_event_id is not None and write.source.event_id >= gate.end_event_id:
                continue
            if write.source.vgmticks >= gate.end_vgmticks:
                continue
            expected = {'volume_left': left, 'volume_right': right, 'end_page': end_page,
                        'delta': delta, 'control': control}
            value = write.value & 127 if write.role in ('volume_left', 'volume_right') else write.value
            if write.role in ('programmed_address_low', 'programmed_address_high') or (
                    write.role in expected and value != expected[write.role]):
                unsupported('held_control', 'Address, rate, volume or pan changes during a gate require the mixed route', gate)
        if any(block.source.chip_instance == gate.chip_instance and
               block.source.event_id > gate.start_event_id and block.source.vgmticks < gate.end_vgmticks
               for block in trace.rom_blocks):
            unsupported('held_rom_update', 'Source ROM changes during a gate require the mixed route', gate)
        if not left and not right:
            continue
        key = gate.chip_instance, state.rom_generation
        if key not in rom_cache:
            rom = _Rom()
            for block in trace.rom_blocks:
                if block.source.chip_instance == gate.chip_instance and block.source.event_id < gate.start_event_id:
                    rom.update(block)
            rom_cache[key] = rom
        rom = rom_cache[key]
        cursor = cursors[gate.start_event_id].address_fixed
        boundary = (((end_page + 1) & 255) << 16) or (1 << 24)
        if cursor >> 16 == ((end_page + 1) & 255):
            # The runtime produces no source sample for this request.
            continue
        if boundary <= cursor:
            unsupported('address_wrap', 'A source view wrapping before its end page is outside the finite bank scope', gate)
        bank = (control & mask & (rom.mask >> shift)) << shift
        source_bytes = bytes(rom.read(bank + address) for address in range(cursor >> 8, boundary >> 8))
        if rom.missing_reads:
            unsupported('missing_rom', 'The complete reusable view includes unavailable ROM bytes', gate)
        frame_count = (boundary - cursor + delta - 1) // delta
        wanted = Fraction(frame_count, 1) * profile.rate / source_rate
        count = max(2, 2 * round(wanted / 2))
        if count // 2 > maximum:
            unsupported('sample_length', f'A complete reusable asset exceeds the {maximum}-byte {pdx_format} sample limit', gate)
        identity = dict(chip_instance=gate.chip_instance, rom_generation=state.rom_generation,
            bank=bank, address_fixed=cursor, end_address_fixed=boundary, delta=delta,
            source_bytes_sha256=hashlib.sha256(source_bytes).hexdigest(), pcm_profile=profile.name,
            source_rate_num=source_rate.numerator, source_rate_den=source_rate.denominator)
        view_key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        if view_key not in views:
            def value(frame):
                position = min(frame_count - 1, max(0, frame))
                address = ((cursor + position * delta) >> 8) - (cursor >> 8)
                return (source_bytes[address] - 128) * 128
            def waveform():
                for index in range(count):
                    position = max(Fraction(0), (Fraction(2 * index + 1, 2) * source_rate / profile.rate) - Fraction(1, 2))
                    low = position.numerator // position.denominator
                    fraction = position - low
                    yield round(value(low) * (1 - fraction) + value(low + 1) * fraction)
            decoded = array('h', waveform())
            encoded, error = encode_msm6258(decoded)
            sample_id = payloads.get(encoded)
            if sample_id is None:
                sample_id = len(samples)
                payloads[encoded] = sample_id
                samples.append(PcmSample(sample_id, 'msm6258-adpcm4-low-first', encoded,
                                         hashlib.sha256(encoded).hexdigest()))
            views[view_key] = sample_id, count
            waveforms.append(dict(view_id=view_key, sample_id=sample_id, samples=decoded,
                rate_num=profile.rate.numerator, rate_den=profile.rate.denominator))
            assets.append(dict(view_id=view_key, sample_id=sample_id, **identity,
                source_frame_count=frame_count, target_sample_count=count, encoded_bytes=len(encoded),
                source_duration_vgmticks=str(Fraction(frame_count * 44100, 1) / source_rate),
                duration_error_target_samples=float(count - wanted), squared_error_sum=error))
        sample_id, count = views[view_key]
        start = gate.start_vgmticks.numerator // gate.start_vgmticks.denominator
        stop = -(-gate.end_vgmticks.numerator // gate.end_vgmticks.denominator)
        level = (left + right) / 2 if left and right else max(left, right)
        gain = project_pcm8_volume(level)
        volume = gain.raw_volume
        pan = 0 if left and right else 1 if right else 2 if left else 3
        playback_id = len(playbacks)
        playbacks.append(BankPlayback(playback_id, gate.chip_instance, sample_id, start, stop,
            gate.start_source_event_id, source_ids.get(gate.end_event_id, gate.start_source_event_id), 0, 0, 0,
            profile.mdx_clock_hz, profile.mdx_divider, profile.rate.numerator, profile.rate.denominator,
            pan, False, True, 'projected_independent_pdx_decoder_assumption', gate.termination,
            True, True, count, None, (), (), source_channel=gate.channel, target_volume=volume))
        events.append(dict(playback_id=playback_id, native_gate_id=gate.gate_id, view_id=view_key,
            sample_id=sample_id, chip_instance=gate.chip_instance, source_channel=gate.channel,
            source_event_id=gate.start_source_event_id, start_event_id=gate.start_event_id,
            end_event_id=gate.end_event_id, end_source_event_id=source_ids.get(gate.end_event_id),
            loop_iteration=gate.loop_iteration, native_start_vgmticks=str(gate.start_vgmticks),
            native_end_vgmticks=str(gate.end_vgmticks), start_vgmticks=start, end_vgmticks=stop,
            termination=gate.termination, volume_left=left, volume_right=right,
            target_volume=volume, target_pan=pan, unequal_center_gains=bool(left and right and left != right),
            desired_gain=gain.desired_gain, effective_gain=gain.effective_gain,
            gain_error=gain.gain_error, volume_profile=gain.compatibility_profile))
    evidence = tuple(dict(criterion='transcoding', status='lossy', code='segapcm_bank_' + code,
        detail=detail, cause='target_projection', fallback='explicit_reusable_bank_projection') for code, detail in (
        ('resampling', 'Finite native source views are linearly resampled without antialias filtering and requantized to MSM6258'),
        ('volume_pan', 'Fixed amplitude scale128; volume is quantized to MDX @v and unequal nonzero stereo gains use their centered average'),
        ('phase_rounding', 'Gate bounds round outward by less than one source tick; native frame onset differs by less than one native frame; asset duration rounds to an even target count'),
        ('decoder_reset', 'Each PDX attack assumes an independent decoder reset; physical driver behavior is unverified')))
    evidence += (dict(criterion='source_interpretation', status='unverified', code='segapcm_runtime_model',
                     detail=native.reset_profile, cause='source_assumption'),)
    evidence += (dict(criterion='volume', status='unverified', code='segapcm_bank_driver_gain',
        detail='MXDRV/X68Sound inverse gain-table profile; resident MADRV acoustic levels have not been measured',
        cause='runtime_unverified'),)
    evidence += tuple(dict(criterion='source_interpretation', status='unverified',
        code='segapcm_source_observation', detail=issue, cause='source_assumption') for issue in native.issues)
    return BankAnalysis(native.source_end_vgmticks, tuple(samples), tuple(playbacks), (), (), TransferLog(b''),
        (), bytes(source_raw), profile.mdx_clock_hz, 4, 'derived reusable SegaPCM views; native evidence retained',
        loop_start, (), loop_count=loop_count, pcm_profile=profile.name, target_evidence=evidence,
        bank_assets=tuple(assets), bank_events=tuple(events), bank_waveforms=tuple(waveforms))


def project(trace, native, **options):
    """Prefer complete ROM views, then source-linked finite sounding parts."""
    try:
        result = _project_finite(trace, native, **options)
    except BankUnsupported as error:
        if error.reason['code'] not in ('sample_loop', 'zero_delta', 'held_control',
                                       'held_rom_update', 'address_wrap'):
            raise
        from segapcm_bank_parts import project_parts
        result = project_parts(trace, native, **options)
    return result


def select(trace, native, *, strategy='auto', outdir, stem, **options):
    """Select a whole-source strategy; capability fallback is always recorded."""
    if strategy not in ('auto', 'bank', 'mix'):
        raise ValueError('SegaPCM projection must be auto, bank or mix')
    report = dict(requested=strategy, selected=None, fallback=None)
    path = Path(outdir) / f'{stem}.segapcm_projection.json'
    for suffix in ('assets.csv', 'events.csv', 'parts.csv'):
        (Path(outdir) / f'{stem}.segapcm_bank.{suffix}').unlink(missing_ok=True)
    def save():
        path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if strategy != 'mix':
        try:
            result = project(trace, native, **options)
        except BankUnsupported as error:
            report['fallback'] = error.reason
            if strategy == 'bank':
                report['selected'] = 'blocked'
                save()
                raise
        else:
            report.update(selected='bank', sample_count=len(result.samples), playback_count=len(result.playbacks),
                          stats=result.bank_stats or dict(source_gate_count=len(native.gates),
                          source_part_count=len(result.playbacks), silent_gate_count=len(native.gates)-len(result.playbacks),
                          rom_view_count=len(result.bank_assets), trajectory_variant_count=0,
                          unique_sample_count=len(result.samples),
                          asset_payload_bytes=sum(len(s.encoded_bytes) for s in result.samples),
                          reused_playback_count=len(result.playbacks)-len({p.sample_id for p in result.playbacks}),
                          source_channel_count=len({(p.chip_instance,p.source_channel) for p in result.playbacks})))
            save()
            return result
    from segapcm_pcm import project as mixed
    result = mixed(native, **options)
    report.update(selected='mix', sample_count=len(result.samples), playback_count=len(result.playbacks))
    save()
    return result
