"""Frame-effective finite SegaPCM parts; native evidence remains unchanged.

An address discontinuity is a seek, not an inferred key attack. Gain/rate writes
remain inside a part. Complete stable ROM views and bounded baked trajectories
have separate identities and diagnostics.
"""
from array import array
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json

from msm6258 import PcmSample, TransferLog
from opna_adpcm import encode_msm6258
from pcm8_volume import project_pcm8_volume
from pcm_profiles import get_profile
from segapcm_playback import _Rom, render


MAX_CAPTURE_FRAMES = 16_000_000
MAX_VARIANT_BYTES = 2_000_000


@dataclass
class _Part:
    chip: int
    channel: int
    origin: object
    first_frame: int
    address: int
    parameters: tuple
    first_event: object
    boundary: str
    audio: array = field(default_factory=lambda: array('h'))
    changes: list = field(default_factory=list)
    last_frame: int = 0
    last_address: int = 0
    last_parameters: tuple = ()
    looped: bool = False


class PartCollector:
    def __init__(self):
        self.parts = []
        self.active = {}
        self.frame_count = 0
        self.missing_rom_reads = 0
        self.missing_audible_reads = 0
        self.first_missing_audible = None

    def missing_rom(self, frame, chip, channel, address, generation, bank, left, right, source):
        self.missing_rom_reads += 1
        if left or right:
            self.missing_audible_reads += 1
            if self.first_missing_audible is None:
                self.first_missing_audible = dict(frame=frame, chip=chip, channel=channel,
                    address_fixed=address, bank=bank, rom_generation=generation,
                    source_event_id=source.source_event_id)

    def __call__(self, frame, chip, channel, origin, address, parameters, sample, source, looped):
        from segapcm_bank import BankUnsupported
        key = chip, channel
        previous = self.active.get(key)
        continuous = (previous is not None and previous.origin.event_id == origin.event_id
                      and previous.last_frame + 1 == frame)
        seek = continuous and address != ((previous.last_address + previous.last_parameters[2]) & 0xffffff)
        if not continuous or seek:
            previous = _Part(chip, channel, origin, frame, address, parameters, source,
                             'seek' if seek else 'enable')
            self.parts.append(previous)
            self.active[key] = previous
        if parameters != previous.last_parameters:
            previous.changes.append((len(previous.audio), parameters, address, source.event_id))
        left, right = parameters[:2]
        # Fixed scale128: variant waveforms include absolute source gains once.
        level = Fraction(left + right, 2) if left and right else max(left, right)
        previous.audio.append(round(sample * level))
        previous.last_frame, previous.last_address = frame, address
        previous.last_parameters = parameters
        previous.looped |= looped and bool(left or right)
        self.frame_count += 1
        if self.frame_count > MAX_CAPTURE_FRAMES:
            raise BankUnsupported('part_resource_limit', 'Per-voice capture exceeds its explicit frame budget')


def _resample(values, source_rate, target_rate, count):
    """Use the finite-view adapter's centre-aligned linear interpolation."""
    ratio = source_rate / target_rate
    for index in range(count):
        position = max(Fraction(0), Fraction(2 * index + 1, 2) * ratio - Fraction(1, 2))
        low = position.numerator // position.denominator
        fraction = position - low
        a = values[min(low, len(values) - 1)]
        b = values[min(low + 1, len(values) - 1)]
        yield round(a * (1 - fraction) + b * fraction)


