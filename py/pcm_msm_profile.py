"""Explicit native MSM6258 -> smaller derived PDX samples, retaining source IR."""
import csv
from dataclasses import dataclass,replace
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from msm6258 import PcmAnalysis,PcmSample
from opna_adpcm import _msm_next,encode_msm6258
from pcm_profiles import get_profile


@dataclass(frozen=True)
class ProfiledMsmAnalysis(PcmAnalysis):
    target_evidence: tuple = ()
    target_mapping: tuple = ()
    source_origin: str = 'projected_msm6258_low_profile'
    source_payload_bytes: int = 0
    pcm_profile: str = 'low'

    def dump(self,outdir,stem):
        # Never replace the native PCM State/Segment/sample dumps.
        super().dump(outdir,stem+'.pcm_'+self.pcm_profile)
        root=Path(outdir)
        (root/(stem+'.pcm_profile.json')).write_text(json.dumps(dict(
            pcm_profile=self.pcm_profile,source_ir_unchanged=True,
            reencoded_playback_count=sum((r['source_rate_num'],r['source_rate_den'])!=
                (r['target_rate_num'],r['target_rate_den']) for r in self.target_mapping),
            source_payload_bytes=self.source_payload_bytes,
            target_payload_bytes=sum(len(s.encoded_bytes) for s in self.samples),
            target_distinct_samples=len(self.samples),mapping=self.target_mapping,
            losses=self.target_evidence),indent=2)+'\n')
        fields=tuple(self.target_mapping[0]) if self.target_mapping else ('playback_id',)
        with (root/(stem+'.pcm_profile.mapping.csv')).open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n')
            writer.writeheader();writer.writerows(self.target_mapping)


def project(native,*,pcm_profile='standard'):
    profile=get_profile(pcm_profile)
    if profile.name=='standard':return native
    if isinstance(native,ProfiledMsmAnalysis):
        if native.pcm_profile!=profile.name:
            raise ValueError('PCM profile conversion requires native source IR, not another profile')
        return native
    # Preserve all ordinary source blockers; target quality cannot resolve them.
    if native.issues or native.options&8:return native
    from pcm_mdx import RATES
    by_id={s.sample_id:s for s in native.samples}
    samples=[];playbacks=[];mapping=[];identities={};cache={}
    def bind(sample):
        key=(sample.codec,sample.encoded_bytes)
        if key not in identities:
            identities[key]=len(samples)
            samples.append(replace(sample,sample_id=len(samples)))
        return identities[key]
    for p in native.playbacks:
        sample=by_id.get(p.sample_id)
        schedule_fallback=(set(p.issues)=={'irregular_byte_supply'} and p.decoder_reset_known
            and p.pan is not None and p.stream_transfer_end-p.stream_transfer_start==p.supplied_bytes
            and p.supplied_bytes>0)
        eligible=(sample is not None and bool(sample.encoded_bytes) and sample.codec=='msm6258-adpcm4-low-first'
                  and (p.independently_playable or schedule_fallback) and p.rate_hz>0)
        if not eligible:
            playbacks.append(replace(p,sample_id=bind(sample) if sample is not None else None));continue
        target=min((r for r in RATES if r<=profile.rate),key=lambda r:abs(r-p.rate_hz))
        if target==p.rate_hz:
            sid=bind(sample);playbacks.append(replace(p,sample_id=sid))
            mapping.append(dict(playback_id=p.playback_id,source_sample_id=p.sample_id,target_sample_id=sid,
                source_rate_num=p.rate_num,source_rate_den=p.rate_den,target_rate_num=p.rate_num,target_rate_den=p.rate_den,
                source_encoded_bytes=len(sample.encoded_bytes),target_encoded_bytes=len(sample.encoded_bytes),
                source_start_vgmticks=p.start_vgmticks,source_end_vgmticks=p.end_vgmticks,
                mdx_frequency=RATES.index(target),squared_error_sum=0,encoded_duration_error_vgmticks=0))
            continue
        key=(sample.sample_id,p.rate_hz,target)
        if key not in cache:
            if len(sample.encoded_bytes)*2>16000000:
                raise ValueError('MSM6258 size profile exceeds bounded nominal decode scope')
            signal,index=-2,0;decoded=[]
            for byte in sample.encoded_bytes:
                for nibble in (byte&15,byte>>4):
                    signal,index=_msm_next(signal,index,nibble);decoded.append(signal*64)
            count=max(2,2*round(Fraction(len(decoded))*target/p.rate_hz/2))
            step=float(p.rate_hz/target)
            def values():
                for i in range(count):
                    position=min(len(decoded)-1,i*step);lo=int(position);weight=position-lo
                    yield round(decoded[lo]*(1-weight)+decoded[min(lo+1,len(decoded)-1)]*weight)
            encoded,error=encode_msm6258(values())
            cache[key]=(encoded,count,error)
        encoded,count,error=cache[key]
        sid=bind(PcmSample(-1,'msm6258-adpcm4-low-first',encoded,hashlib.sha256(encoded).hexdigest()))
        frequency=RATES.index(target);clock=4000000 if frequency<2 else 8000000
        divider=(1024,768,1024,768,512)[frequency]
        playbacks.append(replace(p,sample_id=sid,rate_num=target.numerator,rate_den=target.denominator,
            clock_hz=clock,divider=divider,nominal_nibbles=count,consumed_nibbles=None))
        mapping.append(dict(playback_id=p.playback_id,source_sample_id=p.sample_id,target_sample_id=sid,
            source_rate_num=p.rate_num,source_rate_den=p.rate_den,
            target_rate_num=target.numerator,target_rate_den=target.denominator,
            source_encoded_bytes=len(sample.encoded_bytes),target_encoded_bytes=len(encoded),
            source_start_vgmticks=p.start_vgmticks,source_end_vgmticks=p.end_vgmticks,
            mdx_frequency=frequency,squared_error_sum=error,
            encoded_duration_error_vgmticks=float(Fraction(count*44100)/target-
                Fraction(len(sample.encoded_bytes)*2*44100)/p.rate_hz)))
    loss=dict(criterion='transcoding',status='lossy',code='msm6258_'+profile.name+'_profile_reencoding',
        detail='Nominal reset decoder; linear resampling without antialias filter and 10-bit ADPCM requantization; source IR retained',
        cause='target_projection',fallback='explicit_pcm_profile_'+profile.name,source_value='native MSM6258 bytes',
        projected_value=f'PDX rate capped at {float(profile.rate)}Hz; nearest even encoded count')
    evidence=tuple(dict(loss,playback_id=r['playback_id'],start_vgmticks=r['source_start_vgmticks'],
        end_vgmticks=r['source_end_vgmticks'],
        source_value=dict(rate_num=r['source_rate_num'],rate_den=r['source_rate_den'],encoded_bytes=r['source_encoded_bytes']),
        projected_value=dict(rate_num=r['target_rate_num'],rate_den=r['target_rate_den'],encoded_bytes=r['target_encoded_bytes']))
        for r in mapping if (r['source_rate_num'],r['source_rate_den'])!=(r['target_rate_num'],r['target_rate_den']))
    return ProfiledMsmAnalysis(**dict(native.__dict__,samples=tuple(samples),playbacks=tuple(playbacks)),
        target_mapping=tuple(mapping),target_evidence=evidence,
        source_payload_bytes=sum(len(s.encoded_bytes) for s in native.samples),
        pcm_profile=profile.name,source_origin='projected_msm6258_'+profile.name+'_profile')
