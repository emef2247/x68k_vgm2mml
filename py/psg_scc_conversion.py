"""PSG/SCC to OPM target orchestration, shared by the CLI and diagnostics."""
import shutil
import tempfile
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from vgm_io import read_vgm_bytes, read_vgm_header
from vgm_timing import command_times
from vgm_reader import parse_vgm
from psg import build_segments as build_psg
from scc import build_segments as build_scc
from psg_scc_opm import project


@dataclass(frozen=True)
class StructuredContext:
    performance: object
    analysis: object
    projection: object

def source_facts(raw):
    header = read_vgm_header(raw)
    clocks = [header['ay_clock_raw'], header['scc_clock_raw']]
    ay_type, ay_flags = header['ay_type'], header['ay_flags']
    if any(c & 0xc0000000 for c in clocks):
        raise ValueError('Dual chips and SCC variants are not implemented in this target')
    if clocks[0] and (ay_type != 0 or ay_flags not in (0, 1, 2, 3)):
        raise ValueError('Volume/pitch profile supports AY8910 legacy/single output flags only')
    end = 0
    silent_opll_writes = 0
    absent_scc_writes = 0
    for event in command_times(raw):
        cmd = event.command
        end = event.vgmticks + event.wait_samples
        if cmd in (0x61, 0x62, 0x63, 0x64, 0x66) or 0x70 <= cmd <= 0x7f:
            continue
        if cmd == 0xa0:
            if not clocks[0] or raw[event.address + 1] > 15:
                raise ValueError('Unsupported AY instance/register or missing clock')
        elif cmd == 0x51:
            reg, data = raw[event.address + 1:event.address + 3]
            if (0x20 <= reg <= 0x28 and data & 0x10) or (reg == 0x0e and data & 0x20 and data & 0x1f):
                raise ValueError('Active OPLL is not supported by the PSG/SCC OPM target')
            silent_opll_writes += 1
        elif cmd == 0xd2:
            port = raw[event.address + 1]
            if not clocks[1]:
                if port == 2 and raw[event.address + 3] & 15:
                    raise ValueError('SCC volume written without a clock')
                absent_scc_writes += 1
            if port not in (0, 1, 2, 3):
                raise ValueError('SCC test/variant/instance writes require further target support')
        else:
            raise ValueError(f'Unsupported source command in this prototype: {cmd:#x}')
    return dict(psg_clock=clocks[0], scc_clock=clocks[1], end_vgmticks=end,
                ay_type=ay_type, ay_flags=ay_flags, silent_opll_writes=silent_opll_writes, absent_scc_writes=absent_scc_writes)


def _read_generated_csv(path):
    """Read full provenance fields, restoring the process-wide CSV limit."""
    previous_limit = csv.field_size_limit()
    # UTF-8 field character counts cannot exceed the containing file's bytes.
    read_limit = max(previous_limit, path.stat().st_size)
    try:
        csv.field_size_limit(read_limit)
        with path.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            return list(reader.fieldnames or ()), list(reader)
    finally:
        csv.field_size_limit(previous_limit)


