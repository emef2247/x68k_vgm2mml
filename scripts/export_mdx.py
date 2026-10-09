"""Export VGM as MML, MDX, replay VGM and optional PDX, without comparison."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
from mdx_compiler import compile_mxc, compiler_evidence_paths

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'py'))
from opm_mdx import mdx_tick
from vgm_io import read_vgm_bytes
from vgm_timing import command_times


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
              'pcm_policy', 'pcm_projection_status', 'pcm_validation_status',
              'pcm_validation_run', 'pcm_known_losses', 'pcm_assessment', 'error_log')
    with _bounded(output / 'results.csv', output).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run_batch(source, output, *, target='mdx', generator=None, timeout=180,
              max_ticks=None, psg_model=None, psg_gain=None, scc_gain=None,
              opm_pitch_policy=None, pcm_policy=None, compiler='mxc', mxc=None, run68=None,
              normalize_lengths=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if target not in ('mdx', 'opm', 'opm-additive'):
        raise ValueError('Target must be mdx, opm or opm-additive')
    if compiler not in ('mxc', 'mmlx'):
        raise ValueError('Compiler must be mxc or mmlx')
    if pcm_policy not in (None, 'strict', 'best-effort'):
        raise ValueError('PCM policy must be strict or best-effort')
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
    options = []
    if normalize_lengths is not None:
        options.append('--normalize-lengths' if normalize_lengths else '--no-normalize-lengths')
    for flag, value in (('--psg-model', psg_model), ('--psg-gain', psg_gain),
                        ('--scc-gain', scc_gain), ('--opm-pitch-policy', opm_pitch_policy)):
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
        error_log = _bounded(output / '_errors' / relative.with_suffix(relative.suffix + '.log'), output)
        compiler_input = _bounded(output / '_compiler_inputs' /
                                  relative.with_suffix(relative.suffix + '.mxc.mml'), output)
        native_copy, compiler_metadata = (_bounded(p, output) for p in compiler_evidence_paths(compiler_input))
        row = dict(input=str(relative), status='', detail='', compiler=compiler, max_ticks='',
                   mml='', mdx='', vgm='', pdx='', error_log='', compiler_input='',
                   compiler_native_mdx='', compiler_metadata='', pcm_policy='',
                   pcm_projection_status='', pcm_validation_status='',
                   pcm_validation_run='', pcm_known_losses='', pcm_assessment='')
        stage = 'conversion'
        try:
            folder.mkdir(parents=True, exist_ok=True)
            # Only our generated files are replaced. Old binaries must
            # not look like current successes if this run fails.
            for artifact in [*artifacts, pdx, assessment, compiler_input, native_copy, compiler_metadata,
                             folder / (path.stem + '.pcm.assessment.csv')]:
                artifact.unlink(missing_ok=True)
            command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(path),
                       '--target', target, '--outdir', str(folder), *options]
            if target == 'mdx':
                command.extend(['--pcm-generator', str(generator),
                                '--pcm-policy', pcm_policy or 'strict'])
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=timeout)
            if run.returncode:
                raise RuntimeError(run.stdout + run.stderr or f'Converter exited with {run.returncode}')
            if not artifacts[0].is_file() or not artifacts[0].stat().st_size:
                raise RuntimeError('Converter produced no nonempty MML')
            stage = 'generation'
            limit = max_ticks if max_ticks is not None else tick_budget(path)
            row['max_ticks'] = limit
            if pdx.is_file() and artifacts[1].is_file():
                row['compiler'] = 'typed_pcm_mmlx'
                stage = 'replay'
                command = [str(generator), '--from-mdx', str(artifacts[1]),
                           str(artifacts[2]), '--max-ticks', str(limit)]
            elif not pdx.is_file() and compiler == 'mxc':
                stage = 'compilation'
                compile_mxc(artifacts[0], artifacts[1], timeout=timeout,
                            mxc=mxc, run68=run68, generator=generator,
                            prepared_output=compiler_input)
                stage = 'replay'
                command = [str(generator), '--from-mdx', str(artifacts[1]),
                           str(artifacts[2]), '--max-ticks', str(limit)]
            else:
                if pdx.is_file():
                    row['compiler'] = 'typed_pcm_mmlx'
                else:
                    row['compiler_input'] = str(artifacts[0].relative_to(output))
                command = [str(generator), *(str(p) for p in artifacts), '--max-ticks', str(limit)]
                if pdx.is_file():
                    command.extend(['--pcm-mode', 'standard'])
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=timeout)
            if run.returncode:
                raise RuntimeError(run.stdout + run.stderr or f'Generator exited with {run.returncode}')
            if any(not p.is_file() or not p.stat().st_size for p in artifacts):
                raise RuntimeError('Generator did not produce all three nonempty files')
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
                row.update(pcm_policy=report['policy'],
                           pcm_projection_status=report['assessment_status'],
                           pcm_validation_status=report['validation_status'],
                           pcm_validation_run=report['validation_run'],
                           pcm_known_losses=len(report['known_losses']))
                if stage == 'conversion' and report['artifact_status'] == 'blocked':
                    row['status'] = 'pcm_projection_blocked'
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
        if row['status'] != 'success':
            row['error_log'] = str(error_log.relative_to(output))
        rows.append(row)
        _save_results(output, rows)
        print(f"{relative}: {row['status']}", flush=True)
    return rows


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('Value must be positive')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='VGM/VGZ file or directory to scan recursively')
    parser.add_argument('--outdir', type=Path, required=True, help='Separate output tree')
    parser.add_argument('--target', choices=('mdx', 'opm', 'opm-additive'), default='mdx', metavar='{mdx}',
                         help='MDX output with automatic source route (opm/opm-additive are deprecated aliases)')
    parser.add_argument('--normalize-lengths', action=argparse.BooleanOptionalAction, default=None,
                        help='Safe structured MDX target-clock correction (default: ON)')
    parser.add_argument('--compiler', choices=('mxc', 'mmlx'), default='mxc',
                        help='FM-only MML compiler (default mxc); typed PCM uses mmlx')
    parser.add_argument('--mxc', type=Path, help='Native MXC.X compiler')
    parser.add_argument('--run68', type=Path, help='run68 executable for native MXC')
    parser.add_argument('--generator', type=Path,
                        help='Rust replay helper and explicit mmlx/typed PCM compiler')
    parser.add_argument('--timeout', type=positive, default=180, help='Seconds per stage per input')
    parser.add_argument('--max-ticks', type=positive, help='Playback limit; default derived from source waits')
    parser.add_argument('--psg-model', choices=('fm', 'additive'))
    parser.add_argument('--psg-gain', type=float)
    parser.add_argument('--scc-gain', type=float)
    parser.add_argument('--opm-pitch-policy', choices=('clamp', 'error'))
    parser.add_argument('--pcm-policy', choices=('strict', 'best-effort'),
                        help='Native PCM projection policy; default strict')
    args = parser.parse_args()
    try:
        rows = run_batch(args.input, args.outdir, target=args.target, generator=args.generator,
                         compiler=args.compiler, mxc=args.mxc, run68=args.run68,
                         timeout=args.timeout, max_ticks=args.max_ticks, psg_model=args.psg_model,
                         psg_gain=args.psg_gain, scc_gain=args.scc_gain,
                          opm_pitch_policy=args.opm_pitch_policy, pcm_policy=args.pcm_policy,
                          normalize_lengths=args.normalize_lengths)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    success = sum(row['status'] == 'success' for row in rows)
    print(f'{success}/{len(rows)} exported; results: {args.outdir / "results.csv"}')
    return 0 if success == len(rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
