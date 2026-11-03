"""Deliverable target VGM for the projected routes.

The projected routes (PSG/SCC, NES, DCSG, OPNA) build the MDX from a
projected OPM target VGM plus, when a PCM bridge exists, a PCM
analysis whose playbacks the PCM binding schedules onto the MDX P
track and into the PDX. That target VGM is normally an intermediate.
This module serializes it as a deliverable next to the MML, merging
the bound PCM playbacks as MSM6258 streams (the encoding the
project's own stream parser and libvgm accept: data bank type 0x04,
stream target 0x17, register-0 play/stop brackets), so the result
can be played on other YM2151/MSM6258 hosts -- emulator or real
cartridge -- to check a conversion independently of MDX playback.

Equivalence scope: the FM side is the projected stream verbatim and
the PCM side is the bridge schedule the binding consumed, minus the
playbacks the binding omitted. Both stay on the source-sample
timeline; the MDX quantizes them to its tick lattice downstream, so
this file is the projection-stage equivalent of the generated MML,
not a replay of the compiled MDX.
"""
import csv
import struct
from pathlib import Path

from vgm_timing import command_times

HEADER_SIZE = 0x100
STREAM_CHIP_OKIM6258 = 0x17
DATA_BANK_ID = 4


def read_omitted_playback_ids(path):
    """Playback ids the PCM binding omitted, from its dumped CSV."""
    path = Path(path)
    if not path.is_file():
        return frozenset()
    with path.open(encoding='utf-8', newline='') as stream:
        return frozenset(int(row['playback_id'])
                         for row in csv.DictReader(stream))


def _u32(raw, offset):
    return struct.unpack_from('<I', raw, offset)[0]


def _waits(body, gap):
    while gap:
        count = min(gap, 65535)
        body.extend(b'\x61' + struct.pack('<H', count))
        gap -= count


