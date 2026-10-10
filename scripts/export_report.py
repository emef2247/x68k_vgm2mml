"""Small output-only summaries; never treat encoded-byte checks as playback proof."""
from collections import Counter
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from pcm_mdx import RATES
from vgm_io import read_vgm_bytes
from vgm_timing import command_times


def _json(path):
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected an object in {path.name}')
    return value


def _csv(path):
    if not path.is_file():
        return []
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def source_statistics(source):
    """Count one physical stream pass, operator edges separately from writes."""
    raw = read_vgm_bytes(source)
    masks = [0] * 8
    on = off = rising = falling = writes = end = 0
    commands = Counter()
    for event in command_times(raw):
        commands[event.command] += 1
        end = event.vgmticks + event.wait_samples
        if event.command != 0x54 or raw[event.address + 1] != 8:
            continue
        value = raw[event.address + 2]
        channel, mask = value & 7, (value >> 3) & 15
        writes += 1
        on += bool(mask)
        off += not mask
        rising += (mask & ~masks[channel]).bit_count()
        falling += (masks[channel] & ~mask).bit_count()
        masks[channel] = mask
    return dict(samples=end, opm_used=bool(commands[0x54]), opm_writes=commands[0x54], writes=writes,
                on=on, off=off, rising=rising, falling=falling)


def _codes(items):
    counts = Counter(str(item.get('code', 'unknown')) for item in items)
    parts = [f'{code} x{count}' for code, count in counts.most_common(8)]
    if len(counts) > 8:
        parts.append(f'+{len(counts) - 8} other codes')
    return ', '.join(parts) or 'none'


def _pdx_payload_check(folder, stem, pdx):
    bindings = _csv(folder / f'{stem}.pcm_bindings.csv')
    if not bindings or not pdx.is_file():
        return 'unmeasured (no current bindings/PDX pair)'
    payload = pdx.read_bytes()
    matched = checked = total = 0
    for binding in bindings:
        bank, slot = int(binding['bank']), int(binding['slot'])
        sample_path = (folder / f'{stem}.pcm' / binding['file']).resolve()
        if not sample_path.is_relative_to((folder / f'{stem}.pcm').resolve()):
            raise ValueError('PCM sample path leaves the generated sample folder')
        sample = sample_path.read_bytes()
        position = (bank * 96 + slot) * 8
        checked += 1
        total += len(sample)
        if bank != 0 or not 0 <= slot < 96 or position + 8 > len(payload):
            continue
        offset, length = struct.unpack_from('>II', payload, position)
        if offset < 768 or offset + length > len(payload):
            continue
        packed = payload[offset:offset + length]
        matched += (len(sample) == length and hashlib.sha256(sample).digest() ==
                    hashlib.sha256(packed).digest())
    return (f'{matched}/{checked} allocated samples byte-exact; {total} encoded bytes; '
            f'PDX {len(payload)} bytes (includes 768-byte table). '
            'Compared with packing inputs; not decoder/playback fidelity')


def _encoded_command_summary(folder, stem):
    rows = _csv(folder / f'{stem}.mdx.commands.csv')
    if not rows:
        return 'Compiled MDX command statistics: unmeasured (no command census)'
    counts = Counter(row['kind'] for row in rows)
    fm_notes = sum(row['kind'] == 'Note' and row['track'] in 'ABCDEFGH' for row in rows)
    pcm_notes = counts['Note'] - fm_notes
    masks = [int(row['operands_hex'].replace(' ', '')[2:4], 16) & 0x78
             for row in rows if row.get('opcode_hex', '').lower().removeprefix('0x') == 'fe'
             and row.get('operands_hex', '').lower().replace(' ', '').startswith('08')]
    return (f'Compiled MDX encoded commands: FM notes {fm_notes}; PCM notes {pcm_notes}; '
            f'holds {counts["KeyOffDisable"]}; rests {counts["Rest"]}; '
            f'raw register 0x08 requests {len(masks)} (On {sum(bool(mask) for mask in masks)}, '
            f'Off {sum(not mask for mask in masks)}). '
            'Repeats/loops not expanded; counts are not source Key-On/Off equivalence')