def _mark_projected_evidence(folder, source, target, performance, projection):
    """Label generated OPM evidence; original PSG/SCC CSVs remain unchanged."""
    mapping = folder / (source.stem + '.source_map.csv')
    columns, rows = _read_generated_csv(mapping)
    errors = []
    for row in rows:
        tick = projection.mdx_tick(int(row['target_vgmticks']))
        sample = projection.projected_samples(tick)
        row.update(final_mdx_tick=tick, final_projected_vgmticks=sample,
                   source_to_final_error_samples=sample-int(row['vgmticks']))
        errors.append(row['source_to_final_error_samples'])
    errors.append(projection.end_projected_vgmticks-performance.source_end)
    for name in ('final_mdx_tick', 'final_projected_vgmticks', 'source_to_final_error_samples'):
        columns.append(name)
    with mapping.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    for path in folder.glob('*.csv'):
        fields, records = _read_generated_csv(path)
        if not fields:
            continue
        if 'state_origin' not in fields:
            fields.append('state_origin')
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            writer.writerows(dict(row, state_origin='projected_opm') for row in records)
    provenance = dict(state_origin='projected_opm', source_vgm=str(source.resolve()),
                      source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      projected_opm_vgm=str(target.resolve()),
                      projected_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                      source_chip_evidence='PSG/SCC; no native OPM claimed',
                      opm_pipeline='opm_conversion.convert', settings=performance.settings,
                      source_end_vgmticks=performance.source_end,
                      projected_opm_end_vgmticks=projection.source_end_vgmticks,
                      final_mdx_end_vgmticks=projection.end_projected_vgmticks,
                      max_abs_source_to_final_error_samples=max(map(abs, errors), default=0),
                      source_to_final_timing_bound_samples=12, mapping_csv=mapping.name)
    (folder / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    if provenance['max_abs_source_to_final_error_samples'] > 12:
        raise ValueError('Projected note clock exceeds the combined source timing bound')


def _convert(source, out, *, psg_gain=None, scc_gain=.125, title=None, psg_model='fm', pitch_policy=None,
             notation='structured', loops=True):
    if notation not in ('structured', 'registers'):
        raise ValueError('PSG/SCC OPM notation must be structured or registers')
    source, out = Path(source), Path(out)
    facts = source_facts(read_vgm_bytes(source))
    out.mkdir(parents=True, exist_ok=True)
    paths = parse_vgm(str(source), str(out), include_vgmticks=True, dump_loop=True)
    psg = build_psg(paths[2], str(out), stem=source.stem, dump_passes=True)
    scc = build_scc(paths[3], str(out), stem=source.stem, dump_passes=True)
    plan = project(psg, scc, psg_clock=facts['psg_clock'], scc_clock=facts['scc_clock'],
                   end_vgmticks=facts['end_vgmticks'], psg_gain=psg_gain, scc_gain=scc_gain,
                   psg_model=psg_model, pitch_policy=pitch_policy)
    plan.settings.update(ay_type=facts['ay_type'], ay_flags=facts['ay_flags'],
                         silent_opll_writes=facts['silent_opll_writes'], absent_scc_writes=facts['absent_scc_writes'])
    plan.dump(out, source.stem)
    mml = out / (source.stem + '.mdx.mml')
    title = title or source.stem + ' - PSG/SCC OPM (' + psg_model + ')'
    if notation == 'structured':
        from opm_performance import build_performance
        from opm_target_vgm import write_target_vgm
        from opm_conversion import convert as convert_opm
        performance = build_performance(plan)
        performance.dump(out, source.stem)
        folder = out / 'projected_opm'
        folder.mkdir(exist_ok=True)
        target = write_target_vgm(performance, folder / (source.stem + '.vgm'),
                                  mapping_csv=folder / (source.stem + '.source_map.csv'))
        native_mml, analysis, projection = convert_opm(target, folder, dump_passes=True, title=title, loops=loops)
        plan.structured_context = StructuredContext(performance, analysis, projection)
        _mark_projected_evidence(folder, source, target, performance, projection)
        text = native_mml.read_text(encoding='utf-8')
        text = '; PSG/SCC OPM target; PSG model=' + psg_model + '.\n; Musical onsets inferred from audibility; oscillator phase differs from the held baseline.\n' + text
        mml.write_text(text, encoding='utf-8')
    else:
        mml.write_text(plan.render(title), encoding='utf-8')
    return mml, plan



def convert(source, out, *, psg_gain=None, scc_gain=.125, title=None, psg_model='fm', pitch_policy=None,
            dump_passes=True, notation='structured', loops=True):
    """Keep native evidence on request; default standalone audit keeps all passes."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if dump_passes:
        return _convert(source, out, psg_gain=psg_gain, scc_gain=scc_gain, title=title,
                        psg_model=psg_model, pitch_policy=pitch_policy, notation=notation, loops=loops)
    with tempfile.TemporaryDirectory(prefix='psg-scc-opm-') as temp:
        mml, plan = _convert(source, temp, psg_gain=psg_gain, scc_gain=scc_gain, title=title,
                        psg_model=psg_model, pitch_policy=pitch_policy, notation=notation, loops=loops)
        result = out / mml.name
        shutil.copyfile(mml, result)
    return result, plan


