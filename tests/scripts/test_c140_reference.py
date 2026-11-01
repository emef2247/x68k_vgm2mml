"""Optional exact comparison with pinned independent C140 C source.

The dependency is deliberately opt-in; run scripts/c140_reference.py --setup
before this test. Every ROM and command here is newly authored.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "py"), str(ROOT / "scripts")]
from c140_reference import LIBRARY, Reference, metadata
from c140_bank import Voice


class AuthoredRom:
    def __init__(self, data):
        self.data = data

    def read(self, address):
        return self.data[address & (len(self.data) - 1)]


def compare_case(name, *, chip_type=0, clock=12288000, mode=0x90, frequency=0x6500, events=(), frames=700):
    # Whole power-of-two ROM, with distinct bank content and both signs.
    rom = bytes(((i * 37 + (i >> 16) * 19 + (i >> 8) * 3) & 255) for i in range(0x200000))
    reference = Reference(rom, clock, chip_type)
    memory = AuthoredRom(rom)
    registers = [211, 255, frequency >> 8, frequency & 255, 0, mode,
                 0, 0, 1, 0, 0, 13, 0, 0, 0, 0]
    voice = None

    def write(register, value):
        nonlocal voice
        registers[register] = value
        reference.write(register, value)
        if register == 5:
            if value & 0x80:
                voice = Voice(registers, (registers[6] << 8) | registers[7],
                              (registers[8] << 8) | registers[9],
                              (registers[10] << 8) | registers[11])
            elif voice is not None:
                voice.key = False

    try:
        for register, value in enumerate(registers):
            if register != 5:
                write(register, value)
        write(5, mode)
        changes = {}
        for frame, register, value in events:
            changes.setdefault(frame, []).append((register, value))
        for frame in range(frames):
            for register, value in changes.get(frame, ()):
                write(register, value)
            dt = voice.step(memory, chip_type, clock)
            expected = (0, 0) if dt is None else ((dt * registers[1]) >> 9, (dt * registers[0]) >> 9)
            actual = reference.frame()
            if actual != expected:
                raise AssertionError(f"{name} frame {frame}: stereo {actual} != {expected}")
            state = (int(voice.key), voice.position, voice.fraction, voice.last, voice.previous, voice.difference)
            if reference.state() != state:
                raise AssertionError(f"{name} frame {frame}: cursor {reference.state()} != {state}")
        return {"name": name, "frames": frames, "chip_type": chip_type,
                "clock_hz": clock, "stereo_and_cursor": "exact"}
    finally:
        reference.close()


def compare_authored_cases():
    metadata()
    results = []
    for chip_type in (0, 1):
        prefix = f"system{2 if chip_type == 0 else 21}"
        results.append(compare_case(prefix + "_linear_loop", chip_type=chip_type))
        results.append(compare_case(prefix + "_custom_mulaw_loop", chip_type=chip_type, mode=0x98))
        results.append(compare_case(prefix + "_natural_end", chip_type=chip_type, mode=0x80))
        results.append(compare_case(prefix + "_retrigger_live_bank_volume_pause", chip_type=chip_type,
            events=((40, 4, 0x20), (70, 1, 0), (90, 0, 0), (120, 1, 255), (120, 0, 211),
                    (150, 2, 0), (150, 3, 0), (180, 2, 0x32), (180, 3, 0x19),
                    (220, 6, 0), (220, 7, 10), (220, 9, 200),
                    (300, 5, 0x90), (400, 5, 0x90), (600, 5, 0))))
        results.append(compare_case(prefix + "_fractional_native_clock", chip_type=chip_type,
                                    clock=8192000, frequency=0xffff))
    return results


@unittest.skipUnless(sys.platform.startswith("linux") and LIBRARY.exists(),
                     "optional WSL/Linux C140 oracle: run scripts/c140_reference.py --setup")
class C140ReferenceTests(unittest.TestCase):
    def test_gate_scheduler_uses_one_native_clock_across_live_controls(self):
        from c140 import Trace, Write, RomBlock
        from c140_bank import render_gates
        clock = 12288000
        rate = clock // 288
        rom = bytes((i * 37) & 255 for i in range(1024))
        register_values = [255, 255, 0x65, 0, 0, 0x98, 0, 0, 1, 0, 0, 13]
        changes = [(0, i, value) for i, value in enumerate(register_values) if i != 5]
        changes += [(7, 5, 0x98), (91, 2, 0), (91, 3, 0),
                    (131, 2, 0x32), (131, 3, 0x19), (211, 5, 0x98),
                    (333, 1, 0), (333, 0, 0), (401, 1, 255), (401, 0, 255),
                    (777, 5, 0)]
        writes = tuple(Write(i + 1, i + 1, 0, tick, 0, register, value)
                       for i, (tick, register, value) in enumerate(changes))
        block = RomBlock(0, 0, 0, 0, 0, len(rom), 0, rom)
        trace = Trace(900, clock, clock, 'header', 0, writes, (block,), (), (), ())
        gates, actual_rate = render_gates(trace)
        self.assertEqual(actual_rate, rate)
        reference = Reference(rom, clock, 0)
        registers = [0] * 16
        expected = []
        active = None
        frame = 0

        def advance(target):
            nonlocal frame
            while frame < target:
                reference.frame()
                if active is not None:
                    key, _, fraction, _, previous, difference = reference.state()
                    self.assertEqual(key, 1)
                    dt = previous + ((difference * fraction) >> 16)
                    if not ((registers[2] << 8) | registers[3]):
                        dt = 0
                    level = ((registers[0] + registers[1]) / 2
                             if registers[0] and registers[1] else max(registers[:2]))
                    active['wave'].append(round(dt * level / 510))
                frame += 1

        try:
            for event in writes:
                advance(-(-event.vgmticks * rate // 44100))
                registers[event.register] = event.value
                reference.write(event.register, event.value)
                if event.register == 5:
                    if active is not None:
                        active['end_frame'] = frame
                        expected.append(active)
                    active = ({'wave': [], 'start_frame': frame} if event.value & 0x80 else None)
            advance(-(-trace.source_end_vgmticks * rate // 44100))
            self.assertIsNone(active)
            self.assertEqual(len(gates), 2)
            self.assertEqual(len(gates), len(expected))
            for gate, wanted in zip(gates, expected):
                self.assertEqual(gate['start_frame'], wanted['start_frame'])
                self.assertEqual(gate['end_frame'], wanted['end_frame'])
                self.assertEqual(list(gate['wave']), wanted['wave'])
        finally:
            reference.close()

    def test_authored_runtime_against_pinned_core(self):
        results = compare_authored_cases()
        self.assertEqual(len(results), 10)
        self.assertTrue(all(row["stereo_and_cursor"] == "exact" for row in results))


if __name__ == "__main__":
    unittest.main()
