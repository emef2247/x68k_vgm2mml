from array import array
import ctypes
import csv
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'py'))
from psg_playback import RATE, render, _library


def authored(commands, *, loop_offset=None, ay_type=0, flags=0, clock=1789772):
    header = bytearray(0x100)
    header[:4] = b'Vgm '
    struct.pack_into('<I', header, 8, 0x171)
    struct.pack_into('<I', header, 0x34, 0x100 - 0x34)
    struct.pack_into('<I', header, 0x74, clock)
    header[0x78], header[0x79] = ay_type, flags
    if loop_offset is not None:
        struct.pack_into('<I', header, 0x1c, 0x100 + loop_offset - 0x1c)
    result = header + commands + b'\x66'
    struct.pack_into('<I', result, 4, len(result) - 4)
    return bytes(result)


def write(register, value):
    return bytes((0xa0, register, value))


def wait(frames):
    return b'\x61' + struct.pack('<H', frames)


class PsgPlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.library, _ = _library(ROOT)
        except RuntimeError as exc:
            if 'Missing external' in str(exc) or 'requires GCC' in str(exc):
                raise unittest.SkipTest(str(exc))
            raise

    def reference(self, playback):
        """Independent per-frame Python dispatch into the public external API."""
        library = self.library
        library.PSG_new.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        library.PSG_new.restype = ctypes.c_void_p
        library.PSG_setVolumeMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
        library.PSG_setQuality.argtypes = [ctypes.c_void_p, ctypes.c_uint8]
        library.PSG_reset.argtypes = [ctypes.c_void_p]
        library.PSG_writeReg.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]
        library.PSG_calc.argtypes = [ctypes.c_void_p]
        library.PSG_calc.restype = ctypes.c_int16
        library.PSG_delete.argtypes = [ctypes.c_void_p]
        chip = library.PSG_new(playback.metadata['clock_hz'], RATE)
        library.PSG_setVolumeMode(chip, 2)
        library.PSG_setQuality(chip, 1)
        library.PSG_reset(chip)
        result = array('h')
        pending = iter(playback.writes)
        item = next(pending, None)
        try:
            for frame in range(playback.frame_count):
                while item is not None and item.vgmticks == frame:
                    library.PSG_writeReg(chip, item.register, item.data)
                    item = next(pending, None)
                value = library.PSG_calc(chip)
                result.extend((value, value))
        finally:
            library.PSG_delete(chip)
        return result

    def test_shared_noise_envelope_repeated_shape_and_exact_order(self):
        setup = (write(0, 80) + write(2, 120) + write(4, 160) + write(6, 7)
                 + write(7, 0) + write(11, 8) + write(12, 0)
                 + write(8, 16) + write(9, 16) + write(10, 16) + write(13, 10))
        raw = authored(setup + wait(1300) + write(13, 10) + wait(1300)
                       + write(8, 0) + write(9, 0) + write(10, 0))
        original = bytes(raw)
        result = render(raw)
        without_restart = render(authored(setup + wait(2600)))
        self.assertEqual(result.samples, self.reference(result))
        self.assertEqual(result.samples[:2600], without_restart.samples[:2600])
        self.assertNotEqual(result.samples[2600:], without_restart.samples[2600:])
        self.assertEqual(len([item for item in result.writes if item.register == 13]), 2)
        self.assertEqual(len(result.writes), 15)
        self.assertEqual(result.frame_count, 2600)
        self.assertEqual(len(result.gates), 1)
        self.assertEqual(result.gates[0].end_vgmticks, 2600)
        self.assertEqual(result.gates[0].termination, 'amplitudes_muted')
        self.assertEqual(result.writes[-1].vgmticks, 2600)
        self.assertEqual(raw, original)
        self.assertEqual(result.samples[::2], result.samples[1::2])

    def test_software_volume_changes_preserve_tone_phase_and_dac_gate(self):
        setup = write(0, 37) + write(7, 62) + write(8, 15)
        varied = render(authored(setup + wait(1001) + write(8, 5)
                                + wait(517) + write(8, 15) + wait(1103)))
        constant = render(authored(setup + wait(2621)))
        self.assertEqual(varied.samples, self.reference(varied))
        self.assertEqual(varied.samples[2 * 1600:], constant.samples[2 * 1600:])
        self.assertEqual(len(varied.gates), 1)
        self.assertEqual(varied.source_end_vgmticks, 2621)
        dac = render(authored(write(0, 37) + write(7, 63) + write(8, 15) + wait(123)))
        self.assertEqual(len(dac.gates), 1)
        self.assertTrue(any(dac.samples))

    def test_loop_replay_continuity_source_ids_and_dump(self):
        setup = write(0, 43) + write(7, 62) + write(8, 15) + wait(301)
        body = write(8, 7) + wait(503) + write(8, 15) + wait(197)
        result = render(authored(setup + body, loop_offset=len(setup)), loop_count=2)
        explicit = render(authored(setup + body + body))
        self.assertEqual(result.samples, explicit.samples)
        self.assertEqual(result.samples, self.reference(result))
        self.assertEqual(result.source_end_vgmticks, 1701)
        replays = [item for item in result.writes if item.loop_iteration]
        self.assertEqual(len(replays), 2)
        for item in replays:
            first = next(write for write in result.writes
                         if write.source_event_id == item.source_event_id)
            self.assertEqual(item.vgmticks - first.vgmticks, 700)
            self.assertEqual(item.original_vgmticks, first.vgmticks)
            self.assertNotEqual(item.event_id, first.event_id)
        with tempfile.TemporaryDirectory() as directory:
            metadata = result.dump(directory, 'AUTHPSG')
            self.assertFalse(metadata['source_state_modified'])
            self.assertEqual(metadata['source_write_count'], 7)
            with wave.open(metadata['waveform_path']) as stream:
                self.assertEqual(stream.getnframes(), result.frame_count)
                self.assertEqual(stream.getframerate(), RATE)
            with open(metadata['writes_csv_path'], newline='') as stream:
                records = list(csv.DictReader(stream))
            self.assertEqual(len(records), 7)
            self.assertEqual(json.loads(Path(metadata['analysis_json_path']).read_text()), metadata)

    def test_variant_and_corruption_guards(self):
        for options in ({'ay_type': 0x10}, {'flags': 4}, {'clock': 0x40000000 | 1789772}):
            with self.assertRaises(ValueError):
                render(authored(write(8, 1) + wait(10), **options))
        with self.assertRaises(ValueError):
            render(authored(write(0x80, 1) + wait(10)))
        with self.assertRaises(ValueError):
            render(b'bad')
        for flags in range(4):
            self.assertEqual(render(authored(wait(3), flags=flags)).frame_count, 3)


if __name__ == '__main__':
    unittest.main()
