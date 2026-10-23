"""Native DCSG evidence projected through the ordinary structured OPM backend."""
import json
import shutil
from pathlib import Path

from conversion_config import normalization_enabled, normalization_samples
from fm_state_runs import fm_short_state_samples
from vgm_io import read_vgm_bytes
from vgm_loop import read_loop_metadata


def convert(source, outdir, *, notation='structured', loops=True, song_loop=True,
            title=None, normalize_lengths=None, normalization_ms=8, fm_state_ms=24,
            pitch_policy='clamp', force=False):
    from dcsg import analyze, dump_analysis
    from dcsg_opm import project, dump_projection
    from opm_target_vgm import write_target_vgm
    from opm_conversion import convert as convert_opm
    from psg_scc_conversion import (_read_generated_csv, _source_normalization_check,
                                    _mark_projected_evidence)

    if notation not in ('structured', 'registers'):
        raise ValueError('DCSG OPM projection supports structured/registers notation')
    normalization_enabled(normalize_lengths, notation=notation)
    normalization_samples(normalization_ms)
    fm_short_state_samples(fm_state_ms)
    source, out = Path(source), Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    for suffix in ('.mdx.mml', '.mdx.normalization.json', '.fm.short_states.json',
                   '.fm.short_states.csv', '.dcsg_opm.json', '.dcsg_opm.forced_omissions.csv', '.dcsg_opm.approximations.csv'):
        artifact = out / (source.stem + suffix)
        if artifact.resolve() == source.resolve():
            raise ValueError('Conversion output must not replace its source input')
        artifact.unlink(missing_ok=True)
    raw = read_vgm_bytes(source)
    metadata = read_loop_metadata(raw)
    if song_loop and metadata['status'] not in ('no_loop', 'valid'):
        raise ValueError('Cannot project an invalid declared DCSG song loop')
    repeating = song_loop and metadata['status'] == 'valid'
    # Re-enter the loop without resetting source latches, noise or stereo state.
    native = analyze(raw, loop_count=2 if repeating else 1)
    dump_analysis(native, out, source.stem)
    loop_start = metadata['decoded_end_samples'] if repeating else None
    metadata.update(loop_count=2 if repeating else 1, replay_start_samples=loop_start,
                    playback_end_samples=native.end_sample)
    (out / (source.stem + '.dcsg.loop.json')).write_text(
        json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    plan = project(native, force=force, pitch_policy=pitch_policy,
                   terminate=not repeating)
    dump_projection(plan, out, source.stem)
    folder = out / 'projected_opm'
    folder.mkdir(exist_ok=True)
    target = write_target_vgm(plan, folder / (source.stem + '.vgm'),
        mapping_csv=folder / (source.stem + '.source_map.csv'),
        song_loop_start=loop_start, exact_source_times=True)
    _, source_map = _read_generated_csv(folder / (source.stem + '.source_map.csv'))
    mml, _, projection = convert_opm(target, folder, dump_passes=True,
        notation=notation, loops=loops, song_loop=song_loop, replayed_song_loop=True,
        title=title or source.stem, normalize_lengths=normalize_lengths,
        normalization_ms=normalization_ms, fm_state_ms=fm_state_ms,
        normalization_source_times={int(r['target_source_event_id']): int(r['vgmticks'])
                                    for r in source_map},
        normalization_validator=lambda candidate, report: _source_normalization_check(
            plan, metadata, candidate, report, source_map=source_map, exact_source_times=True))
    normalization = json.loads((folder / (source.stem + '.mdx.normalization.json')).read_text())
    _mark_projected_evidence(folder, source, target, plan, projection, normalization,
                             exact_source_times=True, source_chip_evidence='DCSG; no native OPM claimed')
    result = out / mml.name
    result.write_text('; DCSG to OPM approximation; native source and inferred attacks are retained separately.\n'
                      + mml.read_text(encoding='utf-8'), encoding='utf-8')
    for suffix in ('.mdx.normalization.json', '.fm.short_states.json', '.fm.short_states.csv'):
        artifact = folder / (source.stem + suffix)
        if artifact.is_file():
            shutil.copyfile(artifact, out / artifact.name)
    return result, plan
