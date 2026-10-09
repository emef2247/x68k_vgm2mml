"""Frontend route selection; source decoders and target IR stay independent."""
from collections import Counter

from vgm_io import read_vgm_bytes, read_vgm_header
from vgm_timing import command_times


def normalization_enabled(requested, *, notation='structured', target='mdx'):
    if requested is None:
        return target == 'mdx' and notation == 'structured'
    if requested and target == 'mdx' and notation != 'structured':
        raise ValueError('MDX length normalization requires --notation structured')
    return requested


def inspect_source(source):
    """Inventory actual commands, including inaudible writes and stream setup."""
    raw = read_vgm_bytes(source)
    header = read_vgm_header(raw)
    chips, counts, first, unsupported, streams = set(), Counter(), {}, [], {}
    opll_key_on = scc_nonzero_volume = False
    banks = []
    for event in command_times(raw):
        cmd, pos = event.command, event.address
        counts[f'{cmd:#04x}'] += 1
        item = dict(command=f'{cmd:#04x}', address=pos, source_samples=event.vgmticks)
        chip = {0x54: 'opm', 0xa4: 'opm', 0xa0: 'psg', 0xd2: 'scc',
                0x51: 'opll', 0xb7: 'pcm'}.get(cmd)
        if chip:
            chips.add(chip)
            first.setdefault(chip, item)
            if cmd == 0xa4:
                unsupported.append(dict(item, reason='Second OPM instance is not supported'))
            elif cmd == 0x51:
                reg, value = raw[pos + 1:pos + 3]
                opll_key_on |= bool((0x20 <= reg <= 0x28 and value & 0x10)
                                   or (reg == 0x0e and value & 0x20 and value & 0x1f))
            elif cmd == 0xd2:
                scc_nonzero_volume |= raw[pos + 1] == 2 and bool(raw[pos + 3] & 15)
                if raw[pos + 1] not in (0, 1, 2, 3):
                    unsupported.append(dict(item, reason='SCC test/variant/instance writes are not supported'))
        elif cmd == 0x67:
            kind = raw[pos + 2]
            banks.append(dict(item, bank_type=f'{kind:#04x}'))
            if kind in (4, 0x44):
                chips.add('pcm')
                first.setdefault('pcm', item)
        elif 0x90 <= cmd <= 0x95:
            stream_id = raw[pos + 1]
            if cmd == 0x90:
                streams[stream_id] = raw[pos + 2]
            destination = streams.get(stream_id)
            if destination == 0x17:
                # Route to the existing PCM analyzer, which retains and rejects
                # these commands as unsupported_stream_control/data_bank.
                chips.add('pcm')
                first.setdefault('pcm', item)
            else:
                unsupported.append(dict(item, code='unsupported_stream_control',
                    reason='DAC Stream Control is not supported', stream_id=stream_id,
                    destination_chip=destination))
        elif cmd in (0x61, 0x62, 0x63, 0x64, 0x66) or 0x70 <= cmd <= 0x7f:
            continue
        else:
            unsupported.append(dict(item, reason='Unsupported source chip/stream command'))
    opm_offset = 0x30 if header['version'] >= 0x110 else 0x10
    opm_clock = int.from_bytes(raw[opm_offset:opm_offset + 4], 'little')
    opll_clock = int.from_bytes(raw[0x10:0x14], 'little') if header['version'] >= 0x110 else 0
    declarations = dict(opm=opm_clock, opll=opll_clock, psg=header['ay_clock_raw'],
                        scc=header['scc_clock_raw'], pcm=header['okim6258_clock_raw'])
    initialization = {}
    if 'opll' in chips and not opll_key_on:
        initialization['opll'] = dict(command_count=counts['0x51'],
            reason='Existing compatibility initialization: no melodic/rhythm Key-On; source commands retained')
    if 'scc' in chips and not declarations['scc'] and not scc_nonzero_volume:
        initialization['scc'] = dict(command_count=counts['0xd2'],
            reason='Existing compatibility initialization: SCC is undeclared and no nonzero volume is written')
    for chip in chips - {'pcm'} - initialization.keys():
        if not declarations[chip]:
            unsupported.append(dict(first[chip], reason=f'Used {chip.upper()} commands have no clock declaration'))
    return dict(used_chips=sorted(chips), declared_clocks=declarations,
                compatibility_initialization=initialization,
                unused_declarations=sorted(chip for chip, clock in declarations.items()
                                           if clock and chip not in chips),
                command_counts=dict(counts), first_use=first, data_blocks=banks,
                unsupported_commands=unsupported)


def select_mdx_route(usage, *, compatibility_target=None):
    if usage['unsupported_commands']:
        issue = usage['unsupported_commands'][0]
        raise ValueError(f"{issue.get('code', 'unsupported_source')}: {issue['reason']} "
                         f"({issue['command']} at {issue['address']:#x})")
    chips = set(usage['used_chips']) - usage['compatibility_initialization'].keys()
    if compatibility_target in ('opm', 'opm-additive'):
        if not chips or not chips <= {'psg', 'scc'}:
            raise ValueError('Compatibility --target opm/opm-additive requires PSG/SCC source commands')
        return 'psg-scc-to-opm'
    if chips and chips <= {'opm', 'pcm'}:
        return 'native-opm-pcm'
    if chips and chips <= {'psg', 'scc'}:
        return 'psg-scc-to-opm'
    if not chips and 'opll' in usage['used_chips']:
        raise ValueError('OPLL to MDX projection is not supported; use --target mgs for MGSDRV compatibility')
    if not chips:
        raise ValueError('Input contains no supported chip commands; clock declarations alone do not select a route')
    if chips == {'opll'}:
        raise ValueError('OPLL to MDX projection is not supported; use --target mgs for MGSDRV compatibility')
    raise ValueError('Unsupported MDX source combination: ' + ', '.join(sorted(chips)))
