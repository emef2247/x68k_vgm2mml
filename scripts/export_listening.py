"""Publish short, consistent listening filenames while retaining full diagnostics."""
import csv
import os
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from gd3 import read_gd3, title_from_gd3
from conversion_config import inspect_source, select_mdx_route


def safe_stem(relative):
    original = Path(relative).stem
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {
        prefix + str(number) for prefix in ('COM', 'LPT') for number in range(1, 10)}
    if re.fullmatch('[A-Za-z0-9_]{1,8}', original) and original.upper() not in reserved:
        return original
    prefix = re.sub('[^A-Z0-9]', '', original.upper())[:2].ljust(2, 'T')
    return prefix + hashlib.sha256(Path(relative).as_posix().encode('utf-8')).hexdigest()[:6].upper()


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_title(path, target):
    """Preserve each existing route's metadata policy and original-stem fallback."""
    try:
        route = select_mdx_route(inspect_source(path), compatibility_target=target)
    except ValueError:
        # Conversion will diagnose unsupported source semantics; do not replace that error.
        return path.stem, path.stem
    if route == 'psg-scc-to-opm':
        title = title_from_gd3(path, path.stem, 'ja')
        return title, title
    fields = read_gd3(path)
    if fields and (fields[1].strip() or fields[0].strip()):
        return None, fields[1].strip() or fields[0].strip()
    return path.stem, path.stem


def _bounded(path, output):
    if not path.resolve().is_relative_to(output):
        raise ValueError(f'Listening output path leaves output directory: {path}')
    return path


