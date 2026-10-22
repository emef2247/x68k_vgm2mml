"""Authored finite voice-part behavior, independent of private listening inputs."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'py'), str(ROOT / 'tests/scripts')]
import test_segapcm_bank as bank_fixtures
from generate_segapcm_listening import fm, patterns, voice, wait, write
from segapcm_bank import BankUnsupported, project
from segapcm_bank_parts import PartCollector, project_parts
from segapcm_playback import render


class SegaPcmBankPartsTests(unittest.TestCase):
    source = bank_fixtures.SegaPcmBankTests.source

    def setup_commands(self):
        base, _, _ = patterns()['SEGAONE']
        return base[:base.index(fm()) + len(fm())]

    def test_observer_preserves_native_audio_and_runtime_evidence(self):
        trace, native, _ = self.source(name='SEGAMIX')
        observer = PartCollector()
        observed = render(trace, native.source_end_vgmticks, voice_sink=observer)
        self.assertEqual(observed, native)
        self.assertGreater(observer.frame_count, 0)
        self.assertGreater(len(observer.parts), 1)

    def test_muted_initialization_advances_cursor_and_shares_suffix(self):
        # Eleven source ticks put the first audible frame at native frame 8:
        # 8 * delta32 reaches byte 1, rather than restarting byte 0 on unmute.
        commands = (self.setup_commands() + voice(0, left=0, right=0, end=1)
                    + wait(11) + write(0, 2, 64)
                    + voice(1, left=64, right=0, end=1) + write(1, 0x84, 1)
                    + wait(1000) + write(0, 0x86, 1) + write(1, 0x86, 1))
        trace, native, raw = self.source(commands)
        result = project(trace, native, source_raw=raw)
        self.assertEqual(len(result.samples), 1)
        self.assertEqual(len(result.playbacks), 2)
        self.assertEqual([e['address_fixed'] for e in result.bank_events], [256, 256])
        self.assertEqual(result.bank_events[0]['boundary'], 'unmute')
        self.assertEqual(result.bank_parts[0]['leading_silent_frames'], 8)
        self.assertEqual(result.playbacks[0].start_vgmticks, 11)
        self.assertEqual(result.playbacks[0].sample_id, result.playbacks[1].sample_id)

    def test_same_tick_address_bytes_form_one_effective_seek_boundary(self):
        commands = (self.setup_commands() + voice(0)
                    + wait(11) + write(0, 0x84, 10) + write(0, 0x85, 1)
                    + wait(1000) + write(0, 0x86, 1))
        trace, native, raw = self.source(commands)
        result = project(trace, native, source_raw=raw)
        self.assertEqual(len(result.playbacks), 2)
        first, second = result.playbacks
        self.assertEqual(first.end_vgmticks, second.start_vgmticks)
        self.assertEqual(first.termination, 'seek')
        self.assertEqual(result.bank_events[1]['boundary'], 'seek')
        self.assertEqual(result.bank_events[1]['address_fixed'], 0x010a00)
        self.assertEqual(result.bank_stats['seek_part_count'], 1)

    def test_held_gain_and_rate_bake_one_part_without_double_attenuation(self):
        commands = (self.setup_commands() + voice(0, left=64, right=0)
                    + wait(100) + write(0, 2, 32)
                    + wait(100) + write(0, 7, 48)
                    + wait(100) + write(0, 0x86, 1))
        trace, native, raw = self.source(commands)
        result = project(trace, native, source_raw=raw)
        self.assertEqual(len(result.playbacks), 1)
        event, = result.bank_events
        self.assertEqual(event['asset_kind'], 'trajectory_variant')
        self.assertTrue(event['volume_baked'])
        self.assertEqual(event['control_run_count'], 3)
        self.assertEqual(result.playbacks[0].target_volume, 128)
        self.assertEqual(event['desired_gain'], 1)
        self.assertEqual(event['effective_gain'], 1)
        self.assertEqual(result.playbacks[0].start_vgmticks, 0)
        self.assertEqual(result.playbacks[0].end_vgmticks, 300)
        self.assertEqual(len(result.samples), 1)

    def test_loop_enable_without_traversal_is_finite_but_audible_loop_is_not(self):
        prefix = self.setup_commands() + voice(0, end=1, looping=True)
        trace, native, raw = self.source(prefix + wait(100) + write(0, 0x86, 1))
        self.assertFalse(any(e.kind == 'sample_loop' for e in native.runtime_events))
        result = project(trace, native, source_raw=raw)
        self.assertEqual(len(result.playbacks), 1)
        self.assertEqual(result.bank_stats['actual_sample_loop_count'], 0)
        trace, native, raw = self.source(prefix + wait(10000))
        self.assertTrue(any(e.kind == 'sample_loop' for e in native.runtime_events))
        with self.assertRaises(BankUnsupported) as failure:
            project(trace, native, source_raw=raw)
        self.assertEqual(failure.exception.reason['code'], 'sample_loop')

    def test_silent_control_interval_keeps_its_elapsed_time_in_variant(self):
        commands = (self.setup_commands() + voice(0, left=64, right=0)
                    + wait(100) + write(0, 2, 0)
                    + wait(200) + write(0, 2, 64)
                    + wait(100) + write(0, 0x86, 1))
        trace, native, raw = self.source(commands)
        result = project_parts(trace, native, source_raw=raw)
        self.assertEqual(len(result.playbacks), 1)
        playback, = result.playbacks
        self.assertEqual((playback.start_vgmticks, playback.end_vgmticks), (0, 400))
        self.assertEqual(result.bank_events[0]['control_run_count'], 3)
        self.assertTrue(result.bank_events[0]['volume_baked'])
        observer = PartCollector()
        render(trace, native.source_end_vgmticks, voice_sink=observer)
        part, = observer.parts
        mute, unmute = part.changes[1][0], part.changes[2][0]
        self.assertTrue(all(v == 0 for v in part.audio[mute:unmute]))
        self.assertGreater(unmute - mute, 100)

    def sparse_rom_setup(self):
        setup = self.setup_commands()
        return setup[:7] + (65536).to_bytes(4, 'little') + setup[11:]

    def test_muted_missing_rom_is_evidence_not_an_audible_bank_failure(self):
        # Start outside the authored ROM while muted, then stop it. A separate
        # ordinary voice supplies the retained bank asset.
        commands = (self.sparse_rom_setup() + voice(0, left=0, right=0, end=255)
                    + write(0, 0x84, 0) + write(0, 0x85, 0x80)
                    + wait(100) + write(0, 0x86, 1)
                    + voice(1, left=64, right=0, end=1)
                    + wait(100) + write(1, 0x86, 1))
        trace, native, raw = self.source(commands)
        result = project_parts(trace, native, source_raw=raw)
        self.assertGreater(result.bank_stats['muted_missing_rom_reads'], 0)
        self.assertEqual(result.bank_stats['missing_rom_reads'], native.missing_rom_reads)
        self.assertEqual(len(result.playbacks), 1)
        self.assertEqual(result.playbacks[0].source_channel, 1)

    def test_audible_missing_rom_reports_location_and_stays_blocking(self):
        commands = (self.sparse_rom_setup() + voice(0, left=64, right=0, end=255)
                    + write(0, 0x84, 0) + write(0, 0x85, 0x80) + wait(100))
        trace, native, raw = self.source(commands)
        with self.assertRaisesRegex(Exception, 'audible voice frames.*generation=.*address_fixed='):
            project_parts(trace, native, source_raw=raw)

    def test_dump_retains_asset_event_and_part_provenance(self):
        commands = (self.setup_commands() + voice(0, left=64, right=0)
                    + wait(100) + write(0, 2, 32)
                    + wait(100) + write(0, 0x86, 1))
        trace, native, raw = self.source(commands)
        result = project(trace, native, source_raw=raw)
        with tempfile.TemporaryDirectory() as temp:
            result.dump(temp, 'parts')
            for name, expected in (('assets', result.bank_assets),
                                   ('events', result.bank_events),
                                   ('parts', result.bank_parts)):
                path = Path(temp) / f'parts.segapcm_bank.{name}.csv'
                with path.open(newline='') as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), len(expected))
                self.assertEqual(set(rows[0]), set(expected[0]))
                self.assertEqual(rows[0]['view_id'], expected[0]['view_id'])
                if name == 'assets':
                    identity = json.loads(rows[0]['identity_json'])
                    self.assertIn('source_wave_sha256', identity)
                    self.assertIn('source_rate', identity)
                    self.assertIn('pcm_profile', identity)
                    self.assertEqual(int(rows[0]['encoded_bytes']),
                                     len(result.samples[0].encoded_bytes))
            report = json.loads((Path(temp) / 'parts.pcm_source.json').read_text())
            self.assertEqual(report['sample_amplitude_scale'], 128)
            self.assertTrue(report['parallel_playbacks'])
            self.assertTrue(report['target_evidence'])


if __name__ == '__main__':
    unittest.main()