def emit_target_vgm(fm_vgm_path, out_path, *, pcm_analysis=None,
                    omitted_playback_ids=frozenset()):
    """Write the deliverable VGM and return a summary dict.

    fm_vgm_path: the projected FM-only target VGM the conversion fed
    to the OPM converter. pcm_analysis: the bridge analysis the PCM
    binding consumed (``.samples`` / ``.playbacks``), or None for an
    FM-only conversion.
    """
    fm_raw = Path(fm_vgm_path).read_bytes()
    events = list(command_times(fm_raw))
    total = _u32(fm_raw, 0x18)
    loop_tick = None
    loop_samples = 0
    loop_offset = _u32(fm_raw, 0x1C)
    if loop_offset:
        loop_address = 0x1C + loop_offset
        for event in events:
            if event.address == loop_address:
                loop_tick = event.vgmticks
                loop_samples = _u32(fm_raw, 0x20)
                break
    merged = []  # (tick, order, payload)
    order = 0
    for index, event in enumerate(events):
        if event.command == 0x66:
            continue
        if event.command in (0x61, 0x62, 0x63) or 0x70 <= event.command <= 0x7F:
            # Waits are not copied: their duration is already the gap
            # between neighbouring event ticks, and the serializer
            # re-emits waits from those gaps. Copying them as well
            # would count every wait twice.
            continue
        end = (events[index + 1].address if index + 1 < len(events)
               else len(fm_raw))
        merged.append((event.vgmticks, order, fm_raw[event.address:end]))
        order += 1
        total = max(total, event.vgmticks)
    summary = dict(fm_commands=len(merged), pcm_playbacks=0, pcm_samples=0,
                   pcm_pan_writes=0, pcm_truncated=0, pcm_clock=None,
                   loop_preserved=loop_tick is not None)
    if pcm_analysis is not None:
        samples = {sample.sample_id: sample
                   for sample in pcm_analysis.samples}
        playbacks = [p for p in pcm_analysis.playbacks
                     if p.sample_id in samples
                     and p.playback_id not in omitted_playback_ids]
        playbacks.sort(key=lambda p: (p.start_vgmticks, p.playback_id))
        if playbacks:
            bank = bytearray()
            offsets = {}
            for sample_id in sorted(samples):
                offsets[sample_id] = len(bank)
                data = samples[sample_id].encoded_bytes
                merged.append((0, order, b'\x67\x66\x04'
                               + struct.pack('<I', len(data)) + data))
                order += 1
                bank += data
            merged.append((0, order, b'\x90\x00' + bytes((STREAM_CHIP_OKIM6258, 0, 1))))
            order += 1
            merged.append((0, order, b'\x91\x00' + bytes((DATA_BANK_ID, 1, 0))))
            order += 1
            summary['pcm_clock'] = playbacks[0].clock_hz
            summary['pcm_clock_mixed'] = len({p.clock_hz for p in playbacks}) > 1
            frequency = None
            pan = None
            playing_until = -1
            for playback in playbacks:
                data = samples[playback.sample_id].encoded_bytes
                total_nibbles = 2 * len(data)
                consumed = (playback.consumed_nibbles
                            if playback.consumed_nibbles is not None
                            else playback.nominal_nibbles)
                play_nibbles = (total_nibbles if consumed is None
                                else min(consumed, total_nibbles))
                count = (play_nibbles + 1) // 2
                if count <= 0:
                    continue
                start = playback.start_vgmticks
                if start < playing_until:
                    # The binding never overlaps physical playbacks;
                    # stop defensively before retriggering.
                    merged.append((start, order, b'\x94\x00'))
                    order += 1
                    merged.append((start, order, b'\xb7\x00\x01'))
                    order += 1
                # Stream frequency is the byte rate, half the nibble
                # rate, rounded half up (7813 for 15625, matching the
                # project's native stream fixtures).
                rate = int(float(playback.rate_hz) / 2 + 0.5)
                if rate != frequency:
                    merged.append((start, order,
                                   b'\x92\x00' + struct.pack('<I', rate)))
                    order += 1
                    frequency = rate
                if playback.pan is not None and playback.pan != pan:
                    merged.append((start, order,
                                   bytes((0xB7, 0x02, playback.pan & 3))))
                    order += 1
                    pan = playback.pan
                    summary['pcm_pan_writes'] += 1
                merged.append((start, order, b'\xb7\x00\x01'))
                order += 1
                merged.append((start, order, b'\xb7\x00\x02'))
                order += 1
                merged.append((start, order,
                               b'\x93\x00'
                               + struct.pack('<I', offsets[playback.sample_id])
                               + b'\x01' + struct.pack('<I', count)))
                order += 1
                summary['pcm_playbacks'] += 1
                playing_until = playback.end_vgmticks
                if play_nibbles < total_nibbles:
                    summary['pcm_truncated'] += 1
                    stop_tick = playback.end_vgmticks
                else:
                    # A full sample ends physically when its last byte
                    # is consumed, one byte period after the final
                    # supply; the bridge end is the source gate's own
                    # (ceiling-rounded) tick and can sit a tick later.
                    stop_tick = start + int(
                        count * 88200 / float(playback.rate_hz) + 0.5)
                # Close every playback with a stop, not only truncated
                # ones: the reference stream model treats the chip as
                # playing until a stop control arrives, so an open span
                # would misstate the playback's rate and tail.
                merged.append((stop_tick, order, b'\x94\x00'))
                order += 1
                merged.append((stop_tick, order, b'\xb7\x00\x01'))
                order += 1
                total = max(total, playback.end_vgmticks)
            summary['pcm_samples'] = len(samples)
    merged.sort(key=lambda item: (item[0], item[1]))
    body = bytearray()
    cursor = 0
    loop_position = None
    for tick, _, payload in merged:
        if loop_tick is not None and loop_position is None and tick >= loop_tick:
            _waits(body, loop_tick - cursor)
            cursor = loop_tick
            loop_position = HEADER_SIZE + len(body)
        _waits(body, tick - cursor)
        cursor = tick
        body.extend(payload)
    if loop_tick is not None and loop_position is None:
        _waits(body, loop_tick - cursor)
        cursor = loop_tick
        loop_position = HEADER_SIZE + len(body)
    _waits(body, total - cursor)
    body.append(0x66)
    header = bytearray(HEADER_SIZE)
    header[:4] = b'Vgm '
    struct.pack_into('<I', header, 4, HEADER_SIZE + len(body) - 4)
    struct.pack_into('<I', header, 8, 0x171)
    struct.pack_into('<I', header, 0x18, total)
    struct.pack_into('<I', header, 0x30, _u32(fm_raw, 0x30))
    if summary['pcm_clock']:
        struct.pack_into('<I', header, 0x90, summary['pcm_clock'])
        # OKIM6258 options byte, matching the project's native
        # fixtures: bit 2 marks the 4-bit ADPCM data format.
        header[0x94] = 6
    struct.pack_into('<I', header, 0x34, HEADER_SIZE - 0x34)
    if loop_position is not None:
        struct.pack_into('<I', header, 0x1C, loop_position - 0x1C)
        struct.pack_into('<I', header, 0x20, loop_samples)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(header) + bytes(body))
    summary['total_samples'] = total
    summary['bytes'] = HEADER_SIZE + len(body)
    return summary
