"""ZMUSIC (ZMD) renderer: emit a ZMD binary from the converter's
musical layer (MusicalMdx units + voices), the same intermediate
the MDX renderer consumes.

Scope of this renderer: FM tracks and the song loop. Note
units become ZMD notes (pitch from the performed state,
intra-unit pitch or level changes become tied slices), rests
become ZMD rests, control units become raw register writes
($bc) separated by waits ($81), voices become common-block
VSET commands ($18), and the song-loop marker becomes the
$f5 loop point. When the caller supplies the PCM projection's
typed commands and the packed PDX image, one ADPCM track and
the embedded PDX block ($28, ID 2) are rendered as well.
Phrase compression is not attempted.

Format ground truth: src/zmd.mac in kg68k/zmusic3 (header,
track-info table, common commands, track commands). All
multi-byte fields are big-endian; every offset is relative to
the address just after its own field.
"""
import math
import struct
from fractions import Fraction

MASTER_CLOCK = 192
_OP_ORDER_ZMD = (0, 2, 1, 3)  # VSET operator groups are OP1, OP3, OP2, OP4
_SEMITONES = {'c': 0, 'c+': 1, 'd': 2, 'd+': 3, 'e': 4, 'f': 5,
              'f+': 6, 'g': 7, 'g+': 8, 'a': 9, 'a+': 10, 'b': 11}


def _v(value):
    """ZMD variable step/gate value: one byte up to 127, else a
    big-endian word of 0x8000 + value."""
    if value <= 127:
        return bytes((value,))
    if value > 32767:
        raise ValueError(f'ZMD step/gate value too large: {value}')
    return struct.pack('>H', 0x8000 + value)


def _note_number(octave, note, kf):
    """Absolute pitch split into ZMD note number and detune
    (1/64-semitone units) from a performed pitch spelling."""
    midi = (octave + 1) * 12 + _SEMITONES[note]
    total = midi * 64 + kf
    return total // 64, total % 64


def _enabled(value):
    """An OPM enable bit as stored on a performed state: 1/0, or
    None when the register was never written (treated as on)."""
    return value is None or bool(value)


def _vset_data(voice, state):
    """Build the 46-byte CMN_VSET tone data for one voice.

    ``voice`` is the musical layer's (ops, algorithm, feedback,
    mask) tuple with ops rows in (AR, D1R, D2R, RR, D1L, TL, KS,
    MUL, DT1, DT2, AM) order; ``state`` is a performed OPM state
    that uses the voice, supplying the shared LFO setup and the
    channel PMS/AMS. The PAN/AF byte is the OPM channel byte
    (RL enable bits, feedback, algorithm)."""
    ops, algorithm, feedback, _mask = voice
    data = bytearray()
    data.append(state.lfo_rate_raw or 0)
    data.append(0x80 | (state.pmd or 0))
    data.append(state.amd or 0)
    data.append(state.lfo_control_raw or 0)
    pan = ((0x80 if _enabled(state.left_enabled) else 0)
           | (0x40 if _enabled(state.right_enabled) else 0))
    data.append(pan | (feedback << 3) | algorithm)
    data.append(((state.pms or 0) << 4) | (state.ams or 0))
    rows = [ops[i] for i in _OP_ORDER_ZMD]
    data.extend((row[8] << 4) | row[7] for row in rows)    # DT1/MUL
    data.extend(row[5] for row in rows)                    # TL
    data.extend((row[6] << 6) | row[0] for row in rows)   # KS/AR
    data.extend((row[10] << 7) | row[1] for row in rows)  # AME/D1R
    data.extend((row[9] << 6) | row[2] for row in rows)   # DT2/D2R
    data.extend((row[4] << 4) | row[3] for row in rows)   # D1L/RR
    data.extend(b'\x00' * 16)                              # name
    assert len(data) == 46
    return bytes(data)


