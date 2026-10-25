"""Generate original C140 fixtures from arithmetic waveforms, never game ROMs."""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/scripts'))
from test_c140 import make_vgm,voice,write,wait
from test_opm_performed_runs import setup as fm_setup
from test_opm_mdx import write as fm_write


def cases():
    yield 'linear_bank',make_vgm(voice(end=64)+wait(1000)+voice(level=120,end=64)+wait(1000)),dict(chip_type=0,clock_raw=12288000)
    yield 'system21_controls',make_vgm(voice(mode=0x98,loop=16)+wait(500)+write(1,100)+wait(500)+write(2,0)+write(3,0)+wait(100)+write(2,0x80)+wait(500)+write(5,0)+wait(500),chip_type=1),dict(chip_type=1,clock_raw=12288000)
    raw=bytearray(make_vgm(fm_setup()+fm_write(8,120)+voice(mode=0x90,loop=16)+wait(2000)+write(5,0)+fm_write(8,0)+wait(1000),clock=21390))
    struct.pack_into('<I',raw,0x30,4000000)
    yield 'opm_legacy_clock',bytes(raw),dict(chip_type=0,clock_raw=21390,clock_hz=12288000)


def main():
    for name,raw,facts in cases():
        folder=ROOT/'tests/fixtures/public/opm_c140'/name
        folder.mkdir(parents=True,exist_ok=True)
        (folder/(name+'.vgm')).write_bytes(raw)
        (folder/'source.json').write_text(json.dumps(dict(origin='Project-authored arithmetic waveform and register sequence; no ROM-derived content',sha256=hashlib.sha256(raw).hexdigest(),**facts),indent=2)+'\n')
        print(name,len(raw))


if __name__=='__main__':main()
