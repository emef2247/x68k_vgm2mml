"""Convert native OPM VGM through inspectable Segments to MDX MML controls."""
import json
import csv
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from opm import OpmAnalysis, build_segments, dump_analysis
from opm_mdx import MdxProjection, mdx_tick, projected_samples, project_segments, render, dump_projection
from vgm_reader import parse_vgm
from conversion_config import normalization_enabled
from pcm_assessment import generated_binary_artifacts


def _record_pcm_assessment(assessment, outdir, stem, *, requires_pdx, retained=()):
    for name, suffix in (('mml', '.mdx.mml'), ('mdx', '.mdx'), ('pdx', '.pdx')):
        path = outdir / (stem + suffix)
        required = name == 'mml' or (name in ('pdx', 'mdx') and requires_pdx)
        status = ('preserved_existing' if path in retained else
                  'generated' if path.is_file() and path.stat().st_size else
                  'blocked' if required and assessment.artifact_status == 'blocked' else
                  'not_generated' if required else 'not_requested')
        assessment.artifacts[name] = dict(path=str(path), status=status, required=required)
        if status == 'generated':
            assessment.artifacts[name]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    assessment.dump(outdir, stem)


def convert(source, outdir, *, dump_passes=False, track_layout='channels', notation='structured', loops=True, title=None, gd3_language='ja', normalize_lengths=None, pcm_generator=None, pcm_policy='strict', normalization_validator=None, normalization_source_times=None):
    source, outdir = Path(source), Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    requested_normalization = normalize_lengths
    normalize_lengths = normalization_enabled(normalize_lengths, notation=notation)
    if pcm_policy not in ('strict', 'best-effort'):
        raise ValueError('PCM policy must be strict or best-effort')
    owned_binary = generated_binary_artifacts(outdir, source.stem)
    retained_binary = tuple(path for name in ('mdx', 'pdx')
                            if (path := outdir / (source.stem + '.' + name)).is_file()
                            and path not in owned_binary)
    artifacts = list(owned_binary)
    for suffix in ('.mdx.mml', '.pcm.timing.json', '.pcm.assessment.json', '.pcm.assessment.csv',
                   '.mdx.normalization.json', '.mdx.normalization.csv', '.mdx.before.normalize.mml'):
        artifacts.append(outdir / (source.stem + suffix))
    for artifact in artifacts:
        if artifact.resolve() == source.resolve():
            raise ValueError('Conversion output must not replace its source input')
        if not artifact.resolve().is_relative_to(outdir.resolve()):
            raise ValueError('Conversion output leaves its output directory')
    for artifact in artifacts:
        artifact.unlink(missing_ok=True)
    def record_pcm_assessment(assessment, *, requires_pdx):
        _record_pcm_assessment(assessment, outdir, source.stem,
                               requires_pdx=requires_pdx, retained=retained_binary)
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
            for suffix in ('.pcm_bindings.csv', '.pcm_projection.csv',
                           '.pcm_clock.csv', '.pcm_target_commands.csv', '.pcm_omitted_playbacks.csv'):
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
        if metadata['write_count'] and (metadata['clock_hz'] != 4000000 or
                                    metadata['chip_type'] != 'YM2151' or metadata['dual_chip']):
            raise ValueError('Initial MDX target requires one 4 MHz YM2151 instance')
        end = mdx_tick(analysis.source_end_vgmticks, multiplier)
        projection = MdxProjection((), analysis.source_end_vgmticks, end,
                                  projected_samples(end, multiplier),
                                  metadata['clock_hz'] if metadata['write_count'] else 4000000, multiplier)
    before = projection
    normalization = dict(status='unchanged', reason='target-clock correction disabled',
                         source_segments_unchanged=True, before=before.timing_report())
    evidence = []
    baseline_pcm_plan = None
    if normalize_lengths:
        from opm_note_normalization import normalize_projection
        projection, normalization, evidence = normalize_projection(analysis.segments, before,
                                                                   loop_metadata=source_loop,
                                                                   pcm_analysis=pcm_analysis if has_pcm else None,
                                                                   output_short_note_policy=True,
                                                                   source_events=analysis.events,
                                                                   source_event_times=normalization_source_times)
        if normalization['status'] == 'applied' and normalization_validator is not None:
            check = normalization_validator(projection, normalization)
            normalization['source_projection_check'] = check
            if not check['accepted']:
                projection = before
                normalization.update(status='unchanged', reason=check['reason'],
                                     short_note_omission_adopted=False, omitted_pcm_playback_ids=[])
                for row in evidence:
                    row['projection_status'] = 'unchanged'
        if normalization['status'] == 'applied' and has_pcm:
            from pcm_mdx import project
            from opm_mdx_music import build_music
            def preflight_pcm(selected, *, omitted=()):
                plan = project(pcm_analysis, stem=source.stem,
                               sample_multiplier=selected.sample_multiplier, policy=pcm_policy,
                               omit_playback_ids=omitted)
                build_music(selected, analysis.segments, title=source.stem, loops=loops,
                            additional_tracks={'P': plan.units} if plan.bindings else {})
                return plan
            try:
                baseline_pcm_plan = preflight_pcm(before)
            except ValueError as baseline_error:
                normalization['baseline_pcm_projection'] = dict(status='unavailable',
                                                                 reason=str(baseline_error))
            else:
                normalization['baseline_pcm_projection'] = dict(status='available')
            try:
                preflight_pcm(projection, omitted=normalization.get('omitted_pcm_playback_ids', ()))
            except ValueError as candidate_error:
                if baseline_pcm_plan is not None:
                    projection = before
                    normalization.update(status='unchanged',
                                         reason=f'normalized shared-clock projection rejected: {candidate_error}',
                                         short_note_omission_adopted=False, omitted_pcm_playback_ids=[])
                    for row in evidence:
                        row['projection_status'] = 'unchanged'
    elif notation != 'structured':
        normalization['reason'] = 'target-clock correction is not applicable to this notation'
    normalization.update(requested=requested_normalization, enabled=normalize_lengths,
                         adopted=normalization['status'] == 'applied', notation=notation,
                         selected=projection.timing_report(), shared_pcm_clock=has_pcm)
    multiplier = projection.sample_multiplier
    normalization_path = outdir / (source.stem + '.mdx.normalization.json')
    normalization_path.write_text(json.dumps(normalization, indent=2) + '\n', encoding='utf-8')
    if dump_passes and evidence:
        with (outdir / (source.stem + '.mdx.normalization.csv')).open('w', newline='', encoding='utf-8') as stream:
            fields = list(dict.fromkeys(k for row in evidence for k in row))
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in evidence:
                writer.writerow({k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()})
    pcm_plan = None
    pcm_assessment = None
    if has_pcm:
        from pcm_mdx import project, write_pdx
        from pcm_assessment import ProjectionError
        try:
            candidate = project(pcm_analysis, stem=source.stem, sample_multiplier=multiplier,
                                policy=pcm_policy,
                                omit_playback_ids=normalization.get('omitted_pcm_playback_ids', ()))
        except ProjectionError as error:
            record_pcm_assessment(error.assessment, requires_pdx=bool(pcm_analysis.samples))
            raise ProjectionError(f'{error}; PCM assessment: {outdir / (source.stem + ".pcm.assessment.json")}',
                                  error.assessment) from error
        pcm_assessment = candidate.assessment
        candidate.dump(outdir, source.stem)
        record_pcm_assessment(pcm_assessment, requires_pdx=bool(candidate.bindings))
        if candidate.bindings:
            pcm_plan = candidate
            try:
                if retained_binary:
                    raise ValueError('PCM output would replace existing MDX/PDX without a matching generation record; '
                                     'use a separate --outdir')
                write_pdx(pcm_plan, pcm_analysis, outdir, source.stem, generator=pcm_generator)
            except (OSError, ValueError) as error:
                pcm_assessment.error(str(error))
                record_pcm_assessment(pcm_assessment, requires_pdx=True)
                raise
            (outdir / (source.stem + '.pcm.timing.json')).write_text(
                json.dumps(pcm_plan.summary(), indent=2) + '\n', encoding='utf-8')
            record_pcm_assessment(pcm_assessment, requires_pdx=True)
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
                record_pcm_assessment(pcm_assessment, requires_pdx=bool(pcm_plan))
            raise
        text = structure.text
        if (dump_passes and normalization and normalization['status'] == 'applied'
                and (not has_pcm or baseline_pcm_plan is not None)):
            baseline_pcm_options = (dict(additional_tracks={'P': baseline_pcm_plan.units},
                                         additional_headers=(f'#pcmfile "{baseline_pcm_plan.pdx_name}"',
                                             '; Readable PCM projection; canonical MDX uses .pcm/target.tsv.'))
                                    if baseline_pcm_plan else {})
            baseline = build_structure(before, analysis.segments, title=title or source.stem,
                                       loops=loops, **baseline_pcm_options)
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
            record_pcm_assessment(pcm_assessment, requires_pdx=bool(pcm_plan))
        raise
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
    if pcm_plan is not None:
        from pcm_mdx import write_mdx
        try:
            fm_structure = build_structure(projection, analysis.segments,
                                           title=title or source.stem, loops=loops)
            write_mdx(pcm_plan, fm_structure, outdir, source.stem, generator=pcm_generator)
        except (OSError, ValueError) as error:
            if not isinstance(error, ProjectionError):
                pcm_assessment.error(str(error))
            record_pcm_assessment(pcm_assessment, requires_pdx=True)
            raise
    if pcm_assessment is not None:
        pcm_assessment.generated()
        record_pcm_assessment(pcm_assessment, requires_pdx=bool(pcm_plan))
    return mml, analysis, projection