class _TrackWriter:
    def __init__(self):
        self.data = bytearray()
        self.tick = 0
        self.voice = None
        self.volume = None
        self.pan = None
        self.detune = None

    def wait_to(self, tick):
        while self.tick < tick:
            step = min(tick - self.tick, 32767)
            self.data.append(0x81)
            self.data.extend(_v(step))
            self.tick += step

    def rest(self, start, end):
        self.wait_to(start)
        while self.tick < end:
            step = min(end - self.tick, 32767)
            self.data.append(0x80)
            self.data.extend(_v(step))
            self.data.extend(_v(step))
            self.tick += step

    def register(self, register, value):
        self.data.extend((0xBC, register, value))

    def timbre(self, voice_id):
        if voice_id != self.voice:
            self.data.append(0xC7)
            self.data.extend(struct.pack('>H', voice_id))
            self.voice = voice_id

    def set_volume(self, volume):
        if volume != self.volume:
            self.data.extend((0x90, volume))
            self.volume = volume

    def set_pan(self, pan):
        if pan != self.pan:
            self.data.extend((0xA0, pan))
            self.pan = pan

    def set_detune(self, detune):
        if detune != self.detune:
            self.data.append(0xB9)
            self.data.extend(struct.pack('>h', detune))
            self.detune = detune

    def loop_point(self):
        """Song loop point ([LOOP] / $f5): at the track end the
        driver returns to just after this command. The offset
        list names work locations to re-initialize on loop;
        this renderer emits no constructs that need it, so the
        list is just the terminating zero."""
        self.data.append(0xF5)
        self.data.extend(struct.pack('>I', 0))

    def note(self, number, step, gate, *, tie=False):
        self.data.append(number)
        self.data.extend(_v(step))
        if tie:
            self.data.extend(struct.pack('>H', 0x8000))
        else:
            self.data.extend(_v(gate))
        self.data.append(128)  # velocity: use current volume
        self.tick += step

    def finish(self, end_tick):
        self.rest(self.tick, end_tick)
        self.data.append(0xFF)
        return bytes(self.data)


_PAN_MAP = {3: 64, 2: 0, 1: 127, 0: 128}


def _level_of(state, voice):
    """Channel attenuation of a performed state against its
    voice, mirroring opm_mdx_music.level_for_tone: a uniform
    carrier TL shift is a volume, anything else is not."""
    from opm_mdx_music import level_for_tone
    if voice is None:
        return None
    return level_for_tone(state, voice)


def _render_note_unit(writer, unit, voices):
    """Emit one note unit as one or more tied ZMD notes.

    The performed runs (unit.performed_key) supply the pitch
    and level for each span. Slice boundaries are the run
    boundaries plus the offsets of trajectory register writes
    the note model does not express (key, KC, KF and the
    voice-covered registers are carried by the notes and the
    VSET; the rest are emitted as raw writes at their ticks).
    Adjacent slices merge when pitch, level and pan all agree.
    """
    from opm_mdx_music import tone_and_level
    channel = ord(unit.track) - 65
    skip = {8, 0x20 + channel, 0x28 + channel, 0x30 + channel}
    raw = {}
    for offset, register, data, _state in unit.trajectory:
        if register not in skip and register < 0x40:
            raw.setdefault(offset, []).append((register, data))
    performed = unit.performed_key
    if performed is None:
        writer.rest(unit.start_tick, unit.end_tick)
        return
    initial, runs = performed[0], performed[2]
    tone = tone_and_level(initial)
    if tone is not None:
        _base, attenuation = tone
        writer.set_volume(127 - attenuation)

    def pan_of(state):
        return _PAN_MAP[((1 if _enabled(state.left_enabled) else 0) << 1)
                        | (1 if _enabled(state.right_enabled) else 0)]

    writer.set_pan(pan_of(initial))
    run_spans = []
    cursor = 0
    for duration, state, _commands in runs:
        if duration > 0:
            run_spans.append((cursor, cursor + duration, state))
            cursor += duration
    unit_len = unit.end_tick - unit.start_tick
    boundaries = sorted({0, unit_len}
                        | {start for start, _e, _s in run_spans}
                        | {off for off in raw if 0 <= off <= unit_len})

    def state_at(offset):
        for start, stop, state in run_spans:
            if start <= offset < stop:
                return state
        return run_spans[-1][2] if run_spans else initial

    slices = []
    for index, offset in enumerate(boundaries[:-1]):
        stop = boundaries[index + 1]
        state = state_at(offset)
        pitch = _note_number(state.octave, state.note, state.kf)
        level = _level_of(state, voices[unit.voice_id]
                          if unit.voice_id is not None else None)
        signature = (pitch, level, pan_of(state), offset in raw)
        if slices and slices[-1][2] == signature and offset not in raw:
            slices[-1] = (slices[-1][0], stop, signature, state, pitch)
        else:
            slices.append((offset, stop, signature, state, pitch))
    for index, (start, stop, _sig, state, pitch) in enumerate(slices):
        writer.wait_to(unit.start_tick + start)
        for register, data in raw.get(start, ()):
            writer.register(register, data)
        number, detune = pitch
        writer.set_detune(detune)
        level = _level_of(state, voices[unit.voice_id]
                          if unit.voice_id is not None else None)
        if level is not None:
            writer.set_volume(127 - level)
        writer.set_pan(pan_of(state))
        last = index == len(slices) - 1
        writer.note(number, stop - start, stop - start, tie=not last)


