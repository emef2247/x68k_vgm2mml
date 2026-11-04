"""Tests for scripts/mdx_layout.py using a toy generator stub.

The stub compiles MML to a stock-layout MDX whose per-track segment is
the track's own text bytes, so segment preservation through subset
compiles and reassembly can be checked exactly without the real
compiler. It also enforces the stock offset limit, like mmlx does.
"""
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))

import mdx_layout  # noqa: E402

STUB = r'''
import struct, sys
from pathlib import Path

def parse_mdx(data):
    marker = data.index(0x1A)
    base = data.index(0, marker + 1) + 1
    tone_off = struct.unpack('>H', data[base:base + 2])[0]
    first = struct.unpack('>H', data[base + 2:base + 4])[0]
    count = (first - 2) // 2
    words = struct.unpack(f'>{count + 1}H', data[base:base + 2 * (count + 1)])
    entries = list(words[1:])
    bounds = sorted({o for o in entries if o != 0xFFFF} | {tone_off})
    tone_end = min((b for b in bounds if b > tone_off), default=len(data) - base)
    segs = {}
    for idx, off in enumerate(entries):
        if off == 0xFFFF: continue
        end = min((b for b in bounds if b > off), default=len(data) - base)
        segs[idx] = data[base + off: base + end]
    return base, tone_off, entries, data[base + tone_off: base + tone_end], segs

def main():
    args = sys.argv[1:]
    pcm = args[0] == '--compile-pcm'
    if args[0] in ('--compile-only', '--compile-pcm'):
        text = Path(args[1]).read_text()
        tracks = {}
        for line in text.splitlines():
            if len(line) > 2 and line[1] == ' ' and 'A' <= line[0] <= 'P':
                tracks.setdefault(line[0], []).append(line)
        extended = pcm or any(ord(l) - 65 >= 9 for l in tracks)
        count = 16 if extended else 9
        tone = bytes([7]) * 27 * 2
        segs = {}
        for i in range(count):
            letter = chr(65 + i)
            if letter in tracks:
                raw = ('\n'.join(tracks[letter]) + '\n').encode()
                segs[i] = bytes([ord(letter)]) * (len(raw) // 2)
            else:
                segs[i] = b'\xf1\x00'
        if pcm:
            segs[8] = bytes([0x99]) * 400  # plan-built PCM track (index 8)
        header = 2 + 2 * count
        pos = header
        offsets = {}
        for i in range(count):
            offsets[i] = pos
            if pos > 0xFFFE:
                print(f'MDX track {i} offset exceeds the maximum 0xfffe', file=sys.stderr)
                return 1
            pos += len(segs[i])
        words = [pos] + [offsets[i] for i in range(count)]
        out = bytearray(b'Title\r\n\x1a\0')
        out += struct.pack(f'>{len(words)}H', *words)
        for i in range(count):
            out += segs[i]
        out += tone
        Path(args[3] if pcm else args[2]).write_bytes(bytes(out))
        return 0
    data = Path(args[1]).read_bytes()
    base, tone_off, entries, tone, segs = parse_mdx(data)
    if args[0] == '--inspect-mdx':
        Path(args[2]).write_text('tone\n' + tone.hex() + '\n')
        return 0
    if args[0] == '--inspect-commands':
        lines = ['track,index,kind,opcode,operands,ticks']
        for idx in sorted(segs):
            label = chr(65 + idx) if idx < 8 else chr(ord('P') + idx - 8)
            for j, b in enumerate(segs[idx]):
                kind = 'PcmMode' if b == 0xE8 else f'B{b:02x}'
                lines.append(f'{label},{j},{kind},{b:02x},,0')
        Path(args[2]).write_text('\n'.join(lines) + '\n')
        return 0
    return 2

sys.exit(main())
'''


def make_mml(sizes):
    lines = ['#title "Stub"', '@0 = { 1 2 3 }']
    for letter, size in sizes.items():
        body = 'x' * (size - 3)
        lines.append(f'{letter} {body}')
    return '\n'.join(lines) + '\n'


