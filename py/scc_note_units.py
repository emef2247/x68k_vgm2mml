"""MSX SCC notes/software-volume runs on an immutable source-sample view."""
import csv
from dataclasses import replace
import json
from pathlib import Path

from mml_envelopes import Note,settings
from musical_structure import source_plan
from psg_note_units import interval_end


def analyze(segments,*,end=None):
    view={}
    for ch,rows in segments.items():
        values=[]
        for index,s in enumerate(rows):
            if s.vgmticks is None or s.vgmticks_end is None or s.vgmticks_end<s.vgmticks:
                raise ValueError('SCC musical interpretation requires exact source sample boundaries')
            stop=interval_end(rows,index,end)
            audible=bool(s.enabled and s.volume and s.tone_period>8)
            scale=(s.scale if s.scale!='r' else '') if audible else 'r'
            values.append(replace(s,ticks=s.vgmticks,l=stop-s.vgmticks,scale=scale))
        view[ch]=tuple(values)
    from psg_scc_performance import analyze as analyze_performance
    from psg_scc_volume_curves import project
    return project(analyze_performance(view,'scc',tick_clock_hz=44100))


def interpret(segments,*,end=None):
    return analyze(segments,end=end).performance.to_notes(Note)


def dump(notes,segments,path):
    from psg_scc_performance import dump as dump_performance
    from psg_scc_volume_curves import dump as dump_curves
    end=max((n.start+n.length for items in notes.values() for n in items),default=None)
    projection=analyze(segments,end=end)
    prefix=str(Path(path).with_suffix(''))
    dump_performance(projection.original,prefix)
    dump_curves(projection,prefix+'.volume_curves',details=True)
    path=Path(path)
    fields=('source_ch','note_id','source_start','source_end','rest','tone_period',
            'waveform_id','waveform_hex','source_rows','volume_runs','key_origin')
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for ch,items in notes.items():
            for index,note in enumerate(items):
                writer.writerow(dict(source_ch=ch,note_id=index,source_start=note.start,
                    source_end=note.start+note.length,rest=note.rest,tone_period=note.segment.tone_period,
                    waveform_id=note.segment.waveform_id,waveform_hex=note.segment.waveform_hex,
                    source_rows=json.dumps(note.segment_indices),volume_runs=json.dumps(note.runs),
                    key_origin='source_musical_interpretation_inferred; no native SCC Key-On'))
            keys=tuple((n.length,n.rest,() if n.rest else settings(n.segment,'scc'),tuple(n.runs)) for n in items)
            # Same exact source-note solver as MSX/MUC/MDX; no target envelope IDs.
            plan=source_plan(keys)
            plan.dump(path.with_name(path.stem+f'.ch{ch}.structure.csv'),
                      [n.segment_indices for n in items])
