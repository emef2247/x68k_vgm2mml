"""Export VGM files as MML, MDX and OPM VGM for listening, without comparison."""
import argparse
import csv
from pathlib import Path
import subprocess
import sys

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
    fields = ('input', 'status', 'detail', 'max_ticks', 'mml', 'mdx', 'vgm', 'error_log')
    with _bounded(output / 'results.csv', output).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run_batch(source, output, *, target='mdx', generator=None, timeout=180,
              max_ticks=None, psg_model=None, psg_gain=None, scc_gain=None,
              opm_pitch_policy=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if target not in ('mdx', 'opm', 'opm-additive'):
        raise ValueError('Target must be mdx, opm or opm-additive')
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
    generator = Path(generator or ROOT / 'scripts/mdx_fixture_generator/target/release' /
                     ('mdx-fixture-generator' + suffix)).resolve()
    if not generator.is_file():
        raise ValueError('Build scripts/mdx_fixture_generator or specify --generator')
    options = []
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
        artifacts = [folder / (path.stem + suffix) for suffix in ('.mdx.mml', '.mdx', '.vgm')]
        error_log = _bounded(output / '_errors' / relative.with_suffix(relative.suffix + '.log'), output)
        row = dict(input=str(relative), status='', detail='', max_ticks='',
                   mml='', mdx='', vgm='', error_log='')
        stage = 'conversion'
        try:
            folder.mkdir(parents=True, exist_ok=True)
            # Only our three generated files are replaced. Old binaries must
            # not look like current successes if this run fails.
            for artifact in artifacts:
                artifact.unlink(missing_ok=True)
            command = [sys.executable, str(ROOT / 'vgm2mml.py'), str(path),
                       '--target', target, '--outdir', str(folder), *options]
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=timeout)
            if run.returncode:
                raise RuntimeError(run.stdout + run.stderr or f'Converter exited with {run.returncode}')
            if not artifacts[0].is_file() or not artifacts[0].stat().st_size:
                raise RuntimeError('Converter produced no nonempty MML')
            stage = 'generation'
            limit = max_ticks if max_ticks is not None else tick_budget(path)
            row['max_ticks'] = limit
            command = [str(generator), *(str(p) for p in artifacts), '--max-ticks', str(limit)]
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
            row['status'] = stage + '_failed'
            row['detail'] = str(error).strip()
            error_log.parent.mkdir(parents=True, exist_ok=True)
            error_log.write_text(row['detail'] + '\n', encoding='utf-8')
        for label, artifact in zip(('mml', 'mdx', 'vgm'), artifacts):
            if artifact.is_file() and artifact.stat().st_size:
                row[label] = str(artifact.relative_to(output))
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
    parser.add_argument('--target', choices=('mdx', 'opm', 'opm-additive'), default='mdx',
                        help='mdx: native OPM (default); opm/opm-additive: PSG/SCC input')
    parser.add_argument('--generator', type=Path, help='External MDX compiler/player executable')
    parser.add_argument('--timeout', type=positive, default=180, help='Seconds per stage per input')
    parser.add_argument('--max-ticks', type=positive, help='Playback limit; default derived from source waits')
    parser.add_argument('--psg-model', choices=('fm', 'additive'))
    parser.add_argument('--psg-gain', type=float)
    parser.add_argument('--scc-gain', type=float)
    parser.add_argument('--opm-pitch-policy', choices=('clamp', 'error'))
    args = parser.parse_args()
    try:
        rows = run_batch(args.input, args.outdir, target=args.target, generator=args.generator,
                         timeout=args.timeout, max_ticks=args.max_ticks, psg_model=args.psg_model,
                         psg_gain=args.psg_gain, scc_gain=args.scc_gain,
                         opm_pitch_policy=args.opm_pitch_policy)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    success = sum(row['status'] == 'success' for row in rows)
    print(f'{success}/{len(rows)} exported; results: {args.outdir / "results.csv"}')
    return 0 if success == len(rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
