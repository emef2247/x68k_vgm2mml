"""Export VGM as MML, MDX, replay VGM and optional PDX, without comparison."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
from mdx_compiler import compile_mxc, compiler_evidence_paths
from export_report import write_export_report

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opm_mdx import mdx_tick
from vgm_io import read_vgm_bytes
from vgm_timing import command_times
from pcm_bank_stats import RESULT_FIELDS as PCM_BANK_FIELDS, summarize as bank_statistics, result_columns as bank_result_columns, format_lines as bank_console_lines


def tick_budget(source):
    """Bound playback using actual source waits and the finest MDX timer.

    A coarser inferred timer needs fewer ticks. The header's sample count is
    not authoritative, and scanning the stream does not replay source loops.
    """
    end = 0
    for event in command_times(read_vgm_bytes(source)):
        end = event.vgmticks + event.wait_samples
    limit = max(2, mdx_tick(end) + 2)
    if limit > 0xffffffff:
        raise ValueError('Source duration exceeds the external player tick range')
    return limit


def _text(value):
    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')


def _bounded(path, output):
    if not path.resolve().is_relative_to(output):
        raise ValueError(f'Output path leaves the selected output directory: {path}')
    return path


def _save_results(output, rows):
    fields = ('input', 'status', 'detail', 'compiler', 'compiler_input',
              'compiler_native_mdx', 'compiler_metadata', 'max_ticks', 'mml', 'mdx', 'vgm', 'pdx',
              'pdx_format', 'pcm_policy', 'pcm_policy_requested', 'pcm_policy_reason', 'pcm_projection_status', 'pcm_validation_status',
              'pcm_validation_run', 'pcm_known_losses', 'pcm_assessment', 'report',
              'report_status', 'report_error', 'error_log', 'safe_stem', 'source_sha256', *PCM_BANK_FIELDS)
    with _bounded(output / 'results.csv', output).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def inspect_export_commands(generator, mdx, census, timeout):
    """Inspect the compiled file without replay; missing diagnostics stay explicit."""
    try:
        result = subprocess.run([str(generator), '--inspect-commands', str(mdx), str(census)],
                                cwd=ROOT, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout)
        if result.returncode or not census.is_file():
            raise ValueError(result.stdout + result.stderr or 'Helper produced no command census')
        return ''
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        census.unlink(missing_ok=True)
        return f'MDX command statistics unavailable: {str(error).strip()[:180]}'


def run_batch(source, output, *, target='mdx', generator=None, timeout=1200,
              max_ticks=None,psg_model=None,psg_gain=None,scc_gain=None,scc_model=None,scc_voice_bank=None,
              opm_pitch_policy=None, pcm_policy=None, compiler='mmlx', mxc=None, run68=None,
              normalize_lengths=None, normalization_ms=8, fm_state_ms=24, no_vgm=True, song_loop=True, listening_layout=False, _title=None,
              _report_source=None, _display_name=None, fm_only=False, force=False,pcm_profile='standard',psg_only=False,scc_only=False,psg_output='opm',segapcm_projection='auto',pcm_bank_merge='budget96',pdx_format='ex-pdx'):
    if listening_layout:
        from export_listening import run_listening_batch
        return run_listening_batch(source, output, core=run_batch, options=dict(
            target=target, generator=generator, timeout=timeout, max_ticks=max_ticks,
            psg_model=psg_model,psg_gain=psg_gain,scc_gain=scc_gain,scc_model=scc_model,scc_voice_bank=scc_voice_bank,
            opm_pitch_policy=opm_pitch_policy, pcm_policy=pcm_policy, compiler=compiler,
            mxc=mxc, run68=run68, normalize_lengths=normalize_lengths, normalization_ms=normalization_ms, fm_state_ms=fm_state_ms, no_vgm=no_vgm, song_loop=song_loop, fm_only=fm_only, force=force,pcm_profile=pcm_profile,psg_only=psg_only,scc_only=scc_only,psg_output=psg_output,segapcm_projection=segapcm_projection,pcm_bank_merge=pcm_bank_merge,pdx_format=pdx_format))
    source, output = Path(source).resolve(), Path(output).resolve()
    from conversion_config import normalization_samples
    normalization_samples(normalization_ms)
    from fm_state_runs import fm_short_state_samples
    fm_short_state_samples(fm_state_ms)
    from pcm_profiles import get_profile
    get_profile(pcm_profile)
    if psg_only and scc_only:raise ValueError('--psg-only and --scc-only are mutually exclusive')
    if target not in ('mdx', 'opm', 'opm-additive'):
        raise ValueError('Target must be mdx, opm or opm-additive')
    if compiler not in ('mxc', 'mmlx'):
        raise ValueError('Compiler must be mxc or mmlx')
    if pcm_policy not in (None, 'auto', 'strict', 'best-effort'):
        raise ValueError('PCM policy must be auto, strict or best-effort')
    if pcm_policy is not None and target != 'mdx':
        raise ValueError('--pcm-policy requires --target mdx')
    if timeout <= 0 or (max_ticks is not None and not 0 < max_ticks <= 0xffffffff):
        raise ValueError('Timeout and playback tick limit must be positive and representable')
    if not source.exists():
        raise ValueError(f'Input does not exist: {source}')
    if source.is_dir():
        if source == output or source in output.parents or output in source.parents:
            raise ValueError('Input and output directories must be separate trees')
        files = sorted(p for p in source.rglob('*')
                       if p.is_file() and p.suffix.lower() in ('.vgm', '.vgz'))
    else:
        if source.suffix.lower() not in ('.vgm', '.vgz'):
            raise ValueError('Input must be a VGM/VGZ file or directory')
        if source.is_relative_to(output):
            raise ValueError('Output directory must not contain the input file')
        files = [source]
    if not files:
        raise ValueError('No VGM/VGZ files found')
    suffix = '.exe' if sys.platform == 'win32' else ''
    generator = Path(generator or shutil.which('mdx-fixture-generator') or
                     ROOT / 'scripts/mdx_fixture_generator/target/release' /
                     ('mdx-fixture-generator' + suffix)).resolve()
    if not generator.is_file():
        raise ValueError('Build scripts/mdx_fixture_generator or specify --generator')
    if segapcm_projection not in ('auto', 'bank', 'mix'):
        raise ValueError('SegaPCM projection must be auto, bank or mix')
    if pcm_bank_merge not in ('budget96', 'similar', 'off'):
        raise ValueError('PCM bank merge must be budget96, similar or off')
    if pdx_format not in ('ex-pdx', 'standard'):
        raise ValueError('PDX format must be ex-pdx or standard')
    options = ['--pdx-format',pdx_format,'--pcm-bank-merge',pcm_bank_merge,'--pcm-profile',pcm_profile,'--psg-output',psg_output,
               '--segapcm-projection',segapcm_projection]
    if psg_only:options.append('--psg-only')
    if scc_only:options.append('--scc-only')
    if force:
        options.append('--force')
    if fm_only:
        options.append('--fm-only')
    options.extend(['--normalization-ms', str(normalization_ms), '--fm-state-ms', str(fm_state_ms)])
    if normalize_lengths is not None:
        options.append('--normalize-lengths' if normalize_lengths else '--no-normalize-lengths')
    for flag, value in (('--psg-model', psg_model), ('--psg-gain', psg_gain),
                        ('--scc-gain',scc_gain),('--scc-model',scc_model),('--scc-voice-bank',Path(scc_voice_bank).resolve() if scc_voice_bank is not None else None),('--opm-pitch-policy',opm_pitch_policy)):
        if value is not None:
            options.extend([flag, str(value)])
    _bounded(output / 'results.csv', output)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in files:
        relative = path.relative_to(source) if source.is_dir() else Path(path.name)
        # Retain the input suffix to distinguish same-stem VGM and VGZ files.
        folder = _bounded(output / 'tracks' / relative, output)
        artifacts = [_bounded(folder / (path.stem + suffix), output)
                     for suffix in ('.mdx.mml', '.mdx', '.vgm')]
        pdx = _bounded(folder / (path.stem + '.pdx'), output)
        assessment = _bounded(folder / (path.stem + '.pcm.assessment.json'), output)
        census = _bounded(folder / (path.stem + '.mdx.commands.csv'), output)
        error_log = _bounded(output / '_errors' / relative.with_suffix(relative.suffix + '.log'), output)
        compiler_input = _bounded(output / '_compiler_inputs' /
                                  relative.with_suffix(relative.suffix + '.mxc.mml'), output)
        native_copy, compiler_metadata = (_bounded(p, output) for p in compiler_evidence_paths(compiler_input))
        row = dict(input=str(relative), status='', detail='', compiler=compiler, max_ticks='', pdx_format=pdx_format,
                   mml='', mdx='', vgm='', pdx='', error_log='', compiler_input='',
                   compiler_native_mdx='', compiler_metadata='', pcm_policy='',
                   pcm_projection_status='', pcm_validation_status='',
                   pcm_validation_run='', pcm_known_losses='', pcm_assessment='', report='',
                   report_status='', report_error='', safe_stem='', source_sha256='')
        row.update({field: '' for field in PCM_BANK_FIELDS})
        stage = 'conversion'
        try:
            folder.mkdir(parents=True, exist_ok=True)
            # Only our generated files are replaced. Old binaries must
            # not look like current successes if this run fails.
            for artifact in [*artifacts, pdx, assessment, compiler_input, native_copy, compiler_metadata,
                             folder / (path.stem + '.pcm.assessment.csv'),
                             folder / (path.stem + '.report.txt'), census,
                             folder / (path.stem + '.conversion.json'),
                             folder / (path.stem + '.segapcm_projection.json'),
                             folder / (path.stem + '.pcm_bank.stats.json'),
                             *(folder / (path.stem + suffix) for suffix in
                               ('.pcm_bank_merge.json', '.pcm_bank_merge.samples.csv', '.pcm_bank_merge.playbacks.csv', '.pcm_bank.source_validation.json')),
                             *(folder / (path.stem + '.pcm_' + kind + '.csv') for kind in
                               ('bindings', 'projection', 'omitted_playbacks')),
                             folder / (path.stem + '.opna_ssg.omissions.csv'),
                             folder / (path.stem + '.opna_ssg.omissions.json'),
                             folder / (path.stem + '.opna_fm.omissions.csv'),
                             folder / (path.stem + '.opna_fm.omissions.json'),
                             folder / (path.stem + '.opna.unmodeled.csv'),
                             folder / (path.stem + '.opna_force.skipped_registers.csv'),
                             folder / (path.stem + '.opna_force.skipped_registers.json'),
                             folder / (path.stem + '.psg_force.skipped_registers.csv'),
                             folder / (path.stem + '.psg_force.skipped_registers.json'),
                             folder / (path.stem + '.pcm.force_capacity.csv'),
                             folder / (path.stem + '.pcm.force_capacity.json'),
                             folder / (path.stem + '.mdx.normalization.json')]:
                artifact.unlink(missing_ok=True)
            command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(path),
                       '--target', target, '--outdir', str(folder), *options]
            if not song_loop:
                command.append('--no-song-loop')
            if target == 'mdx':
                command.extend(['--pcm-generator', str(generator),
                                '--pcm-policy', pcm_policy or 'auto'])
            if _title is not None:
                command.extend(['--title', _title])
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=timeout)
            if run.returncode:
                raise RuntimeError(run.stdout + run.stderr or f'Converter exited with {run.returncode}')
            conversion_path = folder / (path.stem + '.conversion.json')
            if conversion_path.is_file():
                conversion = json.loads(conversion_path.read_text(encoding='utf-8'))
                if conversion.get('status') == 'source_analyzed':
                    stage = 'target_projection'
                    raise RuntimeError('Native source analysis retained without target output. '
                                       'Use --fm-only to compile the OPM portion for diagnostic playback.')
            if not artifacts[0].is_file() or not artifacts[0].stat().st_size:
                raise RuntimeError('Converter produced no nonempty MML')
            stage = 'generation'
            limit = None if no_vgm else (max_ticks if max_ticks is not None else tick_budget(path))
            if limit is not None:
                row['max_ticks'] = limit
            command = None
            if pdx.is_file():
                row['compiler'] = 'typed_pcm_mmlx'
                if not pdx.stat().st_size or not artifacts[1].is_file() or not artifacts[1].stat().st_size:
                    raise RuntimeError('Converter produced no complete typed PCM MDX/PDX pair; '
                                       'readable PCM MML is not a replacement compilation input')
                if not no_vgm:
                    stage = 'replay'
                    command = [str(generator), '--from-mdx', str(artifacts[1]),
                               str(artifacts[2]), '--max-ticks', str(limit)]
            elif compiler == 'mxc':
                stage = 'compilation'
                compile_mxc(artifacts[0], artifacts[1], timeout=timeout,
                            mxc=mxc, run68=run68, generator=generator,
                            prepared_output=compiler_input)
                if not no_vgm:
                    stage = 'replay'
                    command = [str(generator), '--from-mdx', str(artifacts[1]),
                               str(artifacts[2]), '--max-ticks', str(limit)]
            else:
                row['compiler_input'] = str(artifacts[0].relative_to(output))
                if no_vgm:
                    stage = 'compilation'
                    command = [str(generator), '--compile-only', str(artifacts[0]), str(artifacts[1])]
                else:
                    command = [str(generator), *(str(p) for p in artifacts), '--max-ticks', str(limit)]
            if command is not None:
                run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                     encoding='utf-8', errors='replace', timeout=timeout)
                if run.returncode:
                    raise RuntimeError(run.stdout + run.stderr or f'Generator exited with {run.returncode}')
            required = artifacts[:2] if no_vgm else artifacts
            if any(not p.is_file() or not p.stat().st_size for p in required):
                raise RuntimeError('Generator did not produce all requested nonempty files')
            row['status'] = 'success'
            error_log.unlink(missing_ok=True)
        except subprocess.TimeoutExpired as error:
            row['status'] = stage + '_timeout'
            row['detail'] = f'{stage} timed out after {timeout} seconds'
            error_log.parent.mkdir(parents=True, exist_ok=True)
            error_log.write_text(_text(error.stdout) + _text(error.stderr) + '\n' + row['detail'] + '\n',
                                 encoding='utf-8')
        except (OSError, RuntimeError, ValueError) as error:
            row['detail'] = str(error).strip()
            row['status'] = ('pcm_replay_unavailable' if stage in ('generation', 'replay')
                             and 'PCM replay unavailable:' in row['detail'] else stage + '_failed')
            error_log.parent.mkdir(parents=True, exist_ok=True)
            error_log.write_text(row['detail'] + '\n', encoding='utf-8')
        if assessment.is_file():
            row['pcm_assessment'] = str(assessment.relative_to(output))
            try:
                report = json.loads(assessment.read_text(encoding='utf-8'))
                selection = report.get('policy_selection', {})
                row.update(pcm_policy_requested=selection.get('requested', pcm_policy or 'auto'),
                           pcm_policy_reason=selection.get('reason', ''))
                row.update(pcm_policy=report['policy'],
                           pcm_projection_status=report['assessment_status'],
                           pcm_validation_status=report['validation_status'],
                           pcm_validation_run=report['validation_run'],
                           pcm_known_losses=len(report['known_losses']))
                if stage == 'conversion' and report['artifact_status'] == 'blocked':
                    mdx_capacity = any(item.get('code') == 'mdx_capacity_exceeded'
                                       for item in report.get('items', []))
                    row['status'] = 'compilation_failed' if mdx_capacity else 'pcm_projection_blocked'
            except (OSError, ValueError, KeyError, TypeError) as error:
                row['status'] = 'assessment_failed'
                row['detail'] += f'\nCannot read PCM assessment: {error}'
                error_log.parent.mkdir(parents=True, exist_ok=True)
                error_log.write_text(row['detail'].strip() + '\n', encoding='utf-8')
        for label, artifact in zip(('mml', 'mdx', 'vgm'), artifacts):
            if artifact.is_file() and artifact.stat().st_size:
                row[label] = str(artifact.relative_to(output))
        if pdx.is_file() and pdx.stat().st_size:
            row['pdx'] = str(pdx.relative_to(output))
        if compiler_input.is_file() and compiler_input.stat().st_size:
            row['compiler_input'] = str(compiler_input.relative_to(output))
        for label, evidence in (('compiler_native_mdx', native_copy), ('compiler_metadata', compiler_metadata)):
            if evidence.is_file() and evidence.stat().st_size:
                row[label] = str(evidence.relative_to(output))
        if row['mdx']:
            diagnostic = inspect_export_commands(generator, artifacts[1], census, timeout)
            if diagnostic:
                row['detail'] = '\n'.join(filter(None, (row['detail'], diagnostic)))
        bank_summary = {}
        try:
            bank_summary = bank_statistics(folder, path.stem, allow_binary=bool(row['pdx']))
            row.update(bank_result_columns(bank_summary))
            if bank_summary:
                (folder / (path.stem + '.pcm_bank.stats.json')).write_text(
                    json.dumps(bank_summary, indent=2) + '\n', encoding='utf-8')
        except (OSError, ValueError, KeyError, TypeError) as error:
            row['detail'] = '\n'.join(filter(None, (row['detail'], f'PCM bank statistics unavailable: {error}')))
        try:
            summary_path = write_export_report(_report_source or path, folder, path.stem, row)
            row['report'] = str(summary_path.relative_to(output))
            row['report_status'] = 'success'
        except (OSError, ValueError, KeyError, TypeError) as error:
            row['report_status'] = 'failed'
            row['report_error'] = f'Cannot write TXT report: {error}'
            error_log.parent.mkdir(parents=True, exist_ok=True)
            error_log.write_text((row['detail'] + '\n' + row['report_error']).strip() + '\n', encoding='utf-8')
        if row['status'] != 'success' or row['report_status'] == 'failed':
            row['error_log'] = str(error_log.relative_to(output))
        rows.append(row)
        _save_results(output, rows)
        print(f"{_display_name or relative}: {row['status']}", flush=True)
        if row.get('pcm_policy_requested') == 'auto' and row['pcm_policy']:
            print(f"PCM policy: auto -> {row['pcm_policy']} ({row['pcm_policy_reason']})", flush=True)
        for line in bank_console_lines(bank_summary):
            print(line, flush=True)
        if force:
            from opna_force import force_console_lines
            try:
                for line in force_console_lines(folder, path.stem):
                    print(line, flush=True)
            except (OSError, ValueError, KeyError, TypeError) as error:
                print(f'Force diagnostic summary unavailable: {error}', flush=True)
    return rows


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('Value must be positive')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='VGM/VGZ file or directory to scan recursively')
    parser.add_argument('--outdir', type=Path, help='Output tree; omitted: packages beside source VGM files')
    parser.add_argument('--target', choices=('mdx', 'opm', 'opm-additive'), default='mdx', metavar='{mdx}',
                         help='MDX output with automatic source route (opm/opm-additive are deprecated aliases)')
    parser.add_argument('--normalize-lengths', action=argparse.BooleanOptionalAction, default=None,
                        help='Safe structured MDX target-clock correction (default: ON)')
    parser.add_argument('--normalization-ms', type=float, default=8,
                        help='Whole-note omission threshold and maximum target boundary movement in ms (default: 8; ignored with --no-normalize-lengths)')
    parser.add_argument('--fm-state-ms', type=float, default=24,
                        help='Eligible intra-note FM-state omission threshold in ms (default: 24)')
    parser.add_argument('--compiler', choices=('mxc', 'mmlx'), default='mmlx',
                        help='FM-only MML compiler (default mmlx); typed PCM uses mmlx')
    parser.add_argument('--mxc', type=Path, help='Native MXC.X compiler')
    parser.add_argument('--run68', type=Path, help='run68 executable for native MXC')
    parser.add_argument('--generator', type=Path,
                        help='Rust replay helper and default mmlx/typed PCM compiler')
    parser.add_argument('--timeout', type=positive, default=1200, help='Seconds per stage per input (default: 1200)')
    parser.add_argument('--max-ticks', type=positive, help='Playback limit; default derived from source waits')
    parser.add_argument('--no-song-loop', action='store_true', help='Export one finite source pass, without the declared VGM song loop')
    replay = parser.add_mutually_exclusive_group()
    replay.add_argument('--vgm', dest='no_vgm', action='store_false',
                        help='Also replay the generated MDX to a verification VGM (off by default)')
    replay.add_argument('--no-vgm', dest='no_vgm', action='store_true',
                        help='Compatibility option: omit verification VGM (already the default)')
    parser.set_defaults(no_vgm=True)
    parser.add_argument('--force', action='store_true',
                        help='Partial MDX output: omit unsupported OPNA HW effects and excess PCM samples; list all losses')
    parser.add_argument('--fm-only', action='store_true',
                        help='Diagnostic OPM + SegaPCM export: explicitly omit SegaPCM from MDX; retain source evidence')
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument('--psg-only','--psg_only',action='store_true')
    selection.add_argument('--scc-only','--scc_only',action='store_true')
    parser.add_argument('--psg-output',choices=('opm','pcm'),default='opm')
    parser.add_argument('--psg-model', choices=('fm', 'additive'))
    parser.add_argument('--psg-gain', type=float)
    parser.add_argument('--scc-gain',type=float)
    parser.add_argument('--scc-model',choices=('additive','additive8','fm-additive','fm-fm'),help='SCC voice model (default fm-additive; fit missing bank automatically)')
    parser.add_argument('--scc-voice-bank',type=Path)
    parser.add_argument('--opm-pitch-policy', choices=('clamp', 'error'))
    parser.add_argument('--pcm-policy', choices=('auto', 'strict', 'best-effort'),
                        help='PCM policy: auto (default), strict or best-effort; auto follows observed DAC supply')
    parser.add_argument('--pdx-format',choices=('ex-pdx','standard'),default='ex-pdx',
                        help='PDX sample lengths: ex-pdx (default, 32-bit) or standard (16-bit)')
    parser.add_argument('--pcm-profile',choices=('standard','low','ultra_low'),default='standard',
                        help='PCM output rate/size profile (default: standard)')
    parser.add_argument('--segapcm-projection',choices=('auto','bank','mix'),default='auto',
                        help='SegaPCM reusable finite bank preference (auto), required bank, or legacy mix')
    parser.add_argument('--pcm-bank-merge',choices=('budget96','similar','off'),default='budget96',
                        help='PCM sharing: budget96 (default) fits 96 samples and a 1,200,000-byte PDX; similar keeps quality bounds; off keeps exact sharing')
    args = parser.parse_args()
    try:
        rows = run_batch(args.input, args.outdir, target=args.target, generator=args.generator,
                         compiler=args.compiler, mxc=args.mxc, run68=args.run68,
                         timeout=args.timeout, max_ticks=args.max_ticks, psg_model=args.psg_model,
                         psg_gain=args.psg_gain,scc_gain=args.scc_gain,scc_model=args.scc_model,scc_voice_bank=args.scc_voice_bank,
                          opm_pitch_policy=args.opm_pitch_policy, pcm_policy=args.pcm_policy,
                          normalize_lengths=args.normalize_lengths, normalization_ms=args.normalization_ms, fm_state_ms=args.fm_state_ms, no_vgm=args.no_vgm,
                          listening_layout=True, song_loop=not args.no_song_loop, fm_only=args.fm_only, force=args.force,pcm_profile=args.pcm_profile,psg_only=args.psg_only,scc_only=args.scc_only,psg_output=args.psg_output,segapcm_projection=args.segapcm_projection,pcm_bank_merge=args.pcm_bank_merge,pdx_format=args.pdx_format)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    success = sum(row['status'] == 'success' for row in rows)
    output_root = args.outdir or (args.input if args.input.is_dir() else args.input.parent)
    print(f'{success}/{len(rows)} exported; results: {output_root / "_diagnostics/results.csv"}')
    return 0 if success == len(rows) and not any(row.get('report_status') == 'failed' for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
