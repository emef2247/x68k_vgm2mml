"""NES DPCM -> MSM6258 ADPCM bridge (py/nesapu_pcm.py).

The bridge decodes covered DPCM samples from the NES analysis,
resamples and encodes them as MSM6258 ADPCM assets, and turns each
trigger into an independent PDX playback on the source timeline.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
from nesapu import analyze
from nesapu_pcm import covered_event_indexes, project


def nes_vgm(body):
    raw = bytearray(256)
    raw[:4] = b'Vgm '
    struct.pack_into('<I', raw, 4, 256 + len(body) + 1 - 4)
    struct.pack_into('<I', raw, 8, 0x171)
    struct.pack_into('<I', raw, 0x34, 256 - 0x34)
    struct.pack_into('<I', raw, 0x84, 1789773)  # NES APU clock
    return bytes(raw) + body + b'\x66'


def write(register, value):
    return bytes((0xb4, register, value))


def ram_block(payload, start=0xc000):
    return (b'\x67\x66\xc2' + struct.pack('<I', 2 + len(payload))
            + struct.pack('<H', start) + payload)


# 129 bytes of 0xff: the DMC counter climbs by 2 per bit and saturates.
SAMPLE = b'\xff' * 129
TRIGGER = (write(18, 0x00) + write(19, 0x08) + write(16, 0x0f)
           + write(21, 0x10))
WAITS = b'\x62' * 6  # 4410 ticks; the sample needs ~1373


class NesapuPcmTests(unittest.TestCase):
    def test_covered_trigger_becomes_an_adpcm_playback(self):
        raw = nes_vgm(ram_block(SAMPLE) + TRIGGER + WAITS)
        trace = analyze(raw)
        self.assertEqual(covered_event_indexes(trace, raw), (0,))
        analysis = project(trace, source_raw=raw, gain=1.25)
        self.assertEqual(len(analysis.samples), 1)
        sample = analysis.samples[0]
        self.assertEqual(sample.codec, 'msm6258-adpcm4-low-first')
        self.assertTrue(sample.encoded_bytes)
        self.assertEqual(len(analysis.playbacks), 1)
        playback = analysis.playbacks[0]
        self.assertEqual(playback.start_vgmticks, 0)
        self.assertEqual(playback.termination, 'sample_end')
        self.assertGreater(playback.end_vgmticks, 1000)
        self.assertLess(playback.end_vgmticks, 2000)
        self.assertEqual(playback.sample_id, 0)
        self.assertEqual(analysis.dpcm_stats['unique_samples'], 1)

    def test_decoded_waveform_follows_the_dmc_counter(self):
        import io
        import wave
        from pcm_block_wav import _wav_bytes
        raw = nes_vgm(ram_block(SAMPLE) + TRIGGER + WAITS)
        analysis = project(analyze(raw), source_raw=raw)
        encoded = analysis.samples[0].encoded_bytes
        handle = wave.open(io.BytesIO(_wav_bytes(encoded, 15625)))
        frames = handle.readframes(handle.getnframes())
        values = struct.unpack(f'<{len(frames) // 2}h', frames)
        quarter = len(values) // 4
        self.assertGreater(max(values), 5000)
        self.assertGreater(sum(values[-quarter:]) / quarter,
                           sum(values[:quarter]) / quarter)

    def test_uncovered_trigger_stays_silent_and_is_recorded(self):
        raw = nes_vgm(TRIGGER + WAITS)
        trace = analyze(raw)
        self.assertEqual(covered_event_indexes(trace, raw), ())
        analysis = project(trace, source_raw=raw)
        self.assertEqual(analysis.playbacks, ())
        self.assertEqual(analysis.dpcm_stats['uncovered_events'], 1)
        self.assertTrue(any(issue.code
                            == 'nes_dpcm_trigger_without_sample_data'
                            for issue in analysis.issues))

    def test_loop_replay_duplicates_body_playbacks(self):
        # The trigger sounds after two waits, inside the loop body.
        raw = nes_vgm(ram_block(SAMPLE) + b'\x62\x62' + TRIGGER + WAITS)
        trace = analyze(raw)
        end = trace.source_end_vgmticks
        analysis = project(trace, source_raw=raw, loop_point=735,
                           loop_start=end, expanded_end=end + (end - 735),
                           loop_count=2)
        self.assertEqual(analysis.source_end_vgmticks, end + (end - 735))
        self.assertEqual(analysis.source_loop_vgmticks, end)
        starts = [p.start_vgmticks for p in analysis.playbacks]
        self.assertEqual(len(starts), 2)
        self.assertEqual(starts[1] - starts[0], end - 735)

    def test_looped_sample_is_baked_to_its_gate(self):
        # Loop flag set (0x40) at the fastest rate; a $4015 write
        # clearing bit 4 cuts the gate after 2940 ticks, about 2.1
        # natural passes of the sample.
        body = (ram_block(SAMPLE)
                + write(18, 0x00) + write(19, 0x08) + write(16, 0x4f)
                + write(21, 0x10) + b'\x62' * 4 + write(21, 0x00)
                + b'\x62' * 2)
        raw = nes_vgm(body)
        trace = analyze(raw)
        analysis = project(trace, source_raw=raw)
        self.assertEqual(len(analysis.playbacks), 1)
        playback = analysis.playbacks[0]
        self.assertEqual(playback.termination, 'disabled')
        self.assertEqual(playback.end_vgmticks, 2940)
        row = analysis.dpcm_event_rows[0]
        self.assertGreater(row['repetitions'], 1)
        # The baked asset covers the gate (whole repetitions only, so
        # it may overhang by less than one pass).
        span = round(2940 / 44100 * 15625)
        self.assertGreaterEqual(playback.nominal_nibbles, span)
        self.assertLess(playback.nominal_nibbles, span + 500)


if __name__ == '__main__':
    unittest.main()
