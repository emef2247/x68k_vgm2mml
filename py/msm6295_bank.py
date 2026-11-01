"""MSM6295 inferred native playbacks and cached independent PCM8 assets.

The reference profile is libvgm bad50c571db45b872304bdcd0603dd2214f0663e.
Source decoder and target MSM6258 encoder deliberately remain different stages.
"""
from array import array
from dataclasses import dataclass, asdict, fields
from fractions import Fraction
from pathlib import Path
import csv
import hashlib
import json
import math

from msm6258 import PcmAnalysis, PcmPlayback, PcmSample, TransferLog
from segapcm_bank import BankPlayback, BankUnsupported
from pcm_profiles import get_profile
from pcm_capacity import sample_byte_limit
from pcm8_volume import project_pcm8_volume
from opna_adpcm import encode_msm6258

MAX_ROM_BYTES = 64 * 1024 * 1024
MAX_NATIVE_SAMPLES = 16_000_000
MAX_TARGET_SAMPLES = 16_000_000
VOLUME_TABLE = (32, 22, 16, 11, 8, 6, 4, 3, 2, 0, 0, 0, 0, 0, 0, 0)
STEP_VALUES = tuple(math.floor(16 * math.pow(1.1, step)) for step in range(49))
STEP_CHANGES = (-1, -1, -1, -1, 2, 4, 6, 8)
RESET_PROFILE = 'libvgm_oki_adpcm_signal_minus2_step0'


@dataclass
class Decoder:
    signal: int = -2
    step: int = 0

    def clock(self, nibble):
        nibble &= 15
        value = STEP_VALUES[self.step]
        difference = value // 8
        if nibble & 1:
            difference += value // 4
        if nibble & 2:
            difference += value // 2
        if nibble & 4:
            difference += value
        self.signal = max(-2048, min(2047, self.signal + (-difference if nibble & 8 else difference)))
        self.step = max(0, min(48, self.step + STEP_CHANGES[nibble & 7]))
        return self.signal


def decode_adpcm(payload):
    decoder = Decoder()
    result = array('h')
    for value in payload:
        result.append(decoder.clock(value >> 4) * 16)
        result.append(decoder.clock(value & 15) * 16)
    return result


class Rom:
    def __init__(self):
        self.data = bytearray()
        self.known = bytearray()
        self.generation = 0
        self.prefix_cache = {}

    def update(self, block, *, active=False):
        if block.total > MAX_ROM_BYTES:
            raise BankUnsupported('rom_resource_limit', 'MSM6295 ROM exceeds the explicit 64 MiB budget')
        changed = len(self.data) != block.total
        if not changed:
            changed = any(not self.known[block.start + i] or self.data[block.start + i] != value
                          for i, value in enumerate(block.payload))
        if active and changed:
            raise BankUnsupported('live_rom_unsupported', 'MSM6295 ROM changes while a voice is active')
        if len(self.data) != block.total:
            self.data, self.known = bytearray(block.total), bytearray(block.total)
        self.data[block.start:block.start + len(block.payload)] = block.payload
        self.known[block.start:block.start + len(block.payload)] = b'\1' * len(block.payload)
        self.generation += 1
        self.prefix_cache.clear()

    def read(self, address):
        if not 0 <= address < len(self.data) or not self.known[address]:
            raise BankUnsupported('missing_rom', f'MSM6295 reads unavailable ROM byte {address:#x}')
        return self.data[address]

    def known_prefix(self, start, end):
        key = start, end
        if key in self.prefix_cache:
            return self.prefix_cache[key]
        limit = min(end + 1, len(self.data))
        at = start
        while at < limit and self.known[at]:
            at += 1
        payload = bytes(self.data[start:at]) if start < at else b''
        self.prefix_cache[key] = payload
        return payload


@dataclass(frozen=True)
class NativeAsset:
    sample_id: int
    payload: bytes
    sha256: str
    nominal_nibbles: int
    complete: bool
    rate_hz: int
    decoder_reset_profile: str = RESET_PROFILE
    codec: str = 'okim6295-adpcm4-high-first'


@dataclass(frozen=True)
class NativePlayback:
    playback_id: int
    sample_id: int
    source_channel: int
    sample_number: int
    attenuation: int
    source_event_id: int
    end_source_event_id: int | None
    start_event_id: int
    end_event_id: int | None
    loop_iteration: int
    start_vgmticks: int
    end_vgmticks: Fraction
    start_frame: int
    end_frame: int
    nominal_nibbles: int
    consumed_nibbles: int
    termination: str
    rom_generation: int
    latched_start: int
    latched_end: int