class MdxLayoutTest(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='mdx-layout-test-'))
        self.generator = self.work / 'stub_generator.py'
        self.generator.write_text('#!/usr/bin/env python3\n' + STUB)
        self.generator.chmod(0o755)

    def assemble(self, sizes, name='song'):
        mml = self.work / f'{name}.mml'
        mml.write_text(make_mml(sizes))
        out = self.work / f'{name}.mdx'
        report = mdx_layout.assemble_mdx(mml, None, out,
                                         generator=self.generator, timeout=60)
        return out, report

    def test_split_and_plan(self):
        head, tracks = mdx_layout.split_mml(make_mml({'A': 100, 'B': 200}))
        self.assertEqual(sorted(tracks), ['A', 'B'])
        self.assertTrue(any('#title' in line for line in head))
        subsets = mdx_layout.plan_subsets({'A': ['x' * 60_000], 'B': ['y' * 60_000],
                                           'C': ['z' * 10]})
        self.assertEqual(sorted(l for s in subsets for l in s), ['A', 'B', 'C'])
        for subset in subsets:
            total = sum(len(line) + 1 for letter in subset
                        for line in {'A': ['x' * 60_000], 'B': ['y' * 60_000],
                                     'C': ['z' * 10]}[letter])
            self.assertLessEqual(total, mdx_layout.SUBSET_MML_CAP)

    def test_placement_rescues_overflow(self):
        out, report = self.assemble({'A': 2_000, 'B': 40_000, 'C': 20_000, 'D': 20_000})
        self.assertTrue(report['layout_fallback'])
        self.assertLessEqual(report['max_start_offset'], 0xFFFE)
        _, _, entries, _, segments = mdx_layout._parse_mdx(out.read_bytes())
        # Segments survive byte-exact (as the stub defined them).
        self.assertEqual(len(segments[1]), 20_000)   # B: half its MML size
        self.assertEqual(len(segments[2]), 10_000)   # C
        # Largest track (B) starts last among tracks.
        self.assertEqual(entries[1], max(entries))

    def test_largest_a_stays_first_and_fits(self):
        out, report = self.assemble({'A': 60_000, 'B': 30_000, 'C': 30_000}, name='big_a')
        _, _, entries, _, _ = mdx_layout._parse_mdx(out.read_bytes())
        # A must stay physically first: parsers derive the track count
        # from its offset. The rescue still fits because the binding
        # start is total - largest_non_A.
        self.assertEqual(entries[0], min(entries))
        self.assertLessEqual(report['max_start_offset'], 0xFFFE)

    def test_unrescuable_raises(self):
        mml = self.work / 'hopeless.mml'
        mml.write_text(make_mml({'A': 2_000, 'B': 100_000, 'C': 100_000, 'D': 100_000}))
        with self.assertRaises(mdx_layout.LayoutError):
            mdx_layout.assemble_mdx(mml, None, self.work / 'hopeless.mdx',
                                    generator=self.generator, timeout=60)

    def test_pcm_route_carries_plan_track(self):
        mml = self.work / 'pcm_song.mml'
        mml.write_text(make_mml({'A': 2_000, 'B': 40_000, 'C': 20_000, 'D': 20_000}))
        manifest = self.work / 'manifest.tsv'
        manifest.write_text('dummy\n')
        out = self.work / 'pcm_song.mdx'
        report = mdx_layout.assemble_pcm_mdx(mml, manifest, out,
                                             generator=self.generator, timeout=60)
        self.assertTrue(report['layout_fallback'])
        _, _, entries, _, segments = mdx_layout._parse_mdx(out.read_bytes())
        # The plan-built PCM segment (index 8) survives byte-exact.
        self.assertEqual(segments[8], bytes([0x99]) * 400)
        self.assertEqual(entries[1], max(entries))  # B (largest FM) last


if __name__ == '__main__':
    unittest.main()
