"""PSG/SCC to OPM target orchestration, shared by the CLI and diagnostics."""
import shutil
import tempfile
from pathlib import Path
from vgm_io import read_vgm_bytes, read_vgm_header
from vgm_timing import command_times
from vgm_reader import parse_vgm
from psg import build_segments as build_psg
from scc import build_segments as build_scc
from psg_scc_opm import project

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


def _convert(source, out, *, psg_gain=None, scc_gain=.125, title=None, psg_model='fm', pitch_policy=None):
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
    mml.write_text(plan.render(title or source.stem + ' - PSG/SCC OPM (' + psg_model + ')'), encoding='utf-8')
    return mml, plan



def convert(source, out, *, psg_gain=None, scc_gain=.125, title=None, psg_model='fm', pitch_policy=None, dump_passes=True):
    """Keep native evidence on request; default standalone audit keeps all passes."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if dump_passes:
        return _convert(source, out, psg_gain=psg_gain, scc_gain=scc_gain, title=title,
                        psg_model=psg_model, pitch_policy=pitch_policy)
    with tempfile.TemporaryDirectory(prefix='psg-scc-opm-') as temp:
        mml, plan = _convert(source, temp, psg_gain=psg_gain, scc_gain=scc_gain, title=title,
                        psg_model=psg_model, pitch_policy=pitch_policy)
        result = out / mml.name
        shutil.copyfile(mml, result)
    return result, plan


