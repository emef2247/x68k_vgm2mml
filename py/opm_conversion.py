"""Convert native OPM VGM through inspectable Segments to MDX MML controls."""
import json
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from opm import OpmAnalysis, build_segments, dump_analysis
from opm_mdx import MdxProjection, mdx_tick, projected_samples, project_segments, render, dump_projection
from vgm_reader import parse_vgm


def _record_pcm_assessment(assessment, outdir, stem, *, requires_pdx):
    for name, suffix in (('mml', '.mdx.mml'), ('mdx', '.mdx'), ('pdx', '.pdx')):
        path = outdir / (stem + suffix)
        required = name == 'mml' or (name in ('pdx', 'mdx') and requires_pdx)
        status = ('generated' if path.is_file() and path.stat().st_size else
                  'blocked' if required and assessment.artifact_status == 'blocked' else
                  'not_generated' if required else 'not_requested')
        assessment.artifacts[name] = dict(path=str(path), status=status, required=required)
    assessment.dump(outdir, stem)


def convert(source, outdir, *, dump_passes=False, track_layout='channels', notation='structured', loops=True, title=None, gd3_language='ja', normalize_lengths=False, pcm_generator=None, pcm_policy='strict'):
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if normalize_lengths and notation != 'structured':
        raise ValueError('Native MDX length normalization requires structured notation')
    if pcm_policy not in ('strict', 'best-effort'):
        raise ValueError('PCM policy must be strict or best-effort')
    for suffix in ('.mdx.mml', '.pdx', '.pcm.timing.json', '.pcm.assessment.json', '.pcm.assessment.csv',
                   '.mdx.normalization.json', '.mdx.normalization.csv', '.mdx.before.normalize.mml'):
        artifact = outdir / (source.stem + suffix)
        if artifact.resolve() == source.resolve():
            raise ValueError('Conversion output must not replace its source input')
        artifact.unlink(missing_ok=True)
    metadata = {}
    pcm_metadata = {}
    source_loop = {}
    with TemporaryDirectory(prefix='opm-mdx-') as temporary:
        analysis_dir = outdir if dump_passes else Path(temporary)
        parse_vgm(str(source), str(analysis_dir), opm_metadata=metadata,
                  pcm_metadata=pcm_metadata,
                  loop_metadata=source_loop, dump_loop=dump_passes)
        pcm_analysis = pcm_metadata['analysis']
        has_pcm = bool(pcm_analysis.transfers or pcm_analysis.raw_commands or pcm_analysis.blocks)
        if has_pcm:
            for suffix in ('.mdx', '.vgm', '.pcm_bindings.csv', '.pcm_projection.csv',
                           '.pcm_clock.csv', '.pcm_target_commands.csv'):
                artifact = outdir / (source.stem + suffix)
                if artifact.resolve() != source.resolve():
                    artifact.unlink(missing_ok=True)
            for name in ('target.tsv', 'opm.mml', 'manifest.tsv', 'pdx_build.log', 'mdx_build.log'):
                (outdir / (source.stem + '.pcm') / name).unlink(missing_ok=True)
        if dump_passes and has_pcm:
            pcm_analysis.dump(outdir, source.stem)
        if not metadata['csv_path'] and not has_pcm and not pcm_analysis.clock_hz:
            raise ValueError('Input declares no supported OPM stream')
        analysis = (build_segments(metadata['csv_path'], end_vgmticks=metadata['source_end_vgmticks'])
                    if metadata['csv_path'] else OpmAnalysis((), (), pcm_analysis.source_end_vgmticks, False))
        if dump_passes:
            dump_analysis(analysis, state_csv=outdir/(source.stem+'_trace.opm.csv'),
                          segments_csv=outdir/(source.stem+'.opm.segments.csv'))
    if has_pcm and (notation != 'structured' or track_layout != 'channels'):
        raise ValueError('PCM output requires structured notation and channel tracks')
    if has_pcm and normalize_lengths:
        raise ValueError('PCM target timing must stay shared with OPM; --normalize-lengths is not supported yet')
    clock = None
    if notation == 'structured':
        from opm_mdx_music import infer_clock
        from pcm_mdx import boundaries
        clock = infer_clock(analysis.segments, analysis.source_end_vgmticks,
                            additional_times=boundaries(pcm_analysis) if has_pcm else ())
    multiplier = clock['chosen']['multiplier'] if clock else 1
    if analysis.segments:
        projection = project_segments(analysis.segments, end_vgmticks=analysis.source_end_vgmticks,
                                      sample_multiplier=multiplier)
    else:
        if metadata['csv_path'] and (metadata['clock_hz'] != 4000000 or
                                    metadata['chip_type'] != 'YM2151' or metadata['dual_chip']):
            raise ValueError('Initial MDX target requires one 4 MHz YM2151 instance')
        end = mdx_tick(analysis.source_end_vgmticks, multiplier)
        projection = MdxProjection((), analysis.source_end_vgmticks, end,
                                  projected_samples(end, multiplier), metadata['clock_hz'], multiplier)
    pcm_plan = None
    pcm_assessment = None
    if has_pcm:
        from pcm_mdx import project, write_pdx
        from pcm_assessment import ProjectionError
        try:
            candidate = project(pcm_analysis, stem=source.stem, sample_multiplier=multiplier,
                                policy=pcm_policy)
        except ProjectionError as error:
            _record_pcm_assessment(error.assessment, outdir, source.stem,
                                   requires_pdx=bool(pcm_analysis.samples))
            raise ProjectionError(f'{error}; PCM assessment: {outdir / (source.stem + ".pcm.assessment.json")}',
                                  error.assessment) from error
        pcm_assessment = candidate.assessment
        candidate.dump(outdir, source.stem)
        _record_pcm_assessment(pcm_assessment, outdir, source.stem,
                               requires_pdx=bool(candidate.bindings))
        if candidate.bindings:
            pcm_plan = candidate
            try:
                write_pdx(pcm_plan, pcm_analysis, outdir, source.stem, generator=pcm_generator)
            except (OSError, ValueError) as error:
                pcm_assessment.error(str(error))
                _record_pcm_assessment(pcm_assessment, outdir, source.stem, requires_pdx=True)
                raise
            (outdir / (source.stem + '.pcm.timing.json')).write_text(
                json.dumps(pcm_plan.summary(), indent=2) + '\n', encoding='utf-8')
            _record_pcm_assessment(pcm_assessment, outdir, source.stem, requires_pdx=True)
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
        pcm_options = (dict(additional_tracks={'P': pcm_plan.units},
                            additional_headers=(f'#pcmfile "{pcm_plan.pdx_name}"',
                                '; Readable PCM projection; canonical MDX uses .pcm/target.tsv.'))
                       if pcm_plan else {})
        try:
            structure = build_structure(projection, analysis.segments, title=title or source.stem,
                                        loops=loops, **pcm_options)
        except (OSError, ValueError) as error:
            if pcm_assessment is not None:
                pcm_assessment.error(str(error))
                _record_pcm_assessment(pcm_assessment, outdir, source.stem,
                                       requires_pdx=bool(pcm_plan))
            raise
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
    try:
        mml.write_text(text, encoding='utf-8', newline='\n')
    except OSError as error:
        mml.unlink(missing_ok=True)
        if pcm_assessment is not None:
            pcm_assessment.error(str(error))
            _record_pcm_assessment(pcm_assessment, outdir, source.stem,
                                   requires_pdx=bool(pcm_plan))
        raise
    if pcm_plan is not None:
        from pcm_mdx import write_mdx
        try:
            fm_structure = build_structure(projection, analysis.segments,
                                           title=title or source.stem, loops=loops)
            write_mdx(pcm_plan, fm_structure, outdir, source.stem, generator=pcm_generator)
        except (OSError, ValueError) as error:
            pcm_assessment.error(str(error))
            _record_pcm_assessment(pcm_assessment, outdir, source.stem, requires_pdx=True)
            raise
    if pcm_assessment is not None:
        pcm_assessment.generated()
        _record_pcm_assessment(pcm_assessment, outdir, source.stem,
                               requires_pdx=bool(pcm_plan))
    if dump_passes:
        dump_projection(projection, outdir / (source.stem + '.mdx.controls.csv'), track_layout=track_layout)
        report = projection.timing_report()
        report['track_layout'] = track_layout
        report['notation'] = notation
        if pcm_plan:
            report.update(pcm_plan.summary())
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