def _render_controls_unit(writer, unit):
    writer.wait_to(unit.start_tick)
    cursor = unit.start_tick
    for offset, register, data, _state in unit.trajectory:
        writer.wait_to(unit.start_tick + offset)
        writer.register(register, data)
        cursor = unit.start_tick + offset
    writer.wait_to(unit.end_tick)


# The five standard MDX PCM rates (F0..F4), mirroring
# pcm_mdx.RATES: the MSM6258 clock dividers the projection
# quantises every playback to.
PCM_RATES_HZ = tuple(
    Fraction(clock, divider)
    for clock, divider in ((4000000, 1024), (4000000, 768),
                           (8000000, 1024), (8000000, 768),
                           (8000000, 512)))
# A PDX tone played at this note number is assumed to sound at
# the top standard rate (15,625 Hz); other rates are note
# offsets from it, the fractional part carried by the detune
# command. One calibration constant for the TypeG check.
PCM_REFERENCE_NOTE = 60
PCM_REFERENCE_RATE = PCM_RATES_HZ[4]


def _pcm_note_for_rate(rate_index):
    """(note, detune in 1/64 semitones) reproducing a standard
    rate against the reference note/rate pair."""
    units = round(768 * math.log2(float(PCM_RATES_HZ[rate_index]
                                        / PCM_REFERENCE_RATE)))
    total = PCM_REFERENCE_NOTE * 64 + units
    note, rem = divmod(total, 64)
    if rem > 32:
        note += 1
        rem -= 64
    return note, rem


def _render_pcm_track(commands, losses):
    """Render the projection's typed PCM commands (one MDX P
    track) as one ZMD ADPCM track in tone mode: the timbre
    command selects the PDX tone, the note pitch carries the
    playback rate against the reference, and each playback's
    setters become volume / pan commands. Returns the writer;
    the caller finishes it at the song end tick."""
    writer = _TrackWriter()
    bank = 0
    rate_index = 4
    detune = None
    tie_next = False
    for row in commands:
        kind = row['kind']
        if kind == 'bank':
            bank = int(row['value'])
        elif kind == 'frequency':
            rate_index = int(row['value'])
        elif kind == 'pan':
            writer.set_pan(_PAN_MAP[int(row['value'])])
        elif kind == 'volume':
            writer.set_volume(255 - int(row['value']))
        elif kind == 'gate':
            if int(row['value']) != 8:
                losses['pcm_gate_approximated'] = 1
        elif kind == 'hold':
            tie_next = True
        elif kind == 'note':
            slot = int(row['value'])
            ticks = int(row['ticks'])
            if bank > 0:
                losses['pcm_bank_tones_not_rendered'] = \
                    losses.get('pcm_bank_tones_not_rendered', 0) + 1
                writer.rest(writer.tick, writer.tick + ticks)
                tie_next = False
                continue
            writer.timbre(slot)
            note, det = _pcm_note_for_rate(rate_index)
            if det != detune:
                writer.set_detune(det)
                detune = det
            writer.note(note, ticks, ticks, tie=tie_next)
            tie_next = False
        elif kind == 'rest':
            ticks = int(row['ticks'])
            writer.rest(writer.tick, writer.tick + ticks)
            tie_next = False
        elif kind == 'song_loop':
            writer.loop_point()
        elif kind == 'end':
            pass
        else:
            key = f'pcm_command_not_rendered:{kind}'
            losses[key] = losses.get(key, 0) + 1
    return writer