def write_export_report(source, folder, stem, row):
    """Write a report for success, blocked or failed conversion, without extra replay."""
    source, folder = Path(source), Path(folder)
    unavailable = []

    def optional(label, function, fallback):
        try:
            return function()
        except (OSError, ValueError, KeyError, TypeError, AttributeError, ArithmeticError,
                struct.error) as error:
            unavailable.append(f'{label}: unavailable ({str(error)[:160]})')
            return fallback

    conversion_failed = row['status'].startswith('conversion_')
    conversion = (optional('Route diagnostics', lambda: _json(folder / f'{stem}.conversion.json'), {})
                  if not conversion_failed else {})
    assessment = (optional('PCM assessment', lambda: _json(folder / f'{stem}.pcm.assessment.json'), {})
                  if not conversion_failed else {})
    target_current = not conversion_failed and assessment.get('artifact_status') != 'blocked'
    if not target_current:
        conversion = {}
    pcm_current = target_current and assessment.get('artifact_status') == 'generated'
    timing = (optional('PCM timing', lambda: _json(folder / f'{stem}.pcm.timing.json'), {})
              if pcm_current else {})
    normalization = (optional('Normalization', lambda: _json(folder / f'{stem}.mdx.normalization.json'), {})
                     if target_current else {})
    lines = [f'Input: {source.name}', f'Export: {row["status"]}',
             'Export success means files generated; native playback/display is not tested.',
             f'Route: {conversion.get("chip_projection", "unmeasured")}',
             f'Compiler: {row.get("compiler", "unmeasured")}']
    try:
        stats = source_statistics(source)
        lines.append(f'Source duration: {stats["samples"]} samples / '
                     f'{stats["samples"] / 44100:.6f} s (one stream pass; loops not expanded)')
        if stats['opm_used']:
            lines.extend([f'Source OPM register writes: {stats["opm_writes"]}',
                          f'OPM 0x08 writes: {stats["writes"]}; nonzero masks (Key-On requests) '
                          f'{stats["on"]}; zero masks (Key-Off requests) {stats["off"]}',
                          f'OPM operator edges: rising {stats["rising"]}; falling {stats["falling"]} '
                          '(4 operators/channel; repeated requests are not new edges)'])
        else:
            lines.append('Source OPM Key-On/Off: not applicable (no actual OPM writes; '
                         'for PSG inputs, PSG has no OPM Key-On signal)')
    except (OSError, ValueError, struct.error) as error:
        lines.append(f'Source statistics: unavailable ({str(error)[:180]})')
    census = (optional('Compiled MDX command statistics', lambda: _encoded_command_summary(folder, stem),
                       'Compiled MDX command statistics: unmeasured')
              if target_current and (folder / f'{stem}.mdx').is_file()
              else 'Compiled MDX command statistics: unmeasured (no current compiled artifact)')
    lines.extend([census,
                  'OPM pitch reproduction: unmeasured (no independent source/target pitch comparison)'])
    if normalization:
        lines.append('Note normalization: ' + str(normalization.get('status', 'see normalization JSON')) +
                     '; ' + str(normalization.get('reason', ''))[:180])
        selected = normalization.get('selected', {})
        if isinstance(selected, dict) and selected.get('tick_microseconds'):
            lines.append(f'Selected MDX clock: {selected["tick_microseconds"]} us/tick; '
                         f'tempo byte {selected.get("tempo_byte", "unknown")}; '
                         'nominal target clock, not measured driver interrupt load')
    if assessment:
        lines.extend([f'PCM policy: {assessment.get("policy", "unknown")}; '
                      f'projection {assessment.get("assessment_status", "unknown")}; '
                      f'runtime {assessment.get("validation_status", "unknown")} '
                      f'({assessment.get("validation_run", "not_run")})',
                      f'PCM target: {assessment.get("target_profile", "unknown")}',
                      'PCM encoded payload: ' + (optional('PCM payload',
                          lambda: _pdx_payload_check(folder, stem, folder / f'{stem}.pdx'), 'unmeasured')
                          if pcm_current else 'unmeasured (no current generated PCM pair)')])

        def frequencies():
            rows = _csv(folder / f'{stem}.pcm_projection.csv')
            exact = 0
            for item in rows:
                index = int(item['mdx_frequency'])
                exact += (0 <= index < len(RATES) and Fraction(int(item['rate_num']),
                          int(item['rate_den'])) == RATES[index])
            return (f'PCM frequency mapping: {exact}/{len(rows)} playback spans exact (rational Hz)' if rows
                    else 'PCM frequency mapping: unmeasured (no projection rows)')

        lines.append(optional('PCM frequency mapping', frequencies, 'PCM frequency mapping: unmeasured')
                     if pcm_current else 'PCM frequency mapping: unmeasured (no current projection rows)')
        lines.append(f'PCM playback spans: {timing.get("pcm_playback_count", "unmeasured")}; '
                     f'max boundary error: {timing.get("pcm_max_abs_timing_error_samples", "unmeasured")} '
                     'source samples (44100 Hz); actual decoder consumption unmeasured')
        for label, key in (('Known losses', 'known_losses'), ('Unverified', 'unverified_items'),
                           ('Failures', 'unexpected_mismatches')):
            items = assessment.get(key, [])
            lines.append(optional(label, lambda: f'{label}: {len(items)}; {_codes(items)}',
                                  f'{label}: unavailable'))
        reasons = optional('Blocked reasons', lambda: list(dict.fromkeys(
            str(reason) for reason in assessment.get('block_reasons', []))), [])
        for reason in reasons[:3]:
            lines.append('Blocked: ' + reason.replace('\n', ' ')[:260])
        if len(reasons) > 3:
            lines.append(f'Blocked: +{len(reasons) - 3} other reasons; see assessment JSON')
    else:
        lines.append('PCM assessment: not available / no PCM projection')
    if row.get('detail'):
        lines.append('Detail: ' + row['detail'].replace('\n', ' ')[:320])
    lines.extend(unavailable)
    path = folder / f'{stem}.report.txt'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path
