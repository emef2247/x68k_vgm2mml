import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'py'))

from opm import OpmRegisterState
from opm_mdx_music import MusicalMdx, MusicUnit, tone_and_level
from zmd_emit import pack_pdx, parse_zmd, render_zmd


def _state():
    regs = OpmRegisterState()
    regs.write(0x18, 0)          # LFO rate
    regs.write(0x1B, 0)          # LFO waveform/control
    regs.write(0x20, 0xC7)       # both speakers, alg 7, fb 0
    regs.write(0x38, 0)          # PMS/AMS
    regs.write(0x28, 0x3E)       # KC: C, octave field 3
    regs.write(0x30, 0)          # KF
    for slot in range(4):
        base = slot * 8
        regs.write(0x40 + base, 0)    # DT1/MUL
        regs.write(0x60 + base, 31)   # TL
        regs.write(0x80 + base, 31)   # KS/AR
        regs.write(0xA0 + base, 0)    # AME/D1R
        regs.write(0xC0 + base, 0)    # DT2/D2R
        regs.write(0xE0 + base, 15)   # D1L/RR
    return regs.snapshot(0)


class ZmdEmitTest(unittest.TestCase):
    def test_roundtrip_notes_controls_and_voice(self):
        state = _state()
        tone = tone_and_level(state)
        self.assertIsNotNone(tone)
        voice = tone[0]
        note = MusicUnit('A', 0, 48, 0, 0, 'note', '', (), (),
                         ((0, 0x28, 0x3E, state),), voice_id=0,
                         performed_key=(state, (), ((48, state, ()),),
                                        (), (), state))
        rest = MusicUnit('A', 48, 96, 0, 0, 'rest', '', (), (), ())
        loop = MusicUnit('A', 48, 48, 0, 0, 'song_loop', '', (), (), ())
        controls = MusicUnit('B', 0, 96, 0, 0, 'controls', '', (), (),
                             ((0, 0x18, 100, None), (10, 0x1B, 2, None)))
        musical = MusicalMdx({'A': [note, loop, rest], 'B': [controls]},
                             (voice,), {}, {}, '', '', '', ())
        data, losses = render_zmd(musical, timer_value=199, title='test')
        self.assertEqual(losses, {})
        parsed = parse_zmd(data)
        self.assertEqual(parsed['size'], len(data))
        self.assertEqual(parsed['title'], 'test')
        self.assertEqual(parsed['voices'], [0])
        self.assertEqual(len(parsed['tracks']), 2)
        track_a, track_b = parsed['tracks']
        self.assertIn(('tempo_timer', 199), track_a['events'])
        notes = [e for e in track_a['events'] if e[0] == 'note']
        self.assertEqual(notes, [('note', 60, 48, 48, False, 128)])
        self.assertIn(('loop', []), track_a['events'])
        for track in parsed['tracks']:
            total = sum(e[1] if e[0] in ('rest', 'wait') else e[2]
                        for e in track['events']
                        if e[0] in ('rest', 'wait', 'note'))
            self.assertEqual(total, 96)
        registers = [e for e in track_b['events'] if e[0] == 'register']
        self.assertEqual(registers,
                         [('register', 0x18, 100), ('register', 0x1B, 2)])

    def test_pcm_track_and_embedded_pdx(self):
        pdx = bytes(768) + b'ADPCMDATA'
        commands = [
            dict(kind='bank', value=0, ticks='', start_tick=0),
            dict(kind='frequency', value=0, ticks='', start_tick=0),
            dict(kind='pan', value=3, ticks='', start_tick=0),
            dict(kind='gate', value=8, ticks='', start_tick=0),
            dict(kind='volume', value=200, ticks='', start_tick=0),
            dict(kind='note', value=1, ticks=48, start_tick=0),
            dict(kind='rest', value='', ticks=48, start_tick=48),
            dict(kind='song_loop', value='', ticks='', start_tick=96),
            dict(kind='end', value='', ticks='', start_tick=96),
        ]
        musical = MusicalMdx({'P': []}, (), {}, {}, '', '', '', ())
        data, losses = render_zmd(musical, timer_value=199,
                                  pcm_commands=commands, pdx_bytes=pdx)
        self.assertFalse(losses)
        parsed = parse_zmd(data)
        self.assertEqual(parsed['pcm_block'][0], 2)
        start = parsed['pcm_block'][1]
        self.assertEqual(data[start:start + len(pdx)], pdx)
        self.assertEqual(len(parsed['tracks']), 1)
        track = parsed['tracks'][0]
        self.assertEqual((track['type'], track['ch']), (1, 0))
        events = track['events']
        self.assertIn(('timbre', 1), events)
        self.assertIn(('volume', 55), events)
        self.assertIn(('pan', 64), events)
        self.assertIn(('loop', []), events)
        notes = [e for e in events if e[0] == 'note']
        # F0 = 15,625 / 4 Hz -> two octaves below the reference
        self.assertEqual(notes[0][1], 36)
        steps = sum(e[1] if e[0] == 'rest' else e[2]
                    for e in events if e[0] in ('rest', 'note'))
        self.assertEqual(steps, 96)

    def test_pack_pdx_layout(self):
        image = pack_pdx({0: b'AAAA', 2: b'BB'})
        self.assertEqual(len(image), 768 + 6)
        import struct
        self.assertEqual(struct.unpack_from('>II', image, 0), (768, 4))
        self.assertEqual(struct.unpack_from('>II', image, 8), (0, 0))
        self.assertEqual(struct.unpack_from('>II', image, 16), (772, 2))
        self.assertEqual(image[768:], b'AAAABB')


if __name__ == '__main__':
    unittest.main()
