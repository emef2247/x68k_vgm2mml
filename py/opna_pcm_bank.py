"""Finite independent Delta-T epochs projected into reusable PCM8 assets.

Native ADPCM-B evidence is untouched. Unsupported source capabilities return
None so the established continuous/legacy projection can retain its behavior.
Malformed evidence is an error, never a capability fallback.
"""
import csv
from dataclasses import dataclass, fields
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from msm6258 import PcmAnalysis, PcmPlayback, PcmSample, TransferLog
from opna_adpcm import decode_adpcm_b, encode_msm6258
from opna_pcm import ProjectedPcmAnalysis
from pcm8_volume import project_pcm8_volume
from pcm_profiles import get_profile
from pcm_capacity import sample_byte_limit

MAX_DECODED_SAMPLES = 1000000
MAX_TOTAL_SAMPLES = 8000000


@dataclass(frozen=True)
class BankPlayback(PcmPlayback):
    source_channel: int = 0
    target_volume: int = 128


@dataclass(frozen=True)
class ProjectedBankAnalysis(ProjectedPcmAnalysis):
    source_origin: str = 'projected_msm6258_from_opna_adpcm_b_bank'
    parallel_playbacks: bool = True
    normalization_omission_safe: bool = False
    bank_assets: tuple[dict, ...] = ()
    bank_events: tuple[dict, ...] = ()

    def dump(self, outdir, stem):
        values = {f.name: getattr(self, f.name) for f in fields(PcmAnalysis)}
        values['playbacks'] = tuple(PcmPlayback(**{f.name: getattr(p, f.name)
            for f in fields(PcmPlayback)}) for p in self.playbacks)
        PcmAnalysis(**values).dump(outdir, stem)
        source_path = Path(outdir) / (stem + '.pcm_source.json')
        report = json.loads(source_path.read_text(encoding='utf-8'))
        report.update(source_origin=self.source_origin, parallel_playbacks=True,
                      consumption_origin='derived_complete_adpcm_b_sample',
                      target_evidence=self.target_evidence)
        source_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        self.dump_bridge(outdir, stem)

    def dump_bridge(self, outdir, stem):
        path = super().dump_bridge(outdir, stem)
        for name, rows in (('assets', self.bank_assets), ('events', self.bank_events)):
            with (Path(outdir) / f'{stem}.opna_pcm_bank.{name}.csv').open(
                    'w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]) if rows else ('sample_id',))
                writer.writeheader()
                writer.writerows(rows)
        report = json.loads(path.read_text(encoding='utf-8'))
        report.update(bank_projection='finite independent complete samples',
                      sample_amplitude_scale=256, parallel_playbacks=True,
                      asset_clock_alignment='immutable; only playback events use the shared clock')
        path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        return path


def project(native, *, source_raw, loop_start=None, pcm_profile='standard', pdx_format='ex-pdx'):
    """Return a finite bank, or None for controls/resources outside this scope."""
    from pcm_mdx import RATES
    maximum = sample_byte_limit(pdx_format)
    profile = get_profile(pcm_profile)
    source_raw = bytes(source_raw)
    if hashlib.sha256(source_raw).hexdigest() != native.source_sha256:
        raise ValueError('PCM bank source bytes differ from native OPNA evidence')
    sources = {}
    for sample in native.samples:
        if sample.sample_id in sources:
            raise ValueError('Duplicate native OPNA PCM sample ID')
        if sample.codec != 'yamaha_adpcm_b_high_nibble_first':
            raise ValueError('PCM bank requires native ADPCM-B codec')
        if hashlib.sha256(sample.encoded_bytes).hexdigest() != sample.sha256:
            raise ValueError('Native OPNA PCM sample hash mismatch')
        if not sample.encoded_bytes:
            raise ValueError('Native OPNA PCM sample is empty')
        sources[sample.sample_id] = sample
    if any(not issue.code.endswith('_seeded_from_vgm_rom_block_assumption')
           for issue in native.issues):
        return None
    playback_ids = set()
    for segment in native.segments:
        if segment.rate_den <= 0 or segment.end_vgmticks < segment.start_vgmticks:
            raise ValueError('Malformed native OPNA PCM rate or timing')
        if segment.sample_id is not None and segment.sample_id not in sources:
            raise ValueError('Native OPNA PCM Segment references an absent sample')
        if (segment.issues or segment.repeat or segment.continuation_index
                or not segment.independently_playable or segment.sample_id is None
                or segment.rate_num <= 0 or segment.playback_id in playback_ids):
            return None
        if loop_start is not None and segment.start_vgmticks < loop_start < segment.end_vgmticks:
            return None
        playback_ids.add(segment.playback_id)
    samples, playbacks, assets, events, evidence = [], [], [], [], []
    converted, payload_ids = {}, {}
    total = 0
    for segment in native.segments:
        if segment.end_vgmticks == segment.start_vgmticks:
            continue
        volume = project_pcm8_volume(segment.level, source_scale=256)
        if volume.silent or segment.pan == 0:
            continue
        source = sources[segment.sample_id]
        rate = Fraction(segment.rate_num, segment.rate_den)
        key = (source.encoded_bytes, rate, profile.name)
        if key not in converted:
            allowed = range(len(RATES)) if profile.name == 'standard' else [
                i for i, value in enumerate(RATES) if value <= profile.rate]
            index = min(allowed, key=lambda i: abs(RATES[i] - rate))
            target_rate = RATES[index]
            count_value = Fraction(len(source.encoded_bytes) * 2) * target_rate / rate
            count = -(-count_value.numerator // count_value.denominator)
            if (len(source.encoded_bytes) * 2 > MAX_DECODED_SAMPLES
                    or count > maximum * 2 or total + count > MAX_TOTAL_SAMPLES):
                return None
            decoded = decode_adpcm_b(source.encoded_bytes)
            pcm = []
            for position_index in range(count):
                position = Fraction(position_index) * rate / target_rate
                lo = min(position.numerator // position.denominator, len(decoded) - 1)
                hi = min(lo + 1, len(decoded) - 1)
                fraction = position - lo
                pcm.append(round(decoded[lo] * (1 - fraction) + decoded[hi] * fraction))
            encoded, error = encode_msm6258(pcm)
            if not encoded or len(encoded) > maximum:
                return None
            if encoded not in payload_ids:
                sample_id = len(samples)
                payload_ids[encoded] = sample_id
                samples.append(PcmSample(sample_id, 'msm6258-adpcm4-low-first', encoded,
                                         hashlib.sha256(encoded).hexdigest()))
            sample_id = payload_ids[encoded]
            total += count
            clock = 4000000 if index < 2 else 8000000
            divider = (1024, 768, 1024, 768, 512)[index]
            converted[key] = sample_id, target_rate, clock, divider
            assets.append(dict(sample_id=sample_id, native_sample_id=source.sample_id,
                source_sha256=source.sha256, source_rate_num=rate.numerator,
                source_rate_den=rate.denominator, target_rate_num=target_rate.numerator,
                target_rate_den=target_rate.denominator, pcm_profile=pcm_profile,
                source_reset='nominal ADPCM-B predictor=0 step=127',
                target_reset='independent PDX predictor=-2 index=0 assumption',
                full_sample_count=count, padding_nibbles=count % 2,
                encoded_bytes=len(encoded), squared_error_sum=error, level_baked=False))
        sample_id, target_rate, clock, divider = converted[key]
        ids = segment.source_event_ids
        playbacks.append(BankPlayback(segment.playback_id, 0, sample_id,
            segment.start_vgmticks, segment.end_vgmticks,
            ids[0] if ids else -1, ids[-1] if ids else -1,
            0, 0, 0, clock, divider, target_rate.numerator, target_rate.denominator,
            segment.pan ^ 3, False, True, 'projected_independent_pdx_decoder_assumption',
            'source_end' if segment.termination == 'source_eof_without_reset' else segment.termination,
            True, True, len(samples[sample_id].encoded_bytes) * 2, None, (), (),
            target_volume=volume.raw_volume))
        events.append(dict(playback_id=segment.playback_id, native_segment_id=segment.segment_id,
            native_playback_id=segment.playback_id, native_sample_id=segment.sample_id,
            pdx_sample_id=sample_id, target_sample_id=sample_id,
            start_vgmticks=segment.start_vgmticks, end_vgmticks=segment.end_vgmticks,
            source_level=segment.level, target_volume=volume.raw_volume,
            effective_gain=volume.effective_gain, gain_error=volume.gain_error,
            source_pan=segment.pan, target_pan=segment.pan ^ 3,
            source_event_ids=ids, original_source_event_ids=segment.original_source_event_ids,
            eligible=True))
        for code, detail in (
                ('adpcm_b_nominal_decode', 'Nominal decoder omits Yamaha prefetch and DAC interpolation'),
                ('msm6258_requantization', 'Complete source waveform is independently re-encoded for PDX'),
                ('pcm_linear_resampling', 'Linear resampling without antialias filtering'),
                ('pcm8_onset_gain_quantization', 'Level/256 is quantized once at playback, never baked'),
                ('pcm_encoded_duration_rounding', 'Complete source duration is rounded to a target sample and full ADPCM byte; original gate is retained'),
                ('independent_pdx_decoder_assumption', 'Target reset behavior is assumed, not native supply evidence')):
            evidence.append(dict(criterion='transcoding', status='lossy', code=code,
                detail=detail, cause='target_projection', playback_id=segment.playback_id,
                start_vgmticks=segment.start_vgmticks, end_vgmticks=segment.end_vgmticks))
        for observation in segment.observations:
            evidence.append(dict(criterion='source_interpretation', status='unverified',
                code=observation, detail='Retained native memory-image assumption',
                cause='source_assumption', playback_id=segment.playback_id))
    return ProjectedBankAnalysis(source_end_vgmticks=native.source_end_vgmticks,
        samples=tuple(samples), playbacks=tuple(playbacks), controls=(), issues=(),
        transfers=TransferLog(b''), raw_commands=(), source_raw=source_raw,
        clock_hz=4000000, options=4,
        initialization='derived finite PCM8 bank; no native MSM6258 supply/reset claimed',
        source_loop_vgmticks=loop_start, blocks=(), loop_count=native.loop_count,
        pcm_profile=pcm_profile, target_evidence=tuple(evidence),
        target_mapping=tuple(events), bank_assets=tuple(assets), bank_events=tuple(events))