def _save_manifest(path, entries):
    temporary = path.with_suffix('.json.tmp')
    _bounded(temporary, path.parent.resolve())
    temporary.write_text(json.dumps(dict(schema_version=1, entries=entries), indent=2,
                                     ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def _load_entries(path):
    if not path.exists():
        return {}
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('entries'), dict):
        raise ValueError('Incompatible listening ownership manifest; use a fresh output directory')
    return manifest['entries']


def _check_publications(package, folder, stem, owned):
    publications = owned.get('published', {})
    for published, digest in publications.items():
        target = _bounded(package / published, package)
        if target.parent != folder or target.name not in {stem + ext for ext in ('.mml', '.mdx', '.pdx')}:
            raise ValueError(f'Invalid listening ownership entry: {target}')
        if target.exists() and (not target.is_file() or _digest(target) != digest):
            raise ValueError(f'Refusing to replace modified listening artifact: {target}')
    actual = {p.name.casefold(): p for p in folder.iterdir()} if folder.is_dir() else {}
    for extension in ('.mml', '.mdx', '.pdx'):
        target = _bounded(folder / (stem + extension), package)
        existing = actual.get(target.name.casefold())
        if existing is not None and existing.relative_to(package).as_posix() not in publications:
            raise ValueError(f'Refusing to overwrite unowned listening artifact: {existing}')


def _publish_bundle(candidates, package, diagnostics, owned, entry, manifest_path, entries):
    """Prepare all bytes before replacing a bundle, restoring old bytes on failure."""
    before = dict(entry)
    with tempfile.TemporaryDirectory(prefix='publish_', dir=diagnostics) as temporary:
        temporary = Path(temporary)
        prepared, backups = {}, {}
        for label, (current, target) in candidates.items():
            prepared[label] = temporary / ('new_' + target.name)
            shutil.copyfile(current, prepared[label])
        old_paths = {_bounded(package / name, package) for name in owned.get('published', {})}
        all_paths = old_paths | {target for _, target in candidates.values()}
        for index, target in enumerate(all_paths):
            if target.exists():
                backup = temporary / ('old_' + str(index))
                shutil.copyfile(target, backup)
                backups[target] = backup
        try:
            for label, (_, target) in candidates.items():
                prepared[label].replace(target)
            for target in old_paths - {target for _, target in candidates.values()}:
                target.unlink(missing_ok=True)
            entry['published'] = {target.relative_to(package).as_posix(): _digest(target)
                                  for _, target in candidates.values()}
            _save_manifest(manifest_path, entries)
        except BaseException:
            for target in all_paths:
                if target in backups:
                    backups[target].replace(target)
                else:
                    target.unlink(missing_ok=True)
            entry.clear()
            entry.update(before)
            raise


def _check_planned_layout(planned, output):
    """Reject file/directory and case aliases across the complete package plan."""
    directories, artifacts = {}, {}

    def directory(path):
        while path.is_relative_to(output):
            key = str(path).casefold()
            previous = directories.setdefault(key, path)
            if str(previous) != str(path):
                raise ValueError(f'Case-insensitive output directory collision: {previous} and {path}')
            if path.exists() and not path.is_dir():
                raise ValueError(f'Output directory is occupied by a file: {path}')
            if path == output:
                break
            path = path.parent

    def artifact(path):
        key = str(path).casefold()
        previous = artifacts.setdefault(key, path)
        if str(previous) != str(path):
            raise ValueError(f'Case-insensitive output artifact collision: {previous} and {path}')
        if path.exists() and not path.is_file():
            raise ValueError(f'Output artifact is occupied by a directory: {path}')
        directory(path.parent)

    for _, _, package, _, stem, folder, staged, _, _ in planned:
        directory(package)
        directory(folder)
        directory(package / '_diagnostics' / stem)
        artifact(staged)
        for extension in ('.mml', '.mdx', '.pdx'):
            artifact(folder / (stem + extension))
        for name in ('listening_manifest.json', 'listening_manifest.json.tmp', 'results.csv', 'results.json'):
            artifact(package / name)
    artifact(output / '_diagnostics' / 'results.csv')
    for key in artifacts.keys() & directories.keys():
        raise ValueError(f'Output artifact/directory collision: {artifacts[key]}')


def run_listening_batch(source, output, *, core, options):
    """Publish one flat listening package per original input directory."""
    from export_mdx import _save_results
    source = Path(source).resolve()
    adjacent = output is None
    output = (source if source.is_dir() else source.parent) if adjacent else Path(output).resolve()
    if not source.exists():
        raise ValueError(f'Input does not exist: {source}')
    if source.is_dir():
        if not adjacent and (source == output or source in output.parents or output in source.parents):
            raise ValueError('Input and output directories must be separate trees')
        files = []
        for directory, children, filenames in os.walk(source):
            children[:] = [name for name in children if name.casefold() not in
                           {'tracks', '_source_inputs', '_diagnostics'}]
            files.extend(Path(directory) / name for name in filenames
                         if Path(name).suffix.lower() in ('.vgm', '.vgz'))
        files.sort()
    else:
        if source.suffix.lower() not in ('.vgm', '.vgz') or (not adjacent and source.is_relative_to(output)):
            raise ValueError('Input must be a separate VGM/VGZ file or directory')
        files = [source]
    if not files:
        raise ValueError('No VGM/VGZ files found')
    packages, planned, names = {}, [], set()
    # Preflight the entire batch before staging or replacing any publication.
    for path in files:
        relative = path.relative_to(source) if source.is_dir() else Path(path.name)
        package = _bounded(output / relative.parent, output)
        manifest_path = _bounded(package / 'listening_manifest.json', output)
        if package not in packages:
            packages[package] = _load_entries(manifest_path)
        key = path.name
        owned = packages[package].get(key, {})
        stem = owned.get('safe_stem', safe_stem(relative))
        if not isinstance(stem, str) or not re.fullmatch('[A-Za-z0-9_]{1,8}', stem):
            raise ValueError(f'Invalid listening ownership stem for {path}')
        folder = _bounded(package / 'tracks', output)
        name = str(folder / stem).casefold()
        if name in names:
            raise ValueError(f'Listening filename collision for {relative}; use separate output trees')
        names.add(name)
        staged = _bounded(package / '_source_inputs' / (stem + path.suffix.lower()), output)
        owned = packages[package].get(key, {})
        if owned.get('source_path') and Path(owned['source_path']).resolve() != path.resolve():
            raise ValueError(f'Refusing to replace a different source owner: {path}')
        for directory in (package, folder, staged.parent, package / '_diagnostics' / stem):
            if directory.exists() and not directory.is_dir():
                raise ValueError(f'Output directory is occupied by a file: {directory}')
        _check_publications(package, folder, stem, owned)
        expected_staged = owned.get('staged_sha256', owned.get('source_sha256'))
        reuse_staged = False
        if staged.exists() and (not staged.is_file() or _digest(staged) != expected_staged):
            if not staged.is_file() or expected_staged is not None or _digest(staged) != _digest(path):
                raise ValueError(f'Refusing to replace unowned or modified staged source: {staged}')
            reuse_staged = True
        planned.append((path, relative, package, key, stem, folder, staged, owned, reuse_staged))
    _check_planned_layout(planned, output)
    output.mkdir(parents=True, exist_ok=True)
    rows, package_rows = [], {}
    path_labels = ('compiler_input', 'compiler_native_mdx', 'compiler_metadata',
                   'pcm_assessment', 'error_log', 'report', 'vgm')
    for path, relative, package, key, stem, folder, staged, owned, reuse_staged in planned:
        folder.mkdir(parents=True, exist_ok=True)
        staged.parent.mkdir(parents=True, exist_ok=True)
        source_sha256 = _digest(path)
        if reuse_staged:
            if not staged.is_file() or _digest(staged) != source_sha256:
                raise ValueError(f'Staged source changed before ownership recovery: {staged}')
        else:
            shutil.copyfile(path, staged)
        if _digest(staged) != source_sha256:
            raise ValueError('Staged source bytes changed unexpectedly')
        entries = packages[package]
        entry = dict(owned) if owned else dict(input=key, source_path=str(path), source_sha256=source_sha256, published={})
        entry.update(safe_stem=stem, staged_input=staged.relative_to(package).as_posix(),
                     staged_sha256=source_sha256)
        entries[key] = entry
        manifest_path = package / 'listening_manifest.json'
        _save_manifest(manifest_path, entries)
        title_override, title = original_title(path, options.get('target', 'mdx'))
        diagnostics = _bounded(package / '_diagnostics' / stem, output)
        diagnostics.mkdir(parents=True, exist_ok=True)
        row = core(staged, diagnostics, **options, listening_layout=False, _title=title_override,
                   _report_source=path, _display_name=relative.as_posix())[0]
        _check_publications(package, folder, stem, owned)
        row.update(input=relative.as_posix(), safe_stem=stem, source_sha256=source_sha256)
        for label in path_labels:
            if row.get(label):
                row[label] = str(_bounded(diagnostics / row[label], output).relative_to(output))
        candidates = {}
        for label, extension in (('mml', '.mml'), ('mdx', '.mdx'), ('pdx', '.pdx')):
            diagnostic = row.get(label)
            row[label] = ''
            if diagnostic and (label == 'mml' or row['status'] == 'success'):
                candidates[label] = (_bounded(diagnostics / diagnostic, output), folder / (stem + extension))
        # Preserve a completed listening set on a failed rerun. The result row and
        # latest_attempt describe the failure rather than advertising stale binaries.
        preserve = bool(owned.get('published')) and row['status'] != 'success'
        if not preserve:
            for current, target in candidates.values():
                if not current.is_file():
                    raise ValueError(f'Missing generated listening artifact: {current}')
            entry.update(source_sha256=source_sha256, status=row['status'], title=title)
            _publish_bundle(candidates, package, diagnostics, owned, entry, manifest_path, entries)
            for label, (_, target) in candidates.items():
                row[label] = str(target.relative_to(output))
        entry['latest_attempt_status'] = row['status']
        entry['diagnostics'] = diagnostics.relative_to(package).as_posix()
        entry['latest_attempt'] = dict(status=row['status'], source_sha256=source_sha256,
                                      diagnostics=diagnostics.relative_to(package).as_posix())
        _save_manifest(manifest_path, entries)
        rows.append(row)
        local_row = dict(row, input=key)
        for label in (*path_labels, 'mml', 'mdx', 'pdx'):
            if local_row.get(label):
                local_row[label] = str((output / local_row[label]).relative_to(package))
        if package not in package_rows:
            previous_rows = []
            if (package / 'results.csv').is_file():
                with (package / 'results.csv').open(encoding='utf-8', newline='') as stream:
                    previous_rows = list(csv.DictReader(stream))
            package_rows[package] = {r['input']: r for r in previous_rows}
        package_rows[package][key] = local_row
        _save_results(package, list(package_rows[package].values()))
        aggregate = _bounded(output / '_diagnostics', output)
        aggregate.mkdir(parents=True, exist_ok=True)
        # Aggregate paths are relative to the overall output root, like API rows.
        _save_results(aggregate, rows)
    return rows
