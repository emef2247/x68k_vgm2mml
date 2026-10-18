"""Automatic offline SCC fitting at the explicit target boundary."""
import json
from pathlib import Path
import shutil


def generate(analysis,outdir,stem,*,artifact_outdir=None,scc_gain=.125):
    waves=list(dict.fromkeys(bytes.fromhex(s.waveform_hex)
        for rows in analysis.segments.values() for s in rows
        if s.enabled and s.volume and s.tone_period>8))
    if not waves:return None,dict(status='not_needed',reason='no sounding SCC waveforms')
    out=Path(artifact_outdir or outdir);out.mkdir(parents=True,exist_ok=True)
    csv_path=Path(outdir)/(stem+'.scc.waveforms.csv')
    destination=out/csv_path.name
    if csv_path.resolve()!=destination.resolve():shutil.copyfile(csv_path,destination)
    from scc_fm_fit import OpmProbe,fit_bank
    try:
        probe=OpmProbe()
        print('SCC voice bank: automatic fitting/cache lookup for '+str(len(waves))+' waveform(s)',flush=True)
        bank=fit_bank(waves,probe,gain=scc_gain,cache_dir=probe.root/'.tools/scc-fm-fit/cache')
    except RuntimeError as exc:
        raise ValueError('Automatic SCC voice fitting: '+str(exc)+
            '; supply --scc-voice-bank or select --scc-model additive/additive8') from exc
    path=out/(stem+'.scc.voice_bank.json')
    path.write_text(json.dumps(bank,indent=2)+'\n',encoding='utf-8')
    return path,dict(status='generated_or_cached',waveforms=len(waves),
        waveform_csv=destination.name,voice_bank=path.name,reference_gain=scc_gain,
        cache='.tools/scc-fm-fit/cache',source_segments_unchanged=True)
