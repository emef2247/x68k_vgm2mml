"""Optional authored comparisons against pinned independent MSM6295 C sources.

Install explicitly with scripts/msm6295_reference.py --setup. Tests never fetch
sources or inspect private fixtures by themselves.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "py"), str(ROOT / "scripts")]
from msm6295_reference import LIBRARY, Reference, metadata


def authored_rom():
    rom = bytearray(0x500)
    for sample, start, length in ((1, 0x400, 32), (2, 0x420, 48)):
        base = sample * 8
        rom[base:base + 3] = start.to_bytes(3, "big")
        rom[base + 3:base + 6] = (start + length - 1).to_bytes(3, "big")
        for i in range(length):
            rom[start + i] = (i * 37 + sample * 29) & 255
    return bytes(rom)


def authored_vgm(events, end, *, clock=5821200, pin7=1, loop_tick=None):
    rom = authored_rom()
    block = b"\x67\x66\x8b" + struct.pack("<III", len(rom) + 8, len(rom), 0) + rom
    body = bytearray(block)
    tick = 0
    loop_address = None
    scheduled = list(events)
    if loop_tick is not None:
        scheduled.append((loop_tick, None))
    # A marker at an otherwise equal tick precedes writes and changes no source
    # state; this controls the exact beginning of the repeated authored region.
    scheduled.sort(key=lambda x: (x[0], x[1] is not None))
    for at, value in scheduled:
        if at < tick:
            raise ValueError("unordered authored events")
        if at > tick:
            body += b"\x61" + struct.pack("<H", at - tick)
        tick = at
        if value is None:
            loop_address = 0x100 + len(body)
        else:
            body += bytes((0xb8, 0, value))
    if end > tick:
        body += b"\x61" + struct.pack("<H", end - tick)
    body += b"\x66"
    header = bytearray(0x100)
    header[:4] = b"Vgm "
    struct.pack_into("<I", header, 4, len(header) + len(body) - 4)
    struct.pack_into("<I", header, 8, 0x171)
    struct.pack_into("<I", header, 0x34, 0x100 - 0x34)
    struct.pack_into("<I", header, 0x98, clock | (0x80000000 if pin7 else 0))
    if loop_address is not None:
        struct.pack_into("<I", header, 0x1c, loop_address - 0x1c)
    return bytes(header + body)


def _trunc_div(value, divisor):
    return (abs(value) // divisor) * (-1 if value < 0 else 1)


def compare_case(name, events, end, *, clock=5821200, pin7=1, loop_tick=None, loops=1):
    from msm6295 import analyze
    from msm6295_bank import interpret, decode_adpcm
    trace = analyze(authored_vgm(events, end, clock=clock, pin7=pin7, loop_tick=loop_tick), loop_count=loops)
    native = interpret(trace)
    reference = Reference(authored_rom(), clock, pin7)
    rate = reference.rate()
    if native.rate_hz != rate:
        raise AssertionError(f"{name}: reference native rate differs")
    volume = (32, 22, 16, 11, 8, 6, 4, 3, 2, 0, 0, 0, 0, 0, 0, 0)
    decoded = {}
    for sample in native.assets:
        decoded[sample.sample_id] = decode_adpcm(sample.payload)
    ordered = sorted(trace.writes, key=lambda write: write.event_id)
    cursor = 0
    stop = -(-trace.source_end_vgmticks * rate // 44100)
    try:
        for frame in range(stop):
            while cursor < len(ordered) and -(-ordered[cursor].vgmticks * rate // 44100) <= frame:
                write = ordered[cursor]
                reference.write(write.register, write.value)
                cursor += 1
            actual = reference.frame()
            expected = 0
            sounding = {}
            for playback in native.playbacks:
                if playback.start_frame <= frame < playback.end_frame:
                    wave = decoded[playback.sample_id]
                    index = frame - playback.start_frame
                    expected += _trunc_div(wave[index] * volume[playback.attenuation], 32)
                    sounding[playback.source_channel] = (playback, index)
            if actual != (expected, expected):
                raise AssertionError(f"{name} frame {frame}: PCM {actual} != {(expected, expected)}")
            for channel in range(4):
                state = reference.state(channel)
                if channel in sounding:
                    playback, index = sounding[channel]
                    if state[1] != index + 1:
                        raise AssertionError(f"{name} frame {frame}: channel{channel} cursor differs")
                    # Reconstruct full-scale PCM directly from the core signal:
                    # attenuation must never alter the native decoder itself.
                    if state[4] * 16 != decoded[playback.sample_id][index]:
                        raise AssertionError(f"{name} frame {frame}: decoder state differs")
                # Busy state after the emitted frame can end naturally; an
                # explicit stop at the next frame has not happened yet.
                wanted_busy = any(p.source_channel == channel and p.start_frame <= frame
                                  and frame + 1 < p.end_frame for p in native.playbacks)
                if bool(state[0]) != wanted_busy:
                    # A gate explicitly stopped at the next command remains
                    # busy after this frame; derive that case from termination.
                    ended_by_next_stop = any(p.source_channel == channel and p.start_frame <= frame
                        and p.end_frame == frame + 1 and p.termination != "natural_stop"
                        for p in native.playbacks)
                    if not (state[0] and ended_by_next_stop):
                        raise AssertionError(f"{name} frame {frame}: channel{channel} busy differs")
        return dict(name=name, frames=stop, playbacks=len(native.playbacks), native_pcm_and_cursor="exact")
    finally:
        reference.close()


def compare_authored_cases():
    metadata()
    cases = [
        ("inclusive_end_and_exact_restart", [(0, 0x81), (0, 0x10), (63, 0x82), (63, 0x10),
            (64, 0x82), (64, 0x10)], 170, {}),
        ("pending_high_bit_second_byte", [(0, 0x81), (1, 0x82), (15, 0x40),
            (18, 0x82), (18, 0x11)], 120, {}),
        ("pending_stop_byte_consumes_latch", [(0, 0x81), (0, 0x10), (2, 0x82),
            (3, 0x08), (20, 0x08), (23, 0x82), (23, 0x10)], 130, {}),
        ("busy_ignore_and_stop_masks", [(0, 0x81), (0, 0xf0), (2, 0x82), (2, 0x15),
            (17, 0x28), (22, 0x50), (25, 0x82), (25, 0x42)], 140, {}),
        ("invalid_request_consumes_latch", [(0, 0x83), (0, 0x10), (3, 0x81), (3, 0x10)], 90, {}),
        ("fractional_grid_pin7_high", [(1, 0x81), (2, 0x10), (139, 0x08),
            (146, 0x82), (146, 0x13)], 900, dict(clock=1000000, pin7=1)),
        ("fractional_grid_pin7_low", [(1, 0x81), (2, 0x10), (139, 0x08),
            (146, 0x82), (146, 0x13)], 900, dict(clock=1000000, pin7=0)),
        ("nonzero_loop_entry", [(0, 0x81), (0, 0x10), (15, 0x82), (15, 0x10)],
            20, dict(loop_tick=5, loops=2)),
    ]
    attenuation = [(tick, value) for code in range(16)
                   for tick, value in ((code * 64, 0x81), (code * 64, 0x10 | code))]
    cases.append(("all_attenuation_codes", attenuation, 16 * 64, {}))
    return [compare_case(name, events, end, **options) for name, events, end, options in cases]


@unittest.skipUnless(sys.platform.startswith("linux") and LIBRARY.exists(),
                     "optional WSL/Linux MSM6295 oracle: run scripts/msm6295_reference.py --setup")
class Msm6295ReferenceTests(unittest.TestCase):
    def test_decoder_samples_and_state_against_core(self):
        from msm6295_bank import Decoder, decode_adpcm
        reference = Reference(authored_rom())
        payload = bytes(range(256)) + bytes([0x77] * 80 + [0xff] * 80 + [0x00] * 40)
        nibbles = [n for value in payload for n in (value >> 4, value & 15)]
        try:
            signals, steps = reference.decode_nibbles(nibbles)
            decoder = Decoder()
            for at, nibble in enumerate(nibbles):
                self.assertEqual(decoder.clock(nibble), signals[at], at)
                self.assertEqual((decoder.signal, decoder.step), (signals[at], steps[at]), at)
            self.assertEqual(list(decode_adpcm(payload)), [signal * 16 for signal in signals])
        finally:
            reference.close()

    def test_authored_control_scheduler_against_core(self):
        cases = compare_authored_cases()
        self.assertEqual(len(cases), 9)
        self.assertTrue(all(row['native_pcm_and_cursor'] == 'exact' for row in cases))


if __name__ == "__main__":
    unittest.main()