def render_zmd(musical, *, timer_value, title='', pcm_commands=None,
               pdx_bytes=None):
    """Render a MusicalMdx object to ZMD bytes.

    FM tracks come from the musical layer; when pcm_commands
    (the projection's typed PCM command rows) and pdx_bytes
    (the packed PDX image) are given, one ADPCM track and the
    embedded PDX block are rendered as well. Returns
    (bytes, losses dict)."""
    losses = {}
    units = musical.units
    voices = musical.voices
    fm_tracks = sorted(t for t in units if 'A' <= t <= 'H')
    other = [t for t in units if t not in fm_tracks
             and not (t == 'P' and pcm_commands is not None)]
    if other:
        losses['tracks_not_rendered'] = len(other)
    timed = list(fm_tracks)
    if pcm_commands is not None and 'P' in units:
        timed.append('P')
    end_tick = max((u.end_tick for track in timed
                    for u in units[track]), default=0)

    # First performed state per voice, for the VSET LFO fields.
    voice_states = {}
    for track in fm_tracks:
        for unit in units[track]:
            if unit.voice_id is not None and unit.voice_id not in voice_states:
                if unit.performed_key is not None:
                    voice_states[unit.voice_id] = unit.performed_key[0]
                    continue
                for _o, _r, _d, state in unit.trajectory:
                    if state is not None:
                        voice_states[unit.voice_id] = state
                        break

    common = bytearray()
    for voice_id in range(len(voices)):
        state = voice_states.get(voice_id)
        if state is None:
            losses['voices_without_state'] = \
                losses.get('voices_without_state', 0) + 1
            continue
        common.append(0x18)
        common.extend(struct.pack('>H', voice_id))
        common.append(0)
        common.extend(_vset_data(voices[voice_id], state))
    pcm_field_index = None
    if pdx_bytes is not None:
        # CMN_BLOCK_PCM ($28), data ID 2 = PDX format, followed
        # by the offset of the embedded PDX image (patched once
        # the layout is known).
        pcm_field_index = len(common) + 2
        common.append(0x28)
        common.append(2)
        common.extend(b'\x00\x00\x00\x00')
    common.append(0xFF)

    track_blobs = []
    for index, track in enumerate(fm_tracks):
        writer = _TrackWriter()
        if index == 0:
            writer.data.append(0xC1)  # tempo by timer value
            writer.data.extend(struct.pack('>H', timer_value))
        for unit in units[track]:
            if unit.kind == 'note':
                if unit.voice_id is not None:
                    writer.timbre(unit.voice_id)
                _render_note_unit(writer, unit, voices)
            elif unit.kind == 'rest':
                writer.rest(unit.start_tick, unit.end_tick)
            elif unit.kind == 'controls':
                _render_controls_unit(writer, unit)
            elif unit.kind == 'song_loop':
                writer.wait_to(unit.start_tick)
                writer.loop_point()
            else:
                losses[f'unit_kind_{unit.kind}_not_rendered'] = \
                    losses.get(f'unit_kind_{unit.kind}_not_rendered', 0) + 1
                writer.wait_to(unit.end_tick)
        track_blobs.append(writer.finish(end_tick))
    track_types = [(0, ord(t) - 65) for t in fm_tracks]
    if pcm_commands is not None:
        pcm_writer = _render_pcm_track(pcm_commands, losses)
        track_blobs.append(pcm_writer.finish(end_tick))
        track_types.append((1, 0))

    header_size = 80
    title_bytes = title.encode('ascii', 'replace') + b'\x00'
    comn_addr = header_size
    trk_table_addr = comn_addr + len(common)
    data_addr = trk_table_addr + 2 + 16 * len(track_blobs)
    pdx_addr = data_addr + sum(len(b) for b in track_blobs)
    title_addr = pdx_addr + (len(pdx_bytes) if pdx_bytes else 0)
    total_size = title_addr + len(title_bytes)
    if pcm_field_index is not None:
        field_addr = comn_addr + pcm_field_index
        struct.pack_into('>I', common, pcm_field_index,
                         pdx_addr - (field_addr + 4))
    header = bytearray()
    header.extend(b'\x1aZmuSiC\x30')
    header.extend(struct.pack('>I', comn_addr - 12))          # comn @8
    header.extend(struct.pack('>I', trk_table_addr - 16))     # trk @12
    header.extend(struct.pack('>I', 0))                       # ctrl @16
    header.extend(struct.pack('>I', total_size))              # size @20
    header.extend(struct.pack('>I', 0))                       # song @24
    header.extend(struct.pack('>I', 0))                       # reserved @28
    # total_offset @32: point at z_total_count (@40), relative to 36
    header.extend(struct.pack('>I', 40 - 36))
    header.extend(struct.pack('>I', title_addr - 40))         # title @36
    header.extend(struct.pack('>I', end_tick))                # total @40
    header.extend(struct.pack('>I', 0))                       # play time
    header.extend(struct.pack('>H', 0x0404))                  # meter 4/4
    header.extend(bytes((0, 0)))                              # metronome, rsv
    header.extend(struct.pack('>h', 0))                       # key
    header.extend(struct.pack('>H', MASTER_CLOCK))            # master clock
    bpm = round(60_000_000 / (48 * (timer_value + 1)))
    header.extend(struct.pack('>H', min(65535, bpm)))         # tempo
    header.extend(struct.pack('>H', 0))                       # reserved
    # cmn flag: bitmap of (common command code / 4); bit 6 = VSET
    # cmn flag: bitmap of (common command code / 4); bit 6 =
    # VSET ($18), bit 10 = BLOCK_PCM ($28)
    cmn_flag = (1 << 6) if voices else 0
    if pdx_bytes is not None:
        cmn_flag |= 1 << 10
    header.extend(struct.pack('>I', cmn_flag))
    header.extend(struct.pack('>I', 0))                       # ctrl flag
    header.extend(struct.pack('>I', 0))                       # instrument
    nof_ad = 1 if pcm_commands is not None else 0
    header.extend(bytes((len(fm_tracks), nof_ad, 0, 0, 0, 0)))  # ch counts
    header.extend(struct.pack('>H', 0))
    assert len(header) == header_size, len(header)

    table = bytearray()
    table.extend(struct.pack('>H', len(track_blobs) - 1))
    cursor = data_addr
    entries = []
    for index, blob in enumerate(track_blobs):
        typ, ch = track_types[index]
        entry = bytearray()
        entry.extend(bytes((0, 0, 0, 0)))                     # stat/mode/frq
        entry.extend(struct.pack('>H', typ))                  # type
        entry.extend(struct.pack('>H', ch))
        play_field_addr = trk_table_addr + 2 + 16 * index + 8
        entry.extend(struct.pack('>I', cursor - (play_field_addr + 4)))
        entry.extend(struct.pack('>I', 0))                    # extra info
        entries.append(entry)
        cursor += len(blob)
    for entry in entries:
        table.extend(entry)

    out = bytearray()
    out.extend(header)
    out.extend(common)
    out.extend(table)
    for blob in track_blobs:
        out.extend(blob)
    if pdx_bytes:
        out.extend(pdx_bytes)
    out.extend(title_bytes)
    assert len(out) == total_size, (len(out), total_size)
    return bytes(out), losses


