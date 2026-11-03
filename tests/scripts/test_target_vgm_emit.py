"""Deliverable target VGM (--emit-vgm): the projected OPM stream the
MML was built from, with bound PCM playbacks merged as MSM6258
streams, written beside the MML by the projected routes."""
from pathlib import Path
import json
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]

from types import SimpleNamespace

from msm6258 import analyze
from target_vgm_emit import emit_target_vgm
from vgm_timing import command_times


def fm_vgm(events, *, total, loop_tick=None, loop_samples=0):
    """A write_target_vgm-shaped FM stream: 0x40 header, then the
    (tick, payload) events serialized with 0x61 waits."""
    body = bytearray()
    cursor = 0
    loop_address = None
    for tick, payload in events:
        if loop_tick is not None and loop_address is None and tick >= loop_tick:
            gap = loop_tick - cursor
            if gap:
                body.extend(b'\x61' + struct.pack('<H', gap))
            cursor = loop_tick
            loop_address = 0x40 + len(body)
        gap = tick - cursor
        if gap:
            body.extend(b'\x61' + struct.pack('<H', gap))
        cursor = tick
        body.extend(payload)
    if total > cursor:
        body.extend(b'\x61' + struct.pack('<H', total - cursor))
    body.append(0x66)
    raw = bytearray(0x40)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 4, 0x40 + len(body) - 4)
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 0x18, total)
    struct.pack_into('<I', raw, 0x30, 4000000)
    if loop_address is not None:
        struct.pack_into('<I', raw, 0x1C, loop_address - 0x1C)
        struct.pack_into('<I', raw, 0x20, loop_samples)
    return bytes(raw) + bytes(body)


def fm_writes(raw):
    return [(event.vgmticks, raw[event.address + 1], raw[event.address + 2])
            for event in command_times(raw) if event.command == 0x54]


def bridge(playbacks, samples):
    return SimpleNamespace(
        samples=tuple(SimpleNamespace(sample_id=sid, encoded_bytes=data)
                      for sid, data in samples),
        playbacks=tuple(SimpleNamespace(
            playback_id=pid, sample_id=sid, start_vgmticks=start,
            end_vgmticks=end, clock_hz=8000000,
            rate_hz=__import__('fractions').Fraction(15625), pan=0,
            consumed_nibbles=consumed, nominal_nibbles=nominal,
            termination=termination)
            for pid, sid, start, end, consumed, nominal, termination
            in playbacks))


class EmitTargetVgmTests(unittest.TestCase):
    def test_fm_only_round_trip_and_loop(self):
        events = [(0, b'\x54\x08\x00'), (0, b'\x54\x20\x3c'),
                  (735, b'\x54\x28\x4d'), (2000, b'\x54\x08\x01'),
                  (9000, b'\x54\x28\x00')]
        source = fm_vgm(events, total=10000, loop_tick=2000,
                        loop_samples=8000)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'song.target.vgm'
            summary = emit_target_vgm(
                self._write(temp, source), out)
            raw = out.read_bytes()
        self.assertEqual(fm_writes(raw), fm_writes(source))
        self.assertEqual(struct.unpack_from('<I', raw, 8)[0], 0x171)
        self.assertEqual(struct.unpack_from('<I', raw, 0x18)[0], 10000)
        self.assertEqual(struct.unpack_from('<I', raw, 0x90)[0], 0)
        self.assertTrue(summary['loop_preserved'])
        expanded = list(command_times(raw, loop_count=2))
        end = max(e.vgmticks + e.wait_samples for e in expanded)
        self.assertEqual(end, 10000 + 8000)

    def test_pcm_merge_analyzes_clean(self):
        events = [(0, b'\x54\x08\x00'), (500, b'\x54\x28\x4d')]
        source = fm_vgm(events, total=10000)
        data = bytes(range(200))
        analysis = bridge(
            [(0, 0, 1000, 2129, 400, 400, 'sample_end'),
             (1, 0, 5000, 5100, 100, 400, 'disabled')],
            [(0, data)])
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'song.target.vgm'
            summary = emit_target_vgm(
                self._write(temp, source), out, pcm_analysis=analysis)
            raw = out.read_bytes()
            result = analyze(raw)
        self.assertEqual(summary['pcm_playbacks'], 2)
        self.assertEqual(summary['pcm_truncated'], 1)
        self.assertEqual(struct.unpack_from('<I', raw, 0x90)[0], 8000000)
        self.assertEqual(raw[0x94], 6)
        self.assertEqual(fm_writes(raw), fm_writes(source))
        self.assertEqual(len(result.playbacks), 2)
        full = result.playbacks[0]
        self.assertEqual(full.start_vgmticks, 1000)
        self.assertEqual(full.supplied_bytes, 200)
        self.assertEqual(full.issues, ())
        cut = result.playbacks[1]
        self.assertEqual(cut.start_vgmticks, 5000)
        self.assertEqual(cut.termination, 'stop_control')

    def test_omitted_playbacks_are_excluded(self):
        events = [(0, b'\x54\x08\x00')]
        source = fm_vgm(events, total=10000)
        analysis = bridge(
            [(0, 0, 1000, 2129, 400, 400, 'sample_end'),
             (1, 0, 5000, 7129, 400, 400, 'sample_end')],
            [(0, bytes(range(200)))])
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'song.target.vgm'
            summary = emit_target_vgm(
                self._write(temp, source), out, pcm_analysis=analysis,
                omitted_playback_ids=frozenset({1}))
            result = analyze(out.read_bytes())
        self.assertEqual(summary['pcm_playbacks'], 1)
        self.assertEqual(len(result.playbacks), 1)

    @staticmethod
    def _write(temp, source):
        path = Path(temp) / 'projected.vgm'
        path.write_bytes(source)
        return path


