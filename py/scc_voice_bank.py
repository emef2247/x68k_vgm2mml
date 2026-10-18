"""Validated target-only SCC voice candidates and whole-song optional lanes."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

MODELS=('additive','additive8','fm-additive','fm-fm')
CARRIERS=((3,),(3,),(3,),(3,),(2,3),(1,2,3),(1,2,3),(0,1,2,3))


@dataclass(frozen=True)
class FittedVoice:
    identity: str
    model: str
    algorithm: int
    feedback: int
    operator_muls: tuple
    operator_tl: tuple
    carriers: tuple
    reference_gain: float


def levels(voice,gain,volume):
    if not volume:return tuple(127 if i in voice.carriers else tl for i,tl in enumerate(voice.operator_tl))
    delta=-20*math.log10(gain/voice.reference_gain*volume/15)/.75
    return tuple(max(0,min(127,int(math.floor(tl+delta+.5)))) if i in voice.carriers else tl
                 for i,tl in enumerate(voice.operator_tl))


def load(path,*,clock):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('schema')!='scc-fm-fit-v1' or data.get('target_chip')!='YM2151' or data.get('target_clock_hz')!=clock:
        raise ValueError('SCC voice bank must be scc-fm-fit-v1 for YM2151 at the target clock')
    gain=data.get('reference_gain')
    if type(gain) not in (int,float) or not math.isfinite(gain) or not 0<gain<=1:
        raise ValueError('SCC voice bank has invalid reference gain')
    frequency=data.get('reference_frequency_hz')
    if not isinstance(data.get('emulator'),dict) or not data['emulator'] or type(frequency) not in (int,float) or not math.isfinite(frequency) or not 0<frequency<clock/128:
        raise ValueError('SCC voice bank requires emulator provenance and a valid reference pitch')
    metadata=data['emulator']
    if not isinstance(data.get('search_version'),str) or not data['search_version'].strip():
        raise ValueError('SCC voice bank requires a search version')
    hashes=metadata.get('source_sha256')
    required=('ym2151.c','ym2151.h','mamedef.h','scc_opm_probe.c')
    if (not isinstance(metadata.get('core'),str) or not metadata['core'].strip()
            or not isinstance(hashes,dict) or any(not isinstance(hashes.get(name),str)
                or len(hashes[name])!=64 or any(c not in '0123456789abcdef' for c in hashes[name]) for name in required)):
        raise ValueError('SCC voice bank requires core/wrapper SHA-256 provenance')
    if any(type(metadata.get(key))!=int or metadata[key]<=0 for key in
           ('sample_rate_hz','warmup_frames','measured_frames')):
        raise ValueError('SCC voice bank requires positive probe rate and frame counts')
    calibration=metadata.get('carrier_tl0_peak_units')
    if type(calibration) not in (int,float) or not math.isfinite(calibration) or calibration<=0:
        raise ValueError('SCC voice bank requires positive carrier calibration')
    if not isinstance(data.get('waveforms'),dict):
        raise ValueError('SCC voice bank requires a waveform mapping')
    for identity,wave in data['waveforms'].items():
        if not isinstance(wave,dict) or not isinstance(wave.get('waveform_hex'),str):
            raise ValueError('SCC voice bank requires waveform hex bytes')
        raw=bytes.fromhex(wave['waveform_hex'])
        if len(raw)!=32 or hashlib.sha256(raw).hexdigest()!=identity or wave.get('waveform_sha256')!=identity:
            raise ValueError('SCC voice bank waveform content/hash mismatch')
        if not isinstance(wave.get('candidates'),dict):
            raise ValueError('SCC voice bank requires candidate mappings')
        for candidate in wave['candidates'].values():
            if not isinstance(candidate,dict):raise ValueError('Invalid SCC fitted candidate')
            score=candidate.get('spectral_error')
            if type(score) not in (int,float) or not math.isfinite(score) or score<0:
                raise ValueError('SCC voice bank requires a finite nonnegative spectral score')
            if not isinstance(candidate.get('parts'),list) or not 1<=len(candidate['parts'])<=2:
                raise ValueError('SCC fitted candidate must use one or two channels')
            for part in candidate['parts']:
                if not isinstance(part,dict):raise ValueError('Invalid SCC fitted part')
                alg,feedback=part.get('algorithm'),part.get('feedback')
                if type(alg)!=int or not 0<=alg<=7 or type(feedback)!=int or not 0<=feedback<=7:
                    raise ValueError('SCC fitted algorithm/feedback outside 0..7')
                for key,limit in (('operator_muls',15),('operator_tl',127)):
                    if not isinstance(part.get(key),list) or len(part[key])!=4 or any(type(v)!=int or not 0<=v<=limit for v in part[key]):
                        raise ValueError('SCC fitted '+key+' must contain four valid integer values')
                if not isinstance(part.get('carriers'),list) or tuple(part['carriers'])!=CARRIERS[alg]:
                    raise ValueError('SCC fitted carrier mask does not match algorithm')
    return data


def prepare(segments,psg,psg_map,*,end,model,bank_path,clock,voice,interval_end):
    if model not in MODELS:raise ValueError('SCC model must be '+', '.join(MODELS))
    if bank_path is not None and model in ('additive','additive8'):
        raise ValueError('--scc-voice-bank requires an FM SCC model')
    bank=load(bank_path,clock=clock) if bank_path is not None else None
    if model.startswith('fm-') and bank is None and any(s.enabled and s.volume and s.tone_period>8 for rows in segments.values() for s in rows):raise ValueError('FM SCC models require --scc-voice-bank from scripts/fit_scc_fm.py')
    used={ch for ch,rows in segments.items() if any(s.enabled and s.volume and s.tone_period>8 for s in rows)}
    # Reserve every SCC lane that can emit held initialization, even a DC-only period.
    reserved={ch for ch,rows in segments.items() if any(s.enabled and s.volume for s in rows)}|{psg_map[ch] for ch,rows in psg.items() if any(s.mode and (s.volume or s.envelope_enabled) for s in rows)}
    available=[ch for ch in range(8) if ch not in reserved]
    profiles={};benefits={ch:0. for ch in used};decisions=[];wave_decisions=[]
    for ch in sorted(used):
        for index,s in enumerate(segments[ch]):
            if not s.enabled or not s.volume or s.tone_period<=8:continue
            raw=bytes.fromhex(s.waveform_hex);identity=hashlib.sha256(raw).hexdigest()
            key=s.waveform_hex
            baseline=voice(key)
            if key not in profiles:
                parts=(baseline,);improvement=0.;reason='one-channel additive baseline'
                if model=='additive8':
                    extra=voice(key,offset=4)
                    improvement=max(0.,sum(a*a for a in extra.amplitudes)/2)
                    if improvement>1e-8:parts=(baseline,extra)
                    reason='additional selected harmonic energy'
                elif bank is not None:
                    entry=bank['waveforms'].get(identity)
                    if entry is None or model not in entry['candidates'] or 'additive' not in entry['candidates']:
                        raise ValueError('SCC voice bank lacks selected model for waveform '+identity)
                    candidate=entry['candidates'][model]
                    improvement=max(0.,entry['candidates']['additive']['spectral_error']-candidate['spectral_error'])
                    audible_parts=[(i,part) for i,part in enumerate(candidate['parts'])
                                   if any(part['operator_tl'][op]<127 for op in part['carriers'])]
                    if not audible_parts:improvement=0.
                    if improvement>1e-8:
                        parts=tuple(FittedVoice('scc_fit_'+identity[:16]+'_'+model+'_'+str(i),
                            part.get('model','fm'),part['algorithm'],part['feedback'],tuple(part['operator_muls']),
                            tuple(part['operator_tl']),tuple(part['carriers']),bank['reference_gain'])
                            for i,part in audible_parts)
                    reason=('measured reference-pitch spectral error improvement' if improvement>1e-8 else
                            'candidate has no audible carrier' if not audible_parts else 'candidate did not improve reference additive score')
                profiles[key]=(parts,improvement,reason)
                wave_decisions.append(dict(waveform_sha256=identity,selected_models=[p.model if isinstance(p,FittedVoice) else 'additive' for p in parts],
                    channels=len(parts),improvement=improvement,reason=reason,
                    baseline_spectral_error=entry['candidates']['additive']['spectral_error'] if bank else None,
                    candidate_spectral_error=candidate['spectral_error'] if bank else None))
            parts,improvement,_=profiles[key]
            if len(parts)>1:
                duration=max(0,interval_end(segments[ch],index,end)-s.vgmticks)
                benefits[ch]+=duration*(s.volume/15)**2*improvement
    extra_map={ch:target for ch,target in zip(sorted((ch for ch,b in benefits.items() if b>0),key=lambda ch:(-benefits[ch],ch)),available)}
    for ch in sorted(used):
        decisions.append(dict(source_ch=ch,primary_target_ch=ch,extra_target_ch=extra_map.get(ch),
            weighted_benefit=benefits[ch],action='additional_lane' if ch in extra_map else
            'quality_fallback_one_lane' if benefits[ch]>0 else 'one_lane_sufficient',
            source_channel_omitted=False))
    report=dict(requested_model=model,primary_channels=sorted(used),reserved_target_channels=sorted(reserved),
        extra_channel_map=extra_map,allocation=decisions,waveform_decisions=wave_decisions,
        allocation_policy='whole rendered traversal; duration and source-volume-squared weighted improvement',
        phase_matching=False,source_ir_unchanged=True,
        reference_pitch_hz=bank['reference_frequency_hz'] if bank else None,
        bank_sha256=hashlib.sha256(Path(bank_path).read_bytes()).hexdigest() if bank else None,
        bank_emulator=bank['emulator'] if bank else None,
        bank_search_version=bank['search_version'] if bank else None,
        bank_reference_gain=bank['reference_gain'] if bank else None,
        quality_scope='selection uses bank reference-pitch score; bank pitch checks cover only their listed pitches' if bank else
                      'DFT retained energy only; no acoustic score')
    def select(wave_hex,lane,ch):
        base=voice(wave_hex)
        parts=profiles.get(wave_hex,((base,),0.,''))[0]
        if len(parts)>1 and ch not in extra_map:parts=(base,)
        return parts[lane] if lane<len(parts) else None
    return select,extra_map,report
