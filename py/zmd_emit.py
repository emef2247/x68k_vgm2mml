"""ZMUSIC (ZMD) renderer: emit a ZMD binary from the converter's
musical layer (MusicalMdx units + voices), the same intermediate
the MDX renderer consumes.

Scope of this first renderer: FM tracks only. Note units become
ZMD notes (pitch from the performed state, intra-unit pitch or
level changes become tied slices), rests become ZMD rests,
control units become raw register writes ($bc) separated by
waits ($81), voices become common-block VSET commands ($18).
PCM tracks, song loops and phrase compression are not rendered
yet and are reported as losses by the caller-visible summary.

Format ground truth: src/zmd.mac in kg68k/zmusic3 (header,
track-info table, common commands, track commands). All
multi-byte fields are big-endian; every offset is relative to
the address just after its own field.
"""
import struct

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


def render_zmd(musical, *, timer_value, title=''):
    """Render a MusicalMdx object to ZMD bytes (FM tracks only).

    Returns (bytes, losses dict)."""
    losses = {}
    units = musical.units
    voices = musical.voices
    fm_tracks = sorted(t for t in units if 'A' <= t <= 'H')
    other = [t for t in units if t not in fm_tracks]
    if other:
        losses['tracks_not_rendered'] = len(other)
    end_tick = max((u.end_tick for track in fm_tracks
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
                losses['song_loop_not_rendered'] = 1
                writer.wait_to(unit.start_tick)
            else:
                losses[f'unit_kind_{unit.kind}_not_rendered'] = \
                    losses.get(f'unit_kind_{unit.kind}_not_rendered', 0) + 1
                writer.wait_to(unit.end_tick)
        track_blobs.append(writer.finish(end_tick))

    header_size = 80
    title_bytes = title.encode('ascii', 'replace') + b'\x00'
    comn_addr = header_size
    trk_table_addr = comn_addr + len(common)
    data_addr = trk_table_addr + 2 + 16 * len(track_blobs)
    title_addr = data_addr + sum(len(b) for b in track_blobs)
    total_size = title_addr + len(title_bytes)
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
    header.extend(struct.pack('>I', 0))                       # cmn flag
    header.extend(struct.pack('>I', 0))                       # ctrl flag
    header.extend(struct.pack('>I', 0))                       # instrument
    header.extend(bytes((len(track_blobs), 0, 0, 0, 0, 0)))   # ch counts
    header.extend(struct.pack('>H', 0))
    assert len(header) == header_size, len(header)

    table = bytearray()
    table.extend(struct.pack('>H', len(track_blobs) - 1))
    cursor = data_addr
    entries = []
    for index, blob in enumerate(track_blobs):
        entry = bytearray()
        entry.extend(bytes((0, 0, 0, 0)))                     # stat/mode/frq
        entry.extend(struct.pack('>H', 0))                    # type FM
        entry.extend(struct.pack('>H', ord(fm_tracks[index]) - 65))
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
    pos = comn
    while data[pos] != 0xFF:
        assert data[pos] == 0x18, hex(data[pos])
        voices.append(struct.unpack_from('>H', data, pos + 1)[0])
        pos += 50
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
            else:
                raise ValueError(f'unhandled ZMD command {cmd:#x} at {p}')
        tracks.append(dict(type=typ, ch=ch, events=events))
    return dict(size=size, title=data[title:data.index(b'\x00', title)].decode('ascii', 'replace'),
                voices=voices, tracks=tracks)