@dataclass(frozen=True)
class NativeAnalysis:
    source_end_vgmticks: int
    clock_hz: int
    divider: int
    rate_hz: int
    assets: tuple[NativeAsset, ...]
    playbacks: tuple[NativePlayback, ...]
    requests: tuple[dict, ...]
    states: tuple[dict, ...]

    def dump(self, outdir, stem):
        root = Path(outdir)
        root.mkdir(parents=True, exist_ok=True)
        for name, rows in (('playbacks', [asdict(p) for p in self.playbacks]),
                           ('requests', self.requests), ('voice_states', self.states)):
            columns = list(dict.fromkeys(key for row in rows for key in row))
            with (root / f'{stem}.msm6295.{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=columns or ['event_id'])
                writer.writeheader()
                writer.writerows(rows)
        rows = []
        for asset in self.assets:
            filename = f'{stem}.msm6295.sample.{asset.sample_id:04d}.adpcm'
            (root / filename).write_bytes(asset.payload)
            values = asdict(asset)
            values.pop('payload')
            rows.append(dict(**values, encoded_bytes=len(asset.payload), file=filename))
        with (root / f'{stem}.msm6295.samples.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['sample_id'])
            writer.writeheader()
            writer.writerows(rows)


def interpret(trace):
    """Infer four native voices on one persistent reference frame clock.

    No waveform is generated per playback. Sparse ROM is required only where
    an observed frame consumes it; optional unplayed sample tails can stay unknown.
    """
    if trace.issues and trace.writes:
        raise BankUnsupported('source_unsupported', '; '.join(trace.issues))
    rate = trace.rate_hz
    if trace.writes and rate <= 0:
        raise BankUnsupported('clock', 'MSM6295 clock cannot produce a native rate')
    rom = Rom()
    active, assets, asset_ids, playbacks, requests, states = {}, [], {}, [], [], []
    pending = None
    frame = 0
    native_samples = 0
    unsupported = None
    clock_buffer = bytearray(trace.clock_hz.to_bytes(4, 'little'))
    ordered = sorted([(b.event_id, 'rom', b) for b in trace.rom_blocks] +
                     [(w.event_id, 'write', w) for w in trace.writes])

    def finish(channel, at, tick, event, termination):
        voice = active.pop(channel)
        playbacks.append(NativePlayback(len(playbacks), voice['sample_id'], channel,
            voice['sample_number'], voice['attenuation'], voice['source_event_id'],
            event.source_event_id if event else None, voice['event_id'], event.event_id if event else None,
            voice['loop_iteration'], voice['start_vgmticks'], Fraction(tick),
            voice['start_frame'], at, voice['nominal_nibbles'], voice['consumed_nibbles'],
            termination, voice['rom_generation'], voice['latched_start'], voice['latched_end']))

    def advance(target):
        nonlocal frame
        for channel in tuple(active):
            voice = active[channel]
            asset = assets[voice['sample_id']]
            count = min(target - frame, voice['nominal_nibbles'] - voice['consumed_nibbles'])
            if count and (voice['consumed_nibbles'] + count - 1) // 2 >= len(asset.payload):
                missing = voice['latched_start'] + len(asset.payload)
                raise BankUnsupported('missing_rom', f'MSM6295 playback consumes unavailable ROM byte {missing:#x}')
            voice['consumed_nibbles'] += count
            if voice['consumed_nibbles'] == voice['nominal_nibbles']:
                at = frame + count
                finish(channel, at, Fraction(at * 44100, rate), None, 'natural_stop')
        frame = target

    def request(event, **values):
        row = dict(event_id=event.event_id, source_event_id=event.source_event_id,
            vgmticks=event.vgmticks, native_frame=frame, loop_iteration=event.loop_iteration,
            register=event.register, value=event.value)
        row.update(values)
        requests.append(row)

    for _, kind, event in ordered:
        if rate > 0:
            advance(-(-event.vgmticks * rate // 44100))
        if kind == 'rom':
            if event.chip_instance:
                if trace.writes:
                    raise BankUnsupported('source_unsupported', 'Second MSM6295 ROM instance is unsupported')
                continue
            rom.update(event, active=bool(active))
            continue
        if event.register != 0:
            register, value = event.register, event.value
            if 8 <= register <= 11:
                clock_buffer[register - 8] = value
                if register == 11 and int.from_bytes(clock_buffer, 'little') != trace.clock_hz:
                    unsupported = 'dynamic_clock_unsupported'
            elif register == 12:
                if bool(value) != trace.pin7_high:
                    unsupported = 'dynamic_pin7_unsupported'
            elif register == 14:
                if value:
                    unsupported = 'nmk112_unsupported'
            elif register == 15:
                if value:
                    unsupported = 'bank_switch_unsupported'
            elif register not in (16, 17, 18, 19):
                unsupported = f'extension_register_{register:02x}_unsupported'
            request(event, action='extension_write', reason=unsupported or 'reference_no_effect_in_basic_bank')
            if unsupported and active:
                raise BankUnsupported(unsupported, 'MSM6295 active voice depends on unsupported clock/bank/register state')
            continue
        value = event.value
        if pending is not None:
            sample_number, pending = pending, None
            mask, attenuation = value >> 4, value & 15
            if not mask:
                request(event, action='ignored_start', reason='empty_voice_mask', sample_number=sample_number)
            for channel in range(4):
                if not mask & (1 << channel):
                    continue
                if channel in active:
                    request(event, action='ignored_start', reason='voice_busy', source_channel=channel,
                        sample_number=sample_number, attenuation=attenuation)
                    continue
                if unsupported:
                    raise BankUnsupported(unsupported, 'MSM6295 start depends on unsupported clock/bank/register state')
                base = sample_number * 8
                start = int.from_bytes(bytes(rom.read(base + i) for i in range(3)), 'big') & 0x3ffff
                end = int.from_bytes(bytes(rom.read(base + i) for i in range(3, 6)), 'big') & 0x3ffff
                if start >= end:
                    request(event, action='ignored_start', reason='reference_invalid_sample_range',
                        source_channel=channel, sample_number=sample_number, latched_start=start, latched_end=end)
                    continue
                payload = rom.known_prefix(start, end)
                nominal = 2 * (end - start + 1)
                digest = hashlib.sha256(payload).hexdigest()
                identity = (digest, nominal, rate, RESET_PROFILE)
                sample_id = asset_ids.get(identity)
                if sample_id is None:
                    native_samples += len(payload) * 2
                    if native_samples > MAX_NATIVE_SAMPLES:
                        raise BankUnsupported('native_resource_limit', 'MSM6295 unique assets exceed the native decode budget')
                    sample_id = len(assets)
                    assets.append(NativeAsset(sample_id, payload, digest, nominal, len(payload) * 2 == nominal, rate))
                    asset_ids[identity] = sample_id
                active[channel] = dict(sample_id=sample_id, sample_number=sample_number, attenuation=attenuation,
                    source_event_id=event.source_event_id, event_id=event.event_id,
                    loop_iteration=event.loop_iteration, start_vgmticks=event.vgmticks, start_frame=frame,
                    nominal_nibbles=nominal, consumed_nibbles=0, rom_generation=rom.generation,
                    latched_start=start, latched_end=end)
                request(event, action='accepted_start', reason='reference_idle_voice', source_channel=channel,
                    sample_number=sample_number, sample_id=sample_id, attenuation=attenuation,
                    rom_generation=rom.generation, latched_start=start, latched_end=end,
                    complete_sample=assets[sample_id].complete)
        elif value & 128:
            pending = value & 127
            request(event, action='sample_select', sample_number=pending)
        else:
            for channel in range(4):
                if value & (8 << channel):
                    playing = channel in active
                    request(event, action='stop_request', reason='active_voice' if playing else 'already_idle', source_channel=channel)
                    if playing:
                        finish(channel, frame, event.vgmticks, event, 'explicit_stop')
        states.append(dict(event_id=event.event_id, source_event_id=event.source_event_id,
            vgmticks=event.vgmticks, native_frame=frame, pending_sample=pending,
            busy_mask=sum(1 << ch for ch in active),
            consumed_nibbles=' '.join(str(active[ch]['consumed_nibbles']) if ch in active else '-' for ch in range(4))))
    if rate > 0:
        advance(-(-trace.source_end_vgmticks * rate // 44100))
    for channel in tuple(active):
        finish(channel, frame, trace.source_end_vgmticks, None, 'source_end')
    playbacks.sort(key=lambda p: (p.start_event_id, p.source_channel))
    playbacks = [NativePlayback(**dict(asdict(p), playback_id=index)) for index, p in enumerate(playbacks)]
    return NativeAnalysis(trace.source_end_vgmticks, trace.clock_hz, trace.divider, rate,
        tuple(assets), tuple(playbacks), tuple(requests), tuple(states))


@dataclass(frozen=True)
class Msm6295BankAnalysis(PcmAnalysis):
    parallel_playbacks: bool = True
    source_origin: str = 'projected_msm6258_from_msm6295_bank'
    normalization_omission_safe: bool = False
    pcm_profile: str = 'standard'
    target_evidence: tuple = ()
    bank_assets: tuple = ()
    bank_events: tuple = ()
    bank_parts: tuple = ()
    bank_stats: dict | None = None
    bank_waveforms: tuple = ()
    native_analysis: NativeAnalysis | None = None

    def dump(self, outdir, stem):
        values = {f.name: getattr(self, f.name) for f in fields(PcmAnalysis)}
        values['playbacks'] = tuple(PcmPlayback(**{f.name: getattr(p, f.name) for f in fields(PcmPlayback)}) for p in self.playbacks)
        PcmAnalysis(**values).dump(outdir, stem)
        if self.native_analysis is not None:
            self.native_analysis.dump(outdir, stem)
        root = Path(outdir)
        for name, rows in (('assets', self.bank_assets), ('events', self.bank_events), ('parts', self.bank_parts)):
            columns = list(dict.fromkeys(key for row in rows for key in row))
            with (root / f'{stem}.msm6295_bank.{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=columns or ['sample_id'])
                writer.writeheader()
                writer.writerows(rows)
        path = root / f'{stem}.pcm_source.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report.update(source_origin=self.source_origin, consumption_origin='derived_msm6295_sample_bank',
            parallel_playbacks=True, pcm_profile=self.pcm_profile, target_evidence=self.target_evidence)
        path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def project(trace, *, source_raw, loop_start=None, loop_count=1, pcm_profile='standard', pdx_format='ex-pdx',
            outdir=None, stem=None):
    native = interpret(trace)
    if outdir is not None and stem is not None:
        native.dump(outdir, stem)
    profile = get_profile(pcm_profile)
    maximum = sample_byte_limit(pdx_format)
    target_assets, events, samples, playbacks, waveforms = [], [], [], [], []
    mapping, payload_ids = {}, {}
    total_target = 0
    used = {p.sample_id for p in native.playbacks if p.consumed_nibbles and VOLUME_TABLE[p.attenuation]}
    for asset in native.assets:
        if asset.sample_id not in used:
            continue
        source = decode_adpcm(asset.payload)
        count = max(2, 2 * round(Fraction(len(source), asset.rate_hz) * profile.rate / 2))
        if count // 2 > maximum:
            raise BankUnsupported('sample_length', f'MSM6295 target asset exceeds {maximum}-byte {pdx_format} limit')
        total_target += count
        if total_target > MAX_TARGET_SAMPLES:
            raise BankUnsupported('target_resource_limit', 'MSM6295 unique target assets exceed resampling budget')
        decoded = array('h')
        ratio = Fraction(asset.rate_hz, 1) / profile.rate
        for index in range(count):
            position = max(Fraction(0), Fraction(2 * index + 1, 2) * ratio - Fraction(1, 2))
            low = min(len(source) - 1, position.numerator // position.denominator)
            high = min(len(source) - 1, low + 1)
            fraction = position - position.numerator // position.denominator
            decoded.append(round(source[low] * (1 - fraction) + source[high] * fraction))
        encoded, error = encode_msm6258(decoded)
        sample_id = payload_ids.get(encoded)
        if sample_id is None:
            sample_id = len(samples)
            payload_ids[encoded] = sample_id
            samples.append(PcmSample(sample_id, 'msm6258-adpcm4-low-first', encoded, hashlib.sha256(encoded).hexdigest()))
        mapping[asset.sample_id] = sample_id, count
        view_id = f'msm6295_{asset.sample_id}'
        target_assets.append(dict(view_id=view_id, sample_id=sample_id, native_sample_id=asset.sample_id,
            native_sha256=asset.sha256, native_rate_hz=asset.rate_hz, source_nibbles=len(source),
            nominal_nibbles=asset.nominal_nibbles, complete_sample=asset.complete,
            fallback='' if asset.complete else 'optional_unavailable_tail',
            target_sample_count=count, encoded_bytes=len(encoded), squared_error_sum=error))
        waveforms.append(dict(view_id=view_id, sample_id=sample_id, samples=decoded,
            rate_num=profile.rate.numerator, rate_den=profile.rate.denominator))
    next_starts, last_by_channel = {}, {}
    for playback in reversed(native.playbacks):
        next_starts[playback.playback_id] = last_by_channel.get(playback.source_channel)
        last_by_channel[playback.source_channel] = playback.start_vgmticks
    for playback in native.playbacks:
        if playback.sample_id not in mapping or not playback.consumed_nibbles:
            continue
        gain = project_pcm8_volume(VOLUME_TABLE[playback.attenuation], source_scale=32)
        if gain.silent:
            continue
        sample_id, count = mapping[playback.sample_id]
        start = playback.start_vgmticks
        rounded_end = math.ceil(playback.end_vgmticks)
        end, bounds = rounded_end, []
        if end > trace.source_end_vgmticks:
            end = trace.source_end_vgmticks
            bounds.append('source_end')
        next_start = next_starts[playback.playback_id]
        if next_start is not None and end > next_start:
            end = next_start
            bounds.append('next_accepted_start_same_channel')
        if end <= start:
            continue
        playback_id = len(playbacks)
        playbacks.append(BankPlayback(playback_id, 0, sample_id, start, end,
            playback.source_event_id, playback.end_source_event_id if playback.end_source_event_id is not None else playback.source_event_id,
            0, 0, 0, profile.mdx_clock_hz, profile.mdx_divider,
            profile.rate.numerator, profile.rate.denominator, 0, False, True,
            'projected_independent_pdx_decoder_assumption', playback.termination, True, True,
            count, None, (), (), source_channel=playback.source_channel, target_volume=gain.raw_volume))
        events.append(dict(playback_id=playback_id, native_playback_id=playback.playback_id,
            native_sample_id=playback.sample_id, sample_id=sample_id, sample_number=playback.sample_number,
            source_channel=playback.source_channel, start_event_id=playback.start_event_id,
            source_event_id=playback.source_event_id, end_event_id=playback.end_event_id,
            end_source_event_id=playback.end_source_event_id, loop_iteration=playback.loop_iteration,
            source_start_vgmticks=start, source_end_vgmticks=str(playback.end_vgmticks),
            start_vgmticks=start, end_vgmticks=end, start_frame=playback.start_frame,
            end_frame=playback.end_frame, consumed_nibbles=playback.consumed_nibbles,
            native_start_vgmticks=str(Fraction(playback.start_frame * 44100, native.rate_hz)),
            native_start_grid_shift_vgmticks=str(Fraction(playback.start_frame * 44100, native.rate_hz) - start),
            native_end_rounded_vgmticks=rounded_end,
            native_end_rounding_vgmticks=str(Fraction(rounded_end) - playback.end_vgmticks),
            target_end_bound=';'.join(bounds), target_end_clipped_vgmticks=rounded_end - end,
            termination=playback.termination, attenuation=playback.attenuation,
            source_gain_num=VOLUME_TABLE[playback.attenuation], source_gain_den=32,
            target_volume=gain.raw_volume, effective_target_gain=gain.effective_gain,
            gain_error=gain.gain_error, rom_generation=playback.rom_generation,
            latched_start=playback.latched_start, latched_end=playback.latched_end))
    evidence = tuple(dict(criterion='transcoding', status='lossy', code='msm6295_bank_' + code,
        detail=detail, cause='target_projection') for code, detail in (
        ('resampling', 'MSM6295 high-first source ADPCM decoded independently, linearly resampled without antialias filtering and re-encoded as MSM6258'),
        ('volume', 'MSM6295 attenuation converted through PCM8 gain table; onset quantization is recorded per playback'),
        ('phase_rounding', 'Commands use a reference native grid with onset shift below one native frame; final end rounding is below one VGM tick; EOF and next accepted same-channel start bound target intervals while native endpoints remain recorded'),
        ('decoder_reset', 'Independent PDX decoder reset and physical-driver gain remain unverified')))
    stats = dict(source_gate_count=len(native.playbacks), source_part_count=len(native.playbacks),
        silent_gate_count=sum(not p.consumed_nibbles or not VOLUME_TABLE[p.attenuation] for p in native.playbacks),
        rom_view_count=len(native.assets), trajectory_variant_count=0, unique_sample_count=len(samples),
        asset_payload_bytes=sum(len(s.encoded_bytes) for s in samples),
        reused_playback_count=len(playbacks) - len({p.sample_id for p in playbacks}),
        source_channel_count=len({p.source_channel for p in native.playbacks}),
        unique_native_decoded_samples=sum(len(a.payload) * 2 for a in native.assets if a.sample_id in used),
        ignored_start_count=sum(r.get('action') == 'ignored_start' for r in native.requests),
        bounded_playback_count=sum(bool(event['target_end_bound']) for event in events))
    return Msm6295BankAnalysis(trace.source_end_vgmticks, tuple(samples), tuple(playbacks), (), (),
        TransferLog(b''), (), bytes(source_raw), profile.mdx_clock_hz, 4,
        'derived reusable MSM6295 assets; native evidence retained', loop_start, (),
        loop_count=loop_count, pcm_profile=profile.name, target_evidence=evidence,
        bank_assets=tuple(target_assets), bank_events=tuple(events), bank_stats=stats,
        bank_waveforms=tuple(waveforms), native_analysis=native)
