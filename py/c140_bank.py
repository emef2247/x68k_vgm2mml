"""C140 voices -> reusable MSM6258 assets, retaining independent native gates.

Reference: libvgm bad50c571db45b872304bdcd0603dd2214f0663e c140.c.
The source renderer is deliberately separate from PCM8/PDX target constraints.
"""
from array import array
from dataclasses import dataclass, fields
from fractions import Fraction
from pathlib import Path
import csv
import hashlib
import json
import math
import struct

from msm6258 import PcmAnalysis, PcmPlayback, PcmSample, TransferLog
from segapcm_bank import BankPlayback, BankUnsupported
from pcm_profiles import get_profile
from pcm_capacity import sample_byte_limit
from pcm8_volume import project_pcm8_volume
from opna_adpcm import encode_msm6258

MAX_ROM_BYTES = 64 * 1024 * 1024
MAX_GATE_FRAMES = 4_000_000
MAX_TOTAL_FRAMES = 48_000_000
MAX_TARGET_SAMPLES = 16_000_000
MAX_COMPLETION_FRAMES = 32_000_000


def _float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def native_delta(clock_hz, frequency):
    rate = clock_hz // 288
    base = _float32(_float32(_float32(clock_hz) / 288.0) / _float32(rate))
    return int(_float32(_float32(frequency) * base))


def decode_mulaw(value):
    """C140's custom signed 12-bit expansion, not G.711 mu-law."""
    signed = value if value < 128 else value - 256
    exponent = value & 7
    magnitude = abs(signed >> 3) & 31
    result = ((128 << exponent) & 0xff00) + (magnitude << (exponent + 3 if exponent else 4))
    return -result if value & 128 else result


def sample_address(start, bank, chip_type):
    address = (bank << 16) + start
    if chip_type == 0:
        return ((address & 0x200000) >> 2) | (address & 0x7ffff)
    if chip_type == 1:
        return ((address & 0x300000) >> 1) + (address & 0x7ffff)
    raise BankUnsupported('chip_type', 'Only C140 System 2 and System 21 banking are implemented')


class Rom:
    def __init__(self):
        self.total = 0
        self.data = bytearray()
        self.known = bytearray()
        self.generation = 0

    def update(self, block):
        if block.total > MAX_ROM_BYTES:
            raise BankUnsupported('rom_resource_limit', 'C140 ROM exceeds the explicit 64 MiB allocation budget')
        if block.total != self.total:
            self.total = block.total
            self.data = bytearray(block.total)
            self.known = bytearray(block.total)
        self.data[block.start:block.start + len(block.payload)] = block.payload
        self.known[block.start:block.start + len(block.payload)] = b'\1' * len(block.payload)
        self.generation += 1

    def read(self, address):
        if not self.total:
            raise BankUnsupported('missing_rom', 'C140 voice reads before any ROM is supplied')
        address &= (1 << (self.total - 1).bit_length()) - 1
        if address >= self.total or not self.known[address]:
            raise BankUnsupported('missing_rom', f'C140 voice reads unavailable ROM byte {address:#x}')
        return self.data[address]


@dataclass
class Voice:
    registers: list[int]
    start: int
    end: int
    loop: int
    position: int = 0
    fraction: int = 0
    last: int = 0
    previous: int = 0
    difference: int = 0
    key: bool = True

    def step(self, rom, chip_type, clock_hz):
        frequency = (self.registers[2] << 8) | self.registers[3]
        if not self.key:
            return None
        if not frequency:
            return 0
        self.fraction += native_delta(clock_hz, frequency)
        count = (self.fraction >> 16) & 0x7fff
        self.fraction &= 0xffff
        self.position += count
        if self.position >= self.end - self.start:
            if self.registers[5] & 0x10:
                self.position = self.loop - self.start
                if not 0 <= self.position < self.end - self.start:
                    raise BankUnsupported('invalid_loop', 'C140 latched loop lies outside the sample interval')
            else:
                self.key = False
                return None
        if count:
            value = rom.read(sample_address(self.start, self.registers[4], chip_type) + self.position)
            self.previous = self.last
            self.last = decode_mulaw(value) if self.registers[5] & 8 else ((value if value < 128 else value - 256) << 8)
            self.difference = self.last - self.previous
        return ((self.difference * self.fraction) >> 16) + self.previous


