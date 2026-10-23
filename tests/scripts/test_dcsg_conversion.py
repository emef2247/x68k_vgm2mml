"""Public authored DCSG canonical-route and structured-backend integration."""
import csv
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
from conversion_config import inspect_source, select_mdx_route
from dcsg_conversion import convert
from test_dcsg_opm import vgm, tone, level, noise, write, wait


class DcsgConversionTests(unittest.TestCase):
    def test_inventory_uses_commands_not_unused_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'AUTH.vgm'
            src.write_bytes(vgm(tone(0, 200) + level(0) + wait() + level(0, 15)))
            self.assertEqual(select_mdx_route(inspect_source(src)), 'dcsg-to-opm')
            src.write_bytes(vgm(wait()))
            usage = inspect_source(src)
            self.assertIn('dcsg', usage['unused_declarations'])
            with self.assertRaisesRegex(ValueError, 'no supported chip commands'):
                select_mdx_route(usage)

    def test_canonical_default_preserves_source_and_dumps_original_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root / 'AUTH.vgm'; out = root / 'out'
            raw = vgm(tone(0, 200) + level(0) + wait(4410) + level(0, 4)
                      + wait(4410) + level(0, 15) + wait(4410))
            src.write_bytes(raw)
            result = subprocess.run([sys.executable, str(ROOT/'vgm2mml.py'),str(src),
                '--outdir',str(out),'--dump-passes','--no-song-loop'],capture_output=True,text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(src.read_bytes(), raw)
            report = json.loads((out/'AUTH.conversion.json').read_text())
            self.assertEqual(report['chip_projection'], 'dcsg-to-opm')
            self.assertEqual(report['fm_state_ms'], 24)
            state = json.loads((out/'AUTH.fm.short_states.json').read_text())
            self.assertEqual(state['threshold_samples'], 1058)
            self.assertTrue((out/'AUTH.dcsg.segments.csv').is_file())
            self.assertTrue((out/'AUTH.mdx.mml').is_file())
            with (out/'projected_opm/AUTH.source_map.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(rows)
            self.assertTrue(all(r['vgmticks']==r['target_vgmticks'] for r in rows))
            self.assertTrue(all(r['source_chip']=='dcsg' for r in rows))
            provenance=json.loads((out/'projected_opm/provenance.json').read_text())
            self.assertEqual(provenance['source_chip_evidence'],'DCSG; no native OPM claimed')

    def test_song_loop_replay_keeps_latch_and_inspectable_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root/'AUTH.vgm'; out = root/'out'
            prefix = tone(0,200)+level(0)+wait()
            # Data-only volume changes depend on the latch at the loop entry.
            body = write(3)+wait()+write(0)+wait()
            src.write_bytes(vgm(prefix+body,loop=len(prefix)))
            mml, plan = convert(src,out)
            with (out/'AUTH.dcsg.writes.csv').open() as stream:
                rows=list(csv.DictReader(stream))
            replay=[r for r in rows if r['loop_iteration']=='1']
            self.assertTrue(replay)
            self.assertTrue(all(r['register']=='1' for r in replay))
            self.assertIn('L',mml.read_text())
            self.assertEqual(plan.source_end, 5*4410)

    def test_force_noise_omission_still_renders_remaining_tones(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'AUTH.vgm'
            src.write_bytes(vgm(tone(0,200)+level(0)+noise(0)+wait()+level(0,15)))
            with self.assertRaisesRegex(ValueError,'periodic_noise'):
                convert(src,root/'strict',song_loop=False)
            mml,plan=convert(src,root/'force',force=True,song_loop=False)
            self.assertTrue(plan.settings['forced_omissions'])
            self.assertTrue(any(w.register==8 and w.target_ch==0 and w.data&0x78 for w in plan.writes))
            self.assertTrue(mml.is_file())


if __name__=='__main__':unittest.main()
