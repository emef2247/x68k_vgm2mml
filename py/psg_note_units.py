"""Source-sample PSG/SSG note and volume-run view shared with MSX extraction.

This adapter does not change native Segments, quantize time or import MGSDRV
syntax. Note attacks are inferred, not observed hardware Key operations.
"""
import csv
from dataclasses import replace
import json
from pathlib import Path

from mml_envelopes import Note


def interval_end(rows,index,end=None):
    stop=rows[index].vgmticks_end
    return max(stop,end) if end is not None and index==len(rows)-1 else stop


def analyze(segments,*,end=None):
    def event_type(segment):
        register=getattr(segment,'register',None)
        if register is not None and register<6:
            return 'fCA' if register%2==0 else 'fCB'
        if register==13:return 'evS'
        return ({6:'wNC',7:'mode',8:'aVC',9:'aVC',10:'aVC',
                 11:'ePL',12:'evM'}.get(register,segment.ev_type))
    view={}
    for ch,rows in segments.items():
        values=[]
        for index,s in enumerate(rows):
            if s.vgmticks is None or s.vgmticks_end is None or s.vgmticks_end<s.vgmticks:
                raise ValueError('PSG musical interpretation requires exact source sample boundaries')
            # Source audibility is independent of a legacy rendered rest spelling.
            scale=s.scale if s.scale!='r' else '' if s.mode and (s.volume or s.envelope_enabled) else 'r'
            stop=interval_end(rows,index,end)
            values.append(replace(s,ticks=s.vgmticks,l=stop-s.vgmticks,
                                  scale=scale,ev_type=event_type(s)))
        view[ch]=tuple(values)
    from psg_scc_performance import analyze as analyze_performance
    from psg_scc_volume_curves import project
    return project(analyze_performance(view,'psg',tick_clock_hz=44100))


def interpret(segments,*,end=None):
    return analyze(segments,end=end).performance.to_notes(Note)


def membership(notes):
    return {(ch,row):(index,note.start,note.start+note.length,note.rest)
            for ch,items in notes.items() for index,note in enumerate(items)
            for row in note.segment_indices}


def dump(notes,segments,path):
    from psg_scc_performance import dump as dump_performance
    from psg_scc_volume_curves import dump as dump_curves
    end=max((n.start+n.length for items in notes.values() for n in items),default=None)
    projection=analyze(segments,end=end)
    prefix=str(Path(path).with_suffix(''))
    dump_performance(projection.original,prefix)
    dump_curves(projection,prefix+'.volume_curves',details=True)
    fields=('source_ch','note_id','source_start','source_end','rest','tone_period',
            'mode','envelope_enabled','source_rows','source_event_ids','volume_runs','key_origin')
    with Path(path).open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for ch,items in notes.items():
            for index,note in enumerate(items):
                members=[segments[ch][i] for i in note.segment_indices]
                writer.writerow(dict(source_ch=ch,note_id=index,source_start=note.start,
                    source_end=note.start+note.length,rest=note.rest,tone_period=note.segment.tone_period,
                    mode=note.segment.mode,envelope_enabled=note.segment.envelope_enabled,
                    source_rows=json.dumps(note.segment_indices),source_event_ids=json.dumps(list(dict.fromkeys(
                        getattr(s,'source_event_id',None) for s in members if getattr(s,'source_event_id',None) is not None))),
                    volume_runs=json.dumps(note.runs),key_origin='source_musical_interpretation_inferred'))
