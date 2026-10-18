"""Explicit continuous PSG waveform -> filtered mono MDX PCM target view."""
from array import array
from dataclasses import replace
import math

from pcm_waveform_mdx import project as package_waveform
from pcm_profiles import get_profile


def project(native,*,source_raw,loop_start=None,loop_count=1,pcm_profile='standard',gain=1.):
    if not math.isfinite(gain) or not 0<gain<=1:
        raise ValueError('PSG PCM gain must be finite and in (0,1]')
    try:
        import numpy as np
    except ImportError as exc:
        raise ValueError('PSG PCM target filtering requires NumPy') from exc
    profile=get_profile(pcm_profile)
    # AC coupling is a target approximation; keep the positive native DAC waveform.
    source=np.asarray(native.samples,dtype=np.float64).reshape(-1,2).mean(axis=1)
    ac=np.empty(len(source));coefficient=math.exp(-2*math.pi*20/44100)
    previous=state=0.
    for i,value in enumerate(source):
        state=value-previous+coefficient*state;previous=value;ac[i]=state
    cutoff=.45*float(profile.rate)/44100
    taps=np.arange(63)-31
    kernel=2*cutoff*np.sinc(2*cutoff*taps)*np.hamming(63)
    kernel/=kernel.sum()
    filtered=np.convolve(np.pad(ac,(31,31)),kernel,mode='valid') if len(ac) else ac
    values=np.rint(filtered*gain)
    clipped=int(np.count_nonzero((values<-32768)|(values>32767)))
    mono=np.clip(values,-32768,32767).astype(np.int32)
    stereo=np.repeat(mono,2)
    view=replace(native,samples=array('i',stereo))
    evidence=[dict(criterion='source_interpretation',status='unverified',code='psg_external_runtime',
        detail='Continuous external emu2149 AY8910 runtime; shared noise/envelope and tone phase retained',
        cause='source_assumption',source_value=native.metadata),
        dict(criterion='transcoding',status='lossy',code='psg_target_filter',cause='target_projection',
        detail='20Hz first-order high-pass then centered63tap Hamming-sinc low-pass before profile resampling',
        projected_value=dict(gain=gain,lowpass_cutoff_hz=.45*float(profile.rate),taps=63,
            filter_edges='zero padding; no added timestamp delay; FIR pre-ringing possible',clipped_samples=clipped),
        fallback='explicit_filtered_mono_transcoding')]
    return package_waveform(view,source_raw=source_raw,loop_start=loop_start,loop_count=loop_count,
        source_origin='projected_msm6258_from_psg',evidence_prefix='psg',artifact_prefix='psg_pcm',
        source_description='Continuous AY8910 three-channel mix',source_evidence=evidence,pcm_profile=pcm_profile)