@dataclass(frozen=True)
class C140BankAnalysis(PcmAnalysis):
    parallel_playbacks: bool = True
    source_origin: str = 'projected_msm6258_from_c140_bank'
    normalization_omission_safe: bool = False
    pcm_profile: str = 'standard'
    target_evidence: tuple[dict, ...] = ()
    bank_assets: tuple[dict, ...] = ()
    bank_events: tuple[dict, ...] = ()
    bank_parts: tuple[dict, ...] = ()
    bank_stats: dict | None = None
    bank_waveforms: tuple[dict, ...] = ()

    def dump(self, outdir, stem):
        values = {f.name: getattr(self, f.name) for f in fields(PcmAnalysis)}
        values['playbacks'] = tuple(PcmPlayback(**{f.name: getattr(p, f.name) for f in fields(PcmPlayback)}) for p in self.playbacks)
        PcmAnalysis(**values).dump(outdir, stem)
        root = Path(outdir)
        for name, rows in (('assets', self.bank_assets), ('events', self.bank_events), ('parts', self.bank_parts)):
            with (root / f'{stem}.c140_bank.{name}.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ['sample_id'])
                writer.writeheader()
                writer.writerows(rows)
        path = root / f'{stem}.pcm_source.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report.update(source_origin=self.source_origin, consumption_origin='derived_c140_independent_voices',
                      parallel_playbacks=True, pcm_profile=self.pcm_profile, target_evidence=self.target_evidence)
        path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def render_gates(trace):
    """Interpret live controls on one persistent native frame clock.

    Gate captures preserve fractional cursor and interpolation through controls,
    pauses and song-loop traversals. There is never an invented attack at a seam.
    """
    if trace.issues:
        raise BankUnsupported('source_unsupported', '; '.join(trace.issues))
    if trace.clock_hz < 288:
        raise BankUnsupported('clock', 'C140 clock cannot produce a native sample rate')
    rate = trace.clock_hz // 288
    rom = Rom()
    registers = [[0] * 16 for _ in range(24)]
    active = {}
    gates = []
    frame = 0
    total_frames = 0
    ordered = sorted([(b.event_id, 'rom', b) for b in trace.rom_blocks] +
                     [(w.event_id, 'write', w) for w in trace.writes])

    def finish(channel, end_frame, tick, event, termination):
        gate = active.pop(channel)
        gate.update(end_frame=end_frame, end_vgmticks=tick,
                    end_event_id=event.event_id if event else None,
                    end_source_event_id=event.source_event_id if event else None, termination=termination)
        gates.append(gate)

    def make_dynamic(gate):
        if not gate['dynamic']:
            initial = gate['initial_registers']
            left, right = initial[1], initial[0]
            level = (left + right) / 2 if left and right else max(left, right)
            gate['wave'] = array('h', (round(value * level / 510) for value in gate['wave']))
            gate['dynamic'] = True

    def advance(target):
        nonlocal frame, total_frames
        length = target - frame
        for channel in tuple(active):
            gate = active[channel]
            voice = gate['voice']
            needed = length
            frequency = (voice.registers[2] << 8) | voice.registers[3]
            if frequency and not voice.registers[5] & 0x10:
                delta = native_delta(trace.clock_hz, frequency)
                remaining = (voice.end - voice.start - voice.position) * 65536 - voice.fraction
                needed = min(length, max(0, (remaining + delta - 1) // delta))
            if len(gate['wave']) + needed > MAX_GATE_FRAMES:
                raise BankUnsupported('gate_resource_limit', 'C140 per-voice capture exceeds its explicit frame budget', gate['gate_id'])
            if total_frames + needed > MAX_TOTAL_FRAMES:
                raise BankUnsupported('total_resource_limit', 'C140 captures exceed the explicit aggregate frame budget', gate['gate_id'])
            for at in range(frame, target):
                value = voice.step(rom, trace.chip_type, trace.clock_hz)
                if value is None:
                    finish(channel, at, Fraction(at * 44100, rate), None, 'natural_stop')
                    break
                left, right = voice.registers[1], voice.registers[0]
                level = (left + right) / 2 if left and right else max(left, right)
                gate['wave'].append(round(value * level / 510) if gate['dynamic'] else value)
                total_frames += 1
        frame = target

    for _, kind, event in ordered:
        target = -(-event.vgmticks * rate // 44100)
        advance(target)
        if kind == 'rom':
            for gate in active.values():
                make_dynamic(gate)
            rom.update(event)
            continue
        if event.register >= 0x180:
            continue
        channel, register = divmod(event.register, 16)
        reg = registers[channel]
        previous = reg[register]
        reg[register] = event.value
        if register == 5:
            if channel in active:
                finish(channel, frame, event.vgmticks, event,
                       'retrigger' if event.value & 0x80 else 'key_off')
            if event.value & 0x80:
                start, end, loop = ((reg[i] << 8) | reg[i + 1] for i in (6, 8, 10))
                if end <= start:
                    raise BankUnsupported('sample_range', 'C140 KEYON has a nonpositive latched sample interval')
                gate_id = len(gates) + len(active)
                active[channel] = dict(gate_id=gate_id, source_channel=channel,
                    start_vgmticks=event.vgmticks, start_frame=frame, start_event_id=event.event_id,
                    source_event_id=event.source_event_id, loop_iteration=event.loop_iteration,
                    initial_registers=tuple(reg), rom_generation=rom.generation,
                    voice=Voice(reg, start, end, loop), dynamic=False, wave=array('h'))
        elif channel in active and register <= 4 and previous != event.value:
            make_dynamic(active[channel])
    advance(-(-trace.source_end_vgmticks * rate // 44100))
    for channel in tuple(active):
        finish(channel, frame, trace.source_end_vgmticks, None, 'source_end')
    return sorted(gates, key=lambda g: (g['start_event_id'], g['source_channel'])), rate


def project(trace, *, source_raw, loop_start=None, loop_count=1, pcm_profile='standard', pdx_format='ex-pdx'):
    profile = get_profile(pcm_profile)
    maximum = sample_byte_limit(pdx_format)
    gates, rate = render_gates(trace)
    samples, playbacks, assets, events, waveforms = [], [], [], [], []
    payloads, views, completions = {}, {}, {}
    completion_rom = Rom()
    completion_generation = 0
    completion_frames = 0
    completion_fallbacks = 0
    total_target = 0
    silent = 0
    for gate in gates:
        if not gate['wave'] or gate['end_vgmticks'] <= gate['start_vgmticks']:
            silent += 1
            continue
        reg = gate['initial_registers']
        dynamic = gate['dynamic']
        looping = bool(reg[5] & 0x10)
        source = gate['wave'] if dynamic else array('h', (value // 2 for value in gate['wave']))
        complete = False
        completion_fallback = ''
        # A constant one-shot is a reusable complete asset, independent of keyoff
        # time and onset volume/pan. Variable/looping voices retain the captured
        # trajectory and are shared only by actual converted waveform identity.
        if not dynamic and not looping and ((reg[2] << 8) | reg[3]):
            length = ((reg[8] << 8) | reg[9]) - ((reg[6] << 8) | reg[7])
            delta = native_delta(trace.clock_hz, (reg[2] << 8) | reg[3])
            bound = (length * 65536 + delta - 1) // delta
            generation = gate['rom_generation']
            key = (generation, trace.chip_type, reg[4], (reg[6] << 8) | reg[7],
                   (reg[8] << 8) | reg[9], (reg[10] << 8) | reg[11],
                   (reg[2] << 8) | reg[3], reg[5])
            if key not in completions:
                if bound + 1 > MAX_GATE_FRAMES or completion_frames + bound + 1 > MAX_COMPLETION_FRAMES:
                    completions[key] = None, 'completion_resource_limit'
                else:
                    # Gates are ordered by onset; keep only one mutable sparse
                    # ROM snapshot, rather than one whole allocation per view.
                    if generation < completion_generation:
                        completion_rom = Rom()
                        completion_generation = 0
                    for block in trace.rom_blocks[completion_generation:generation]:
                        completion_rom.update(block)
                    completion_generation = generation
                    voice = Voice(list(reg), key[3], key[4], key[5])
                    expanded = array('h')
                    # Charge the attempted expansion before work, including
                    # failed missing-tail attempts. Cache failures as well.
                    completion_frames += bound + 1
                    try:
                        for _ in range(bound + 1):
                            value = voice.step(completion_rom, trace.chip_type, trace.clock_hz)
                            if value is None:
                                break
                            expanded.append(value // 2)
                    except BankUnsupported as error:
                        if error.reason['code'] != 'missing_rom':
                            raise
                        completions[key] = None, 'optional_tail_missing_rom'
                    else:
                        completions[key] = expanded, ''
            expanded, completion_fallback = completions[key]
            if expanded is not None:
                source, complete = expanded, True
            else:
                completion_fallbacks += 1
        if not any(source):
            silent += 1
            continue
        count = max(2, 2 * round(Fraction(len(source), rate) * profile.rate / 2))
        if count // 2 > maximum:
            raise BankUnsupported('sample_length', f'C140 target asset exceeds {maximum}-byte {pdx_format} limit', gate['gate_id'])
        identity = hashlib.sha256(source.tobytes() + str((rate, profile.rate)).encode()).hexdigest()
        if identity not in views:
            total_target += count
            if total_target > MAX_TARGET_SAMPLES:
                raise BankUnsupported('target_resource_limit', 'C140 resampling exceeds its explicit aggregate target sample budget', gate['gate_id'])
            decoded = array('h')
            ratio = Fraction(rate, 1) / profile.rate
            for index in range(count):
                position = max(Fraction(0), (Fraction(2 * index + 1, 2) * ratio) - Fraction(1, 2))
                low = min(len(source) - 1, position.numerator // position.denominator)
                high = min(len(source) - 1, low + 1)
                fraction = position - position.numerator // position.denominator
                decoded.append(round(source[low] * (1 - fraction) + source[high] * fraction))
            encoded, error = encode_msm6258(decoded)
            sample_id = payloads.get(encoded)
            if sample_id is None:
                sample_id = len(samples)
                payloads[encoded] = sample_id
                samples.append(PcmSample(sample_id, 'msm6258-adpcm4-low-first', encoded,
                                         hashlib.sha256(encoded).hexdigest()))
            views[identity] = sample_id, count
            waveforms.append(dict(view_id=identity, sample_id=sample_id, samples=decoded,
                                  rate_num=profile.rate.numerator, rate_den=profile.rate.denominator))
            assets.append(dict(view_id=identity, sample_id=sample_id, source_frame_count=len(source),
                source_rate_num=rate, source_rate_den=1, target_sample_count=count, encoded_bytes=len(encoded),
                complete_one_shot=complete, completion_fallback=completion_fallback,
                held_control_variant=dynamic, internal_loop=looping,
                squared_error_sum=error))
        sample_id, count = views[identity]
        left, right = reg[1], reg[0]
        if not dynamic:
            level = (left + right) / 2 if left and right else max(left, right)
            gain = project_pcm8_volume(level, source_scale=255)
            if gain.silent:
                silent += 1
                continue
            volume = gain.raw_volume
            pan = 0 if left and right else 1 if right else 2
        else:
            volume, pan = 128, 0
        start = int(gate['start_vgmticks'])
        stop = math.ceil(gate['end_vgmticks'])
        playback_id = len(playbacks)
        playbacks.append(BankPlayback(playback_id, 0, sample_id, start, stop,
            gate['source_event_id'], gate['end_source_event_id'] if gate['end_source_event_id'] is not None else gate['source_event_id'],
            0, 0, 0, profile.mdx_clock_hz, profile.mdx_divider,
            profile.rate.numerator, profile.rate.denominator, pan, False, True,
            'projected_independent_pdx_decoder_assumption', gate['termination'], True, True,
            count, None, (), (), source_channel=gate['source_channel'], target_volume=volume))
        events.append(dict(playback_id=playback_id, native_gate_id=gate['gate_id'], source_channel=gate['source_channel'],
            sample_id=sample_id, view_id=identity, start_event_id=gate['start_event_id'],
            source_event_id=gate['source_event_id'], end_event_id=gate['end_event_id'],
            rom_generation=gate['rom_generation'], initial_bank=reg[4],
            initial_frequency=(reg[2] << 8) | reg[3],
            latched_start=(reg[6] << 8) | reg[7], latched_end=(reg[8] << 8) | reg[9],
            latched_loop=(reg[10] << 8) | reg[11],
            source_codec='custom_mulaw' if reg[5] & 8 else 'linear_signed8',
            chip_type=trace.chip_type,
            end_source_event_id=gate['end_source_event_id'], loop_iteration=gate['loop_iteration'],
            native_start_vgmticks=str(gate['start_vgmticks']), native_end_vgmticks=str(gate['end_vgmticks']),
            start_vgmticks=start, end_vgmticks=stop, termination=gate['termination'],
            target_volume=volume, target_pan=pan, held_control_variant=dynamic, complete_one_shot=complete,
            completion_fallback=completion_fallback))
    evidence = tuple(dict(criterion='transcoding', status='lossy', code='c140_bank_' + code,
                         detail=detail, cause='target_projection') for code, detail in (
        ('resampling', 'Native per-voice linear interpolation is resampled without antialias filtering and encoded as MSM6258'),
        ('volume_pan', 'Fixed waveform scale 1/2; onset gains quantized to PCM8; unequal stereo gains are averaged; held gain/pan variants are baked once and centered'),
        ('phase_rounding', 'Commands apply before the next native frame; target event bounds round outward by less than one VGM tick'),
        ('decoder_reset', 'Independent PDX decoder reset and physical-driver gain remain unverified')))
    stats = dict(source_gate_count=len(gates), source_part_count=len(gates), silent_gate_count=silent,
        rom_view_count=len(assets), trajectory_variant_count=sum(a['held_control_variant'] for a in assets),
        unique_sample_count=len(samples), asset_payload_bytes=sum(len(s.encoded_bytes) for s in samples),
        reused_playback_count=len(playbacks) - len({p.sample_id for p in playbacks}),
        source_channel_count=len({g['source_channel'] for g in gates}),
        completion_native_frames=completion_frames, completion_frame_budget=MAX_COMPLETION_FRAMES,
        completion_cached_views=len(completions), completion_fallback_gates=completion_fallbacks)
    return C140BankAnalysis(trace.source_end_vgmticks, tuple(samples), tuple(playbacks), (), (),
        TransferLog(b''), (), bytes(source_raw), profile.mdx_clock_hz, 4,
        'derived reusable C140 voices; native evidence retained', loop_start, (),
        loop_count=loop_count, pcm_profile=profile.name, target_evidence=evidence,
        bank_assets=tuple(assets), bank_events=tuple(events), bank_stats=stats,
        bank_waveforms=tuple(waveforms))
