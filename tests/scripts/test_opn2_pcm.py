"""OPN2 (YM2612) S3: DAC write runs and DAC streams -> MSM6258 bridge."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'py'))

from opn2_pcm import dac_timeline, dac_waveform, project_dac
from opn2_source import build_analysis

OPN2_CLOCK = 7670454


def build_vgm(body):
    header = bytearray(0x100)
    header[0:4] = b'Vgm '
    struct.pack_into('<I', header, 0x04, 0x100 + len(body) - 4)
    struct.pack_into('<I', header, 0x08, 0x171)
    struct.pack_into('<I', header, 0x0c, 3579545)
    struct.pack_into('<I', header, 0x2c, OPN2_CLOCK)
    struct.pack_into('<I', header, 0x34, 0x100 - 0x34)
    return bytes(header) + bytes(body)


def analyze(body):
    tmp = tempfile.mkdtemp()
    source = Path(tmp) / 'song.vgm'
    source.write_bytes(build_vgm(body))
    analysis, _clock, _end, events = build_analysis(source, Path(tmp) / 'trace.csv')
    return source, analysis, events


def write_run(body, values, wait=0x73):
    body.extend((0x52, 0x2b, 0x80))
    for value in values:
        body.extend((0x52, 0x2a, value))
        body.append(wait)
    body.extend((0x52, 0x2b, 0x00))


class Opn2DacWriteRunTests(unittest.TestCase):
    def test_write_run_becomes_one_playback(self):
        body = bytearray()
        write_run(body, [0x80, 0x90, 0xa0, 0xb0])
        body.append(0x66)
        source, analysis, events = analyze(bytes(body))
        result = project_dac(source.read_bytes(), events, analysis)
        self.assertEqual(result.dac_stats['write_bytes'], 4)
        self.assertEqual(len(result.playbacks), 1)
        self.assertEqual(len(result.samples), 1)
        self.assertEqual(result.playbacks[0].termination, 'song_end')

    def test_dac_waveform_spans_match_bridge_playbacks(self):
        body = bytearray()
        write_run(body, [0xa0, 0x60, 0xc0, 0x40])
        body.extend((0x61, 0xe8, 0x03))
        write_run(body, [0xa0, 0x60, 0xc0, 0x40])
        body.append(0x66)
        source, analysis, events = analyze(bytes(body))
        raw = source.read_bytes()
        wave, _issues, _stats, spans = dac_waveform(raw, events, analysis)
        result = project_dac(raw, events, analysis)
        self.assertEqual([(start, stop) for start, stop, *_ in spans],
                         [(p.start_vgmticks, p.end_vgmticks)
                          for p in result.playbacks])
        for start, stop, *_ in spans:
            self.assertTrue(any(v != 0 for v in wave[start:stop]))
        outside = [v for i, v in enumerate(wave)
                   if not any(s <= i < e for s, e, *_ in spans)]
        self.assertTrue(all(v == 0 for v in outside))

    def test_gap_splits_and_identical_runs_dedupe(self):
        body = bytearray()
        write_run(body, [0x80, 0x90, 0xa0, 0xb0])
        body.extend((0x61, 0xe8, 0x03))  # 1000 samples of silence
        write_run(body, [0x80, 0x90, 0xa0, 0xb0])
        body.append(0x66)
        source, analysis, events = analyze(bytes(body))
        result = project_dac(source.read_bytes(), events, analysis)
        self.assertEqual(len(result.playbacks), 2)
        self.assertEqual(len(result.samples), 1)
        self.assertEqual(result.playbacks[0].sample_id, result.playbacks[1].sample_id)
        self.assertEqual(result.playbacks[0].termination, 'gap')

    def test_writes_while_disabled_are_dropped(self):
        body = bytearray()
        body.extend((0x52, 0x2a, 0x80, 0x52, 0x2a, 0x81))  # DAC still disabled
        body.append(0x62)  # one frame passes before the enable write
        write_run(body, [0x90])
        body.append(0x66)
        source, analysis, events = analyze(bytes(body))
        timeline, _issues, stats = dac_timeline(source.read_bytes(), events, analysis)
        self.assertEqual(stats['write_bytes_dropped_disabled'], 2)
        self.assertEqual([row[1] for row in timeline], [0x90])


def stream_body(payload, commands):
    body = bytearray()
    body.extend((0x67, 0x66, 0x00))
    body.extend(struct.pack('<I', len(payload)))
    body.extend(payload)
    body.extend(commands)
    body.append(0x66)
    return bytes(body)


def stream_setup():
    out = bytearray()
    out.extend((0x90, 0x00, 0x02, 0x00, 0x2a))       # stream 0 -> YM2612 DAC
    out.extend((0x91, 0x00, 0x00, 0x01, 0x00))       # bank 0, step 1, base 0
    out.extend((0x52, 0x2b, 0x80))                   # DAC enable
    return out


class Opn2DacStreamTests(unittest.TestCase):
    def test_manual_plays_and_seek_decode_block_bytes(self):
        commands = stream_setup()
        commands.extend((0x95, 0x00, 0x00, 0x00, 0x00))  # fast start, block 0
        commands.extend((0x83, 0x83, 0x83))              # play 3 bytes
        commands.extend((0xe0, 0x00, 0x00, 0x00, 0x00))  # seek to 0
        commands.append(0x81)                            # play 1 more
        commands.extend((0x52, 0x2b, 0x00))
        source, analysis, events = analyze(
            stream_body(bytes((0x80, 0x90, 0xa0, 0xb0)), commands))
        timeline, _issues, stats = dac_timeline(source.read_bytes(), events, analysis)
        self.assertEqual(stats['manual_bytes'], 4)
        self.assertEqual([row[1] for row in timeline], [0x80, 0x90, 0xa0, 0x80])
        result = project_dac(source.read_bytes(), events, analysis)
        self.assertEqual(len(result.playbacks), 1)

    def test_setupless_seek_play_binds_implicitly(self):
        commands = bytearray()
        commands.extend((0x52, 0x2b, 0x80))              # DAC enable only
        commands.extend((0xe0, 0x00, 0x00, 0x00, 0x00))  # seek to 0
        commands.extend((0x83, 0x83))                    # play 2 bytes
        commands.extend((0x52, 0x2b, 0x00))
        source, analysis, events = analyze(
            stream_body(bytes((0x80, 0x90, 0xa0)), commands))
        timeline, _issues, stats = dac_timeline(source.read_bytes(), events, analysis)
        self.assertTrue(stats['implicit_stream'])
        self.assertEqual([row[1] for row in timeline], [0x80, 0x90])

    def test_same_tick_burst_collapses_and_drops_as_subsample(self):
        commands = bytearray()
        commands.extend((0x52, 0x2b, 0x80))              # DAC enable
        commands.extend((0xe0, 0x00, 0x00, 0x00, 0x00))  # seek to 0
        commands.extend([0x80] * 24)                     # 24 plays, all wait 0
        commands.append(0x62)
        source, analysis, events = analyze(
            stream_body(bytes(range(0x70, 0x70 + 24)), commands))
        result = project_dac(source.read_bytes(), events, analysis)
        self.assertEqual(result.dac_stats['manual_bytes'], 24)
        self.assertEqual(result.dac_stats['collapsed_same_tick_bytes'], 23)
        self.assertEqual(result.dac_stats['subsample_runs_dropped'], 1)
        self.assertEqual(len(result.playbacks), 0)

    def test_autonomous_start_expands_at_stream_frequency(self):
        commands = stream_setup()
        commands.extend((0x92, 0x00))                    # set frequency 44100
        commands.extend(struct.pack('<I', 44100))
        commands.extend((0x93, 0x00))                    # start: offset 0,
        commands.extend(struct.pack('<I', 0))            # mode 1, length 4
        commands.append(0x01)
        commands.extend(struct.pack('<I', 4))
        commands.extend((0x61, 0x64, 0x00))              # wait 100 samples
        commands.extend((0x52, 0x2b, 0x00))
        source, analysis, events = analyze(
            stream_body(bytes((0x70, 0x80, 0x90, 0xa0)), commands))
        timeline, _issues, stats = dac_timeline(source.read_bytes(), events, analysis)
        self.assertEqual(stats['autonomous_bytes'], 4)
        self.assertEqual([row[1] for row in timeline], [0x70, 0x80, 0x90, 0xa0])
        ticks = [row[0] for row in timeline]
        self.assertEqual(ticks, sorted(ticks))
        self.assertEqual(ticks[-1] - ticks[0], 3)


if __name__ == '__main__':
    unittest.main()