def nes_vgm(body):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 4, 256 + len(body) + 1 - 4)
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    struct.pack_into('<I', raw, 0x84, 1789773)  # NES APU clock
    return bytes(raw) + body + b'\x66'


PULSE_NOTE = bytes.fromhex('b4 00 9f b4 02 fd b4 03 f8 62 62 b4 00 80 62')

PDX_STUB = (
    '#!/usr/bin/env python3\n'
    'import struct, sys\n'
    'from pathlib import Path\n'
    'args = sys.argv[1:]\n'
    'if args[0] == "--build-pdx":\n'
    '    manifest, pdx = Path(args[1]), Path(args[2])\n'
    '    rows = []\n'
    '    for line in manifest.read_text().splitlines()[1:]:\n'
    '        if line.strip():\n'
    '            sid, bank, slot, file = line.split("\\t")\n'
    '            rows.append((int(slot), (manifest.parent / file).read_bytes()))\n'
    '    table, payload, offset = bytearray(768), bytearray(), 768\n'
    '    for slot, data in sorted(rows):\n'
    '        struct.pack_into(">II", table, slot * 8, offset, len(data))\n'
    '        payload += data; offset += len(data)\n'
    '    pdx.write_bytes(bytes(table) + bytes(payload))\n'
    'else:\n'
    '    offsets = [0] + [34 + 2 * i for i in range(16)]\n'
    '    body = b"".join(b"\\xe8\\x00" if i == 0 else b"\\xf1\\x00" for i in range(16))\n'
    '    Path(args[3]).write_bytes(b"STUB\\r\\n\\x1a\\x00" + struct.pack(">17H", *offsets) + body)\n')


class EmitVgmCliTests(unittest.TestCase):
    def test_nes_cli_emits_target_vgm_with_dpcm_stream(self):
        block = (b'\x67\x66\xc2' + struct.pack('<I', 2 + 129)
                 + struct.pack('<H', 0xc000) + b'\xff' * 129)
        trigger = bytes.fromhex(
            'b4 12 00 b4 13 08 b4 10 0f b4 15 10') + b'\x62' * 6
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'nes.vgm'
            source.write_bytes(nes_vgm(block + PULSE_NOTE + trigger))
            helper = root / 'helper.py'
            helper.write_text(PDX_STUB)
            helper.chmod(0o755)
            outdir = root / 'out'
            run = subprocess.run(
                [sys.executable, str(ROOT / 'vgm2mml.py'), str(source),
                 '--outdir', str(outdir), '--force', '--emit-vgm',
                 '--pcm-generator', str(helper)],
                capture_output=True, text=True, timeout=300)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('Target VGM:', run.stdout)
            target = outdir / 'nes.target.vgm'
            self.assertTrue(target.is_file())
            report = json.loads((outdir / 'nes.conversion.json').read_text())
            summary = report['projection_settings']['target_vgm']
            self.assertEqual(summary['pcm_playbacks'], 1)
            raw = target.read_bytes()
            # The single-blip fixture's projected FM stream is only
            # waits; FM round-trip equality is covered by the unit
            # tests above. Here the stream merge itself is the point.
            commands = {event.command
                        for event in command_times(raw)}
            self.assertIn(0x93, commands)
            result = analyze(raw)
            self.assertEqual(len(result.playbacks), 1)
            self.assertNotIn('unsupported_adpcm3',
                             result.playbacks[0].issues)


if __name__ == '__main__':
    unittest.main()