def project_parts(trace, native, *, source_raw, loop_start=None, loop_count=1, pcm_profile='standard'):
    from segapcm_bank import BankAnalysis, BankPlayback, BankUnsupported
    profile = get_profile(pcm_profile)
    collector = PartCollector()
    replay = render(trace, native.source_end_vgmticks, loop_start=loop_start, voice_sink=collector)
    if replay.gates != native.gates or replay.samples != native.samples:
        raise ValueError('SegaPCM voice capture differs from the original native render')
    if collector.missing_audible_reads:
        missing = collector.first_missing_audible
        raise BankUnsupported('missing_rom',
            f"{collector.missing_audible_reads} audible voice frames contain unavailable ROM; "
            f"first frame={missing['frame']} chip={missing['chip']} channel={missing['channel']} "
            f"generation={missing['rom_generation']} bank={missing['bank']} "
            f"address_fixed={missing['address_fixed']} source_event={missing['source_event_id']}")
    gates = {(g.chip_instance, g.channel, g.start_event_id): g for g in native.gates}
    roms, payloads, views = {}, {}, {}
    samples, playbacks, assets, events, part_rows, waveforms = [], [], [], [], [], []
    trajectory_bytes = 0
    silent_parts = 0
    step = Fraction(44100, 1) / native.sample_rate

    def source_rom(chip, generation):
        key = chip, generation
        if key not in roms:
            memory = _Rom()
            for block in trace.rom_blocks:
                if block.source.chip_instance == chip and block.rom_generation <= generation:
                    memory.update(block)
            roms[key] = memory
        return roms[key]

    for part_id, part in enumerate(collector.parts):
        gate = gates[(part.chip, part.channel, part.origin.event_id)]
        # Only zero gains prove silent here; zero delta can hold nonzero DC.
        changes = part.changes
        audible = [i for i, (_, params, _, _) in enumerate(changes) if params[0] or params[1]]
        if not audible:
            silent_parts += 1
            part_rows.append(dict(part_id=part_id, native_gate_id=gate.gate_id,
                boundary=part.boundary, classification='silent', start_frame=part.first_frame,
                end_frame=part.last_frame + 1, leading_silent_frames=len(part.audio), view_id=''))
            continue
        first_change = audible[0]
        offset, parameters, cursor, event_id = changes[first_change]
        last_audible = audible[-1]
        end_offset = (changes[last_audible + 1][0] if last_audible + 1 < len(changes) else len(part.audio))
        effective_changes = [c for c in changes[first_change:] if c[0] < end_offset]
        if part.looped:
            raise BankUnsupported('sample_loop', 'Audible source sample loops still require the mixed route', gate.gate_id)
        first_frame = part.first_frame + offset
        end_frame = part.first_frame + end_offset
        start_exact = first_frame * step
        end_exact = min(end_frame * step, native.source_end_vgmticks)
        if loop_start is not None and (start_exact < loop_start < end_exact or
                end_exact == native.source_end_vgmticks and gate.termination == 'source_end'):
            raise BankUnsupported('song_loop_held_gate', 'A bank part crosses the song-loop seam', gate.gate_id)
        # One canonical rounding for both sides of a seek, never ceil/floor overlap.
        start, stop = round(start_exact), round(end_exact)
        if stop <= start:
            raise BankUnsupported('part_timing', 'An audible part has no representable source-tick duration', gate.gate_id)
        left, right, delta, end_page, control, generation, bank = parameters
        stable = all(c[1] == parameters for c in effective_changes) and delta > 0
        boundary = (((end_page + 1) & 255) << 16) or (1 << 24)
        stable = stable and boundary > cursor
        kind = 'rom_view' if stable else 'trajectory_variant'
        if stable:
            memory = source_rom(part.chip, generation)
            missing = memory.missing_reads
            source_bytes = bytes(memory.read(bank + address)
                                 for address in range(cursor >> 8, boundary >> 8))
            if memory.missing_reads != missing:
                raise BankUnsupported('missing_rom', 'Complete finite view includes unavailable ROM', gate.gate_id)
            frame_count = (boundary - cursor + delta - 1) // delta
            identity = dict(kind=kind, bank=bank, address_fixed=cursor,
                end_address_fixed=boundary, delta=delta,
                source_bytes_sha256=hashlib.sha256(source_bytes).hexdigest(),
                source_rate=str(native.sample_rate), pcm_profile=profile.name)
            gain = project_pcm8_volume(Fraction(left + right, 2) if left and right else max(left, right))
            pan = 0 if left and right else 1 if right else 2
            def waveform_values():
                return array('h', ((source_bytes[((cursor + i * delta) >> 8) - (cursor >> 8)] - 128) * 128
                                   for i in range(frame_count)))
        else:
            data = part.audio[offset:end_offset]
            frame_count = len(data)
            identity = dict(kind=kind, source_wave_sha256=hashlib.sha256(
                b''.join(int(v).to_bytes(2, 'little', signed=True) for v in data)).hexdigest(),
                source_rate=str(native.sample_rate), pcm_profile=profile.name)
            gain = project_pcm8_volume(128)
            pans = {0 if c[1][0] and c[1][1] else 1 if c[1][1] else 2
                    for c in effective_changes if c[1][0] or c[1][1]}
            pan = next(iter(pans)) if len(pans) == 1 else 0
            def waveform_values():
                return data
        wanted = Fraction(frame_count) * profile.rate / native.sample_rate
        count = max(2, 2 * round(wanted / 2))
        if count // 2 > 65535:
            raise BankUnsupported('sample_length', 'A finite part exceeds 65535 encoded bytes', gate.gate_id)
        view_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        if view_id not in views:
            decoded = array('h', _resample(waveform_values(), native.sample_rate, profile.rate, count))
            encoded, error = encode_msm6258(decoded)
            if encoded not in payloads:
                if not stable:
                    trajectory_bytes += len(encoded)
                    if trajectory_bytes > MAX_VARIANT_BYTES:
                        raise BankUnsupported('variant_budget', 'Unique trajectory variants exceed their explicit byte budget', gate.gate_id)
                sample_id = len(samples)
                payloads[encoded] = sample_id
                samples.append(PcmSample(sample_id, 'msm6258-adpcm4-low-first', encoded,
                                         hashlib.sha256(encoded).hexdigest()))
            sample_id = payloads[encoded]
            views[view_id] = sample_id
            waveforms.append(dict(view_id=view_id, sample_id=sample_id, samples=decoded,
                rate_num=profile.rate.numerator, rate_den=profile.rate.denominator))
            assets.append(dict(view_id=view_id, sample_id=sample_id, asset_kind=kind,
                encoded_bytes=len(encoded), target_sample_count=count, source_frame_count=frame_count,
                source_duration_vgmticks=str(frame_count * step),
                duration_error_target_samples=float(count - wanted), squared_error_sum=error,
                identity_json=json.dumps(identity, sort_keys=True)))
        sample_id = views[view_id]
        playback_id = len(playbacks)
        termination = 'seek' if part.last_frame + 1 < round(gate.end_vgmticks / step) else gate.termination
        playbacks.append(BankPlayback(playback_id, part.chip, sample_id, start, stop,
            part.first_event.source_event_id, part.origin.source_event_id,
            0, 0, 0, profile.mdx_clock_hz, profile.mdx_divider,
            profile.rate.numerator, profile.rate.denominator, pan, False, True,
            'projected_independent_pdx_decoder_assumption', termination, True, True,
            count, None, (), (), source_channel=part.channel, target_volume=gain.raw_volume))
        events.append(dict(playback_id=playback_id, part_id=part_id, native_gate_id=gate.gate_id,
            view_id=view_id, sample_id=sample_id, asset_kind=kind, chip_instance=part.chip,
            source_channel=part.channel, start_event_id=event_id,
            source_event_id=part.first_event.source_event_id,
            enable_source_event_id=part.origin.source_event_id,
            loop_iteration=gate.loop_iteration, native_start_vgmticks=str(start_exact),
            native_end_vgmticks=str(end_exact), start_vgmticks=start, end_vgmticks=stop,
            boundary=part.boundary if not offset else 'unmute', termination=termination,
            address_fixed=cursor, rom_generation=generation, bank=bank,
            volume_left=left, volume_right=right, target_volume=gain.raw_volume, target_pan=pan,
            desired_gain=gain.desired_gain, effective_gain=gain.effective_gain, gain_error=gain.gain_error,
            volume_baked=not stable, control_run_count=len(effective_changes),
            unequal_center_gains=any(c[1][0] and c[1][1] and c[1][0] != c[1][1] for c in effective_changes),
            pan_trajectory_collapsed=not stable and len(pans) > 1))
        part_rows.append(dict(part_id=part_id, native_gate_id=gate.gate_id,
            boundary=part.boundary, classification=kind, start_frame=first_frame,
            end_frame=end_frame, leading_silent_frames=offset, view_id=view_id))
    evidence = (
        dict(criterion='transcoding', status='lossy', code='segapcm_bank_resampling',
             detail='Finite source-linked parts use linear resampling without antialias filtering and MSM6258 requantization', cause='target_projection'),
        dict(criterion='volume', status='unverified', code='segapcm_bank_driver_gain',
             detail='Inverse MXDRV/X68Sound onset gain profile; native resident driver amplitude remains unmeasured', cause='runtime_unverified'),
        dict(criterion='source_interpretation', status='unverified', code='segapcm_runtime_model',
             detail=native.reset_profile, cause='source_assumption'),
        dict(criterion='transcoding', status='lossy', code='segapcm_part_decoder_reset',
             detail='Each part assumes independent ADPCM decoder reset; a cursor seek is not a native key attack', cause='target_projection'),
        dict(criterion='timing', status='lossy', code='segapcm_bank_frame_rounding',
             detail='Shared part boundaries round once to source ticks; events use MDX clock without waveform stretching', cause='target_projection'),
    )
    if any(e['unequal_center_gains'] or e['pan_trajectory_collapsed'] for e in events):
        evidence += (dict(criterion='pan', status='lossy', code='segapcm_bank_stereo_collapse',
            detail='Unequal stereo gains use their average; changing non-silent pan is centered within a finite variant', cause='target_projection'),)
    stats = dict(missing_rom_reads=collector.missing_rom_reads,
        muted_missing_rom_reads=collector.missing_rom_reads - collector.missing_audible_reads,
        source_gate_count=len(native.gates), source_part_count=len(part_rows),
        silent_gate_count=len({g.gate_id for g in native.gates} - {e['native_gate_id'] for e in events}),
        silent_part_count=silent_parts, rom_view_count=sum(a['asset_kind'] == 'rom_view' for a in assets),
        trajectory_variant_count=sum(a['asset_kind'] == 'trajectory_variant' for a in assets),
        unique_sample_count=len(samples), asset_payload_bytes=sum(len(s.encoded_bytes) for s in samples),
        reused_playback_count=len(playbacks)-len({p.sample_id for p in playbacks}),
        source_channel_count=len({(p.chip_instance,p.source_channel) for p in playbacks}),
        seek_part_count=sum(e['boundary'] == 'seek' for e in events),
        leading_silent_frames=sum(r['leading_silent_frames'] for r in part_rows),
        actual_sample_loop_count=sum(e.kind == 'sample_loop' for e in native.runtime_events))
    return BankAnalysis(native.source_end_vgmticks, tuple(samples), tuple(playbacks), (), (), TransferLog(b''),
        (), bytes(source_raw), profile.mdx_clock_hz, 4,
        'source-linked finite SegaPCM parts; immutable assets, common scale128', loop_start, (),
        loop_count=loop_count, pcm_profile=profile.name, target_evidence=evidence,
        bank_assets=tuple(assets), bank_events=tuple(events), bank_parts=tuple(part_rows), bank_stats=stats,
        bank_waveforms=tuple(waveforms))
