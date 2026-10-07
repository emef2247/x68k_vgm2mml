"""Convert native OPM VGM through inspectable Segments to MDX MML controls."""
import json
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from opm import build_segments, dump_analysis
from opm_mdx import project_segments, render, dump_projection
from vgm_reader import parse_vgm


def convert(source, outdir, *, dump_passes=False, track_layout='channels', notation='structured', loops=True, title=None, gd3_language='ja', normalize_lengths=False):
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if normalize_lengths and notation != 'structured':
        raise ValueError('Native MDX length normalization requires structured notation')
    for suffix in ('.mdx.normalization.json', '.mdx.normalization.csv', '.mdx.before.normalize.mml'):
        (outdir / (source.stem + suffix)).unlink(missing_ok=True)
    metadata = {}
    source_loop = {}
    with TemporaryDirectory(prefix='opm-mdx-') as temporary:
        analysis_dir = outdir if dump_passes else Path(temporary)
        parse_vgm(str(source), str(analysis_dir), opm_metadata=metadata,
                  loop_metadata=source_loop, dump_loop=dump_passes)
        if not metadata['csv_path']:
            raise ValueError('Input declares no supported OPM stream')
        analysis = build_segments(metadata['csv_path'], end_vgmticks=metadata['source_end_vgmticks'])
        if dump_passes:
            dump_analysis(analysis, state_csv=outdir/(source.stem+'_trace.opm.csv'),
                          segments_csv=outdir/(source.stem+'.opm.segments.csv'))
    clock = None
    if notation == 'structured':
        from opm_mdx_music import infer_clock
        clock = infer_clock(analysis.segments, analysis.source_end_vgmticks)
    projection = project_segments(analysis.segments, end_vgmticks=analysis.source_end_vgmticks,
                                  sample_multiplier=clock['chosen']['multiplier'] if clock else 1)
    before = projection
    normalization = None
    if normalize_lengths:
        from opm_note_normalization import normalize_projection
        projection, normalization, evidence = normalize_projection(analysis.segments, before,
                                                                   loop_metadata=source_loop)
        (outdir / (source.stem + '.mdx.normalization.json')).write_text(json.dumps(normalization, indent=2) + '\n', encoding='utf-8')
        if dump_passes and evidence:
            with (outdir / (source.stem + '.mdx.normalization.csv')).open('w', newline='', encoding='utf-8') as stream:
                fields = list(dict.fromkeys(k for row in evidence for k in row))
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for row in evidence:
                    writer.writerow({k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()})
    from gd3 import read_gd3
    gd3 = read_gd3(source)
    title_source = 'explicit' if title is not None else 'gd3' if gd3 and (gd3[1].strip() or gd3[0].strip()) else 'filename'
    order = (0, 1) if gd3_language == 'en' else (1, 0)
    title = title if title is not None else ((gd3[order[0]].strip() or gd3[order[1]].strip()) if gd3 else source.stem)
    mml = outdir / (source.stem + '.mdx.mml')
    structure = None
    if notation in ('structured', 'legacy'):
        if track_layout != 'channels':
            raise ValueError('Structured notation requires channel tracks; use --notation registers for conductor replay')
        if notation == 'structured':
            from opm_mdx_music import build_music as build_structure
        else:
            from opm_mdx_structure import build_structure
        structure = build_structure(projection, analysis.segments, title=title or source.stem, loops=loops)
        text = structure.text
        if dump_passes and normalization and normalization['status'] == 'applied':
            baseline = build_structure(before, analysis.segments, title=title or source.stem, loops=loops)
            (outdir / (source.stem + '.mdx.before.normalize.mml')).write_text(baseline.text, encoding='utf-8')
            normalization.update(before_structure=baseline.summary(), after_structure=structure.summary())
            (outdir / (source.stem + '.mdx.normalization.json')).write_text(json.dumps(normalization, indent=2) + '\n', encoding='utf-8')
    elif notation == 'registers':
        text = render(projection, title=title if title is not None else source.stem, track_layout=track_layout)
    else:
        raise ValueError('Unknown MDX notation')
    mml.write_text(text, encoding='utf-8', newline='\n')
    if dump_passes:
        dump_projection(projection, outdir / (source.stem + '.mdx.controls.csv'), track_layout=track_layout)
        report = projection.timing_report()
        report['track_layout'] = track_layout
        report['notation'] = notation
        report['title_source'] = title_source
        if clock is not None:
            report['score_clock_inference'] = clock
            report['score_clock_inference_scope'] = 'before optional length normalization'
        if normalization is not None:
            report['length_normalization'] = normalization
        if structure is not None:
            structure.dump(outdir / (source.stem + '.mdx.structure'),
                           segments_csv=outdir / (source.stem + '.opm.segments.csv'))
            report.update(structure.summary())
        report['source_state_writes'] = len({e.source_event_id for e in analysis.events})
        report['source_nonchanging_writes_not_in_segments'] = report['source_state_writes'] - len(projection.writes)
        (outdir / (source.stem + '.mdx.timing.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return mml, analysis, projection