def _read_v(data, pos):
    byte = data[pos]
    if byte <= 127:
        return byte, pos + 1
    return struct.unpack_from('>H', data, pos)[0] - 0x8000, pos + 2


def parse_zmd(data):
    """Parse back a ZMD written by render_zmd (verification aid):
    header fields, common-block voice numbers, and per-track
    decoded event lists."""
    assert data[:8] == b'\x1aZmuSiC\x30'
    u32 = lambda off: struct.unpack_from('>I', data, off)[0]
    comn = 12 + u32(8)
    trk = 16 + u32(12)
    size = u32(20)
    title = 40 + u32(36)
    voices = []
    pcm_block = None
    pos = comn
    while data[pos] != 0xFF:
        if data[pos] == 0x18:
            voices.append(struct.unpack_from('>H', data, pos + 1)[0])
            pos += 50
        elif data[pos] == 0x28:
            field = pos + 2
            pcm_block = (data[pos + 1],
                         field + 4 + struct.unpack_from('>I', data, field)[0])
            pos += 6
        else:
            raise AssertionError(f'common command {data[pos]:#x}')
    pos += 1
    count = struct.unpack_from('>H', data, trk)[0] + 1
    tracks = []
    for index in range(count):
        entry = trk + 2 + 16 * index
        typ, ch = struct.unpack_from('>HH', data, entry + 4)
        play = entry + 8 + 4 + struct.unpack_from('>I', data, entry + 8)[0]
        events = []
        p = play
        while data[p] != 0xFF:
            cmd = data[p]
            if cmd < 0x80:
                step, p2 = _read_v(data, p + 1)
                if data[p2] >= 0x80 and \
                        struct.unpack_from('>H', data, p2)[0] == 0x8000:
                    gate, p3, tie = 0, p2 + 2, True
                else:
                    gate, p3 = _read_v(data, p2)
                    tie = False
                events.append(('note', cmd, step, gate, tie, data[p3]))
                p = p3 + 1
            elif cmd == 0x80:
                step, p2 = _read_v(data, p + 1)
                _gate, p3 = _read_v(data, p2)
                events.append(('rest', step))
                p = p3
            elif cmd == 0x81:
                step, p2 = _read_v(data, p + 1)
                events.append(('wait', step))
                p = p2
            elif cmd == 0x90:
                events.append(('volume', data[p + 1])); p += 2
            elif cmd == 0xA0:
                events.append(('pan', data[p + 1])); p += 2
            elif cmd == 0xB9:
                events.append(('detune', struct.unpack_from('>h', data, p + 1)[0])); p += 3
            elif cmd == 0xBC:
                events.append(('register', data[p + 1], data[p + 2])); p += 3
            elif cmd == 0xC1:
                events.append(('tempo_timer', struct.unpack_from('>H', data, p + 1)[0])); p += 3
            elif cmd == 0xC7:
                events.append(('timbre', struct.unpack_from('>H', data, p + 1)[0])); p += 3
            elif cmd == 0xF5:
                offsets = []
                p += 1
                while True:
                    value = struct.unpack_from('>I', data, p)[0]
                    p += 4
                    if value == 0:
                        break
                    offsets.append(value)
                events.append(('loop', offsets))
            else:
                raise ValueError(f'unhandled ZMD command {cmd:#x} at {p}')
        tracks.append(dict(type=typ, ch=ch, events=events))
    return dict(size=size, title=data[title:data.index(b'\x00', title)].decode('ascii', 'replace'),
                voices=voices, tracks=tracks, pcm_block=pcm_block)
