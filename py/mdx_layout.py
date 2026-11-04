"""Layout fallback for MDX compilations that overflow 16-bit offsets.

The stock mmlx layout writes track segments in channel order with the
tone block last, so a dense song fails with "offset exceeds the
maximum 0xfffe" even when every track is individually small. Players
follow the header pointers (tone data offset first, then one offset
per track), so segments may be physically reordered. This module is
used only after the stock compile fails with that error: it
recompiles track subsets (each small enough for the stock layout),
then assembles one MDX with track A first (parsers derive the
header's track count from A's offset, so A must start immediately
after the table), the tone block next, the remaining tracks in
ascending size order and the largest of them last. Every start
offset then fits provided total - largest_non_A <= 0xfffe.

Two compile routes share the assembly: the plain --compile-only
route (assemble_mdx) and the typed PCM route (assemble_pcm_mdx),
whose plan-built PCM track is present in every subset compile and
is carried over byte-exact like any other segment.

The assembled file is verified with the generator's own inspectors:
the tone table must match a subset compile exactly, and each
track's command sequence must match the subset compile it came
from. Any mismatch aborts the fallback instead of publishing a
suspect file.
"""
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

MAX_OFFSET = 0xFFFE
STUB = b'\xf1\x00'
PCM_MODE = b'\xe8'
TRACK_LINE = re.compile(r'^([A-P]) ')
SUBSET_MML_CAP = 110_000


class LayoutError(RuntimeError):
    pass


def split_mml(text):
    """Split MML text into shared head lines and per-track lines."""
    head = []
    tracks = {}
    for line in text.splitlines():
        match = TRACK_LINE.match(line)
        if match:
            tracks.setdefault(match.group(1), []).append(line)
        else:
            head.append(line)
    return head, tracks


def plan_subsets(tracks, passenger=None):
    """Greedy-pack track letters into subsets under an MML byte cap.

    With a passenger letter, every subset also carries that track:
    the typed PCM compile rejects any FM document whose maximum
    end_tick differs from the plan's, so each subset compile must
    contain the longest track even when it owns other tracks.
    """
    sizes = {letter: sum(len(line) + 1 for line in lines)
             for letter, lines in tracks.items()}
    order = sorted(tracks, key=lambda letter: -sizes[letter])
    base = [passenger] if passenger else []
    base_size = sizes.get(passenger, 0)
    subsets = []
    for letter in order:
        if letter == passenger:
            continue
        for subset in subsets:
            if subset[1] + sizes[letter] <= SUBSET_MML_CAP:
                subset[0].append(letter)
                subset[1] += sizes[letter]
                break
        else:
            subsets.append([base + [letter], base_size + sizes[letter]])
    if not subsets and passenger:
        subsets.append([base, base_size])
    return [letters for letters, _ in subsets]


def _parse_mdx(data):
    """Return (prefix, tone_offset, entries, tone, segments) of an MDX."""
    marker = data.index(0x1A)
    pdx_end = data.index(0, marker + 1)
    base = pdx_end + 1
    tone_offset = struct.unpack('>H', data[base:base + 2])[0]
    first = struct.unpack('>H', data[base + 2:base + 4])[0]
    count = (first - 2) // 2
    words = struct.unpack(f'>{count + 1}H', data[base:base + 2 * (count + 1)])
    entries = list(words[1:])
    tone = data[base + tone_offset:]
    bounds = sorted({o for o in entries if o != 0xFFFF} | {tone_offset})
    segments = {}
    for index, offset in enumerate(entries):
        if offset == 0xFFFF:
            continue
        end = min((b for b in bounds if b > offset), default=len(data) - base)
        segments[index] = data[base + offset:base + end]
    return data[:base], tone_offset, entries, tone, segments


def _run(command, timeout):
    run = subprocess.run(command, capture_output=True, text=True,
                         encoding='utf-8', errors='replace', timeout=timeout)
    if run.returncode:
        raise LayoutError(run.stdout + run.stderr
                          or f'Generator exited with {run.returncode}')
    return run


def _inspect(generator, mdx, mode, timeout):
    with tempfile.NamedTemporaryFile('r', suffix='.csv', delete=False) as handle:
        out = Path(handle.name)
    try:
        _run([str(generator), mode, str(mdx), str(out)], timeout)
        return out.read_text(encoding='utf-8')
    finally:
        out.unlink(missing_ok=True)


def _track_label(index):
    """Census label for a track index (A-H, then P-W for PCM tracks)."""
    return chr(65 + index) if index < 8 else chr(ord('P') + index - 8)


def _command_sequences(csv_text):
    """Map track letter -> [(kind, opcode, operands, ticks), ...]."""
    sequences = {}
    for line in csv_text.splitlines()[1:]:
        if not line:
            continue
        track, _, kind, opcode, operands, ticks = line.split(',', 5)
        sequences.setdefault(track, []).append((kind, opcode, operands, ticks))
    return sequences


def _segment_byte_lengths(csv_text):
    """True byte length per track label from a command census.

    The stock serializer zero-fills the body buffer, so the last
    track's raw span can absorb a padding gap before the tone
    block. Census byte lengths (opcode + operands per command)
    give each track's exact extent.
    """
    lengths = {}
    for line in csv_text.splitlines()[1:]:
        if not line:
            continue
        track, _, _, _, operands, _ = line.split(',', 5)
        lengths[track] = lengths.get(track, 0) + 1 + len(operands) // 2
    return lengths


def _assemble(text, output, *, generator, timeout, workdir, compile_subset,
              passenger=None, mdx_workdir=None):
    """Assemble one MDX from subset compiles of the given MML text.

    compile_subset(mml_path, mdx_path) must produce a stock-layout MDX
    containing every track (stubs for inactive ones). Segment indices
    that are not song tracks yet are non-stub in a subset compile (the
    plan-built PCM track) are detected on the first subset and carried
    over byte-exact from every subset compile. Subset MDX files land
    in mdx_workdir when given (the PCM compile loads the PDX beside
    its output, so there they must sit beside the final output) and
    are removed once the assembled file verifies.
    """
    head, tracks = split_mml(text)
    if not tracks:
        raise LayoutError('No track lines found in MML')
    letters = sorted(tracks, key=lambda letter: ord(letter))
    song_indices = {ord(letter) - 65 for letter in letters}
    workdir = Path(workdir)
    mdx_workdir = Path(mdx_workdir) if mdx_workdir else workdir
    segments = {}
    extra_indices = None
    tone = None
    prefix = None
    subset_files = []
    for number, subset in enumerate(plan_subsets(tracks, passenger)):
        sub_mml = workdir / f'subset{number}.mml'
        sub_mdx = mdx_workdir / f'subset{number}.mdx'
        lines = list(head)
        for letter in letters:
            if letter in subset:
                lines.extend(tracks[letter])
        sub_mml.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        compile_subset(sub_mml, sub_mdx)
        sub_prefix, _, _, sub_tone, sub_segments = _parse_mdx(sub_mdx.read_bytes())
        byte_lengths = _segment_byte_lengths(
            _inspect(generator, sub_mdx, '--inspect-commands', timeout))
        for index, segment in list(sub_segments.items()):
            exact = byte_lengths.get(_track_label(index))
            if exact is not None and exact < len(segment):
                sub_segments[index] = segment[:exact]
        if prefix is None:
            prefix, tone = sub_prefix, sub_tone
            extra_indices = {index for index, segment in sub_segments.items()
                             if segment != STUB and index not in song_indices}
        elif sub_prefix != prefix or sub_tone != tone:
            raise LayoutError('Subset compiles disagree on header or tone data')
        active = {ord(letter) - 65 for letter in subset} | extra_indices
        for index in active:
            if index not in sub_segments:
                raise LayoutError(f'Track {chr(65 + index)} missing from subset compile')
            if index in segments and segments[index] != sub_segments[index]:
                raise LayoutError('Track segment differs between subset compiles')
            segments[index] = sub_segments[index]
        subset_files.append((sub_mdx, active))

    extended = bool(extra_indices) or any(index >= 9 for index in song_indices)
    track_count = 16 if extended else 9
    # Track A carries the PCM-mode marker in extended documents.
    first = segments.get(0, STUB)
    if extended and not first.startswith(PCM_MODE):
        segments[0] = PCM_MODE + first
    elif not extended and first.startswith(PCM_MODE):
        segments[0] = first[len(PCM_MODE):]

    present = {index: segments.get(index, STUB) for index in range(track_count)}
    outside = [index for index in segments if index >= track_count]
    if outside:
        raise LayoutError(f'Tracks outside the header form: {outside}')

    # Placement: A first (its offset defines the header size for
    # parsers), then the tone block, then the other tracks in
    # ascending size order so the largest starts last.
    others = sorted((index for index in present if index != 0),
                    key=lambda index: len(present[index]))
    body_order = ['A', 'tone'] + others
    blocks = {'tone': tone, 'A': present[0]}
    blocks.update({index: present[index] for index in others})
    header_size = 2 + 2 * track_count
    offsets = {}
    position = header_size
    for name in body_order:
        if name == 'tone':
            tone_offset = position
        elif name == 'A':
            offsets[0] = position
        else:
            offsets[name] = position
        position += len(blocks[name])
    if tone_offset > 0xFFFF or any(o > MAX_OFFSET for o in offsets.values()):
        raise LayoutError(
            f'Placement still overflows: total {position}, '
            f'max start {max([tone_offset, *offsets.values()])}')

    words = [tone_offset] + [offsets[index] for index in range(track_count)]
    assembled = bytearray(prefix)
    assembled += struct.pack(f'>{len(words)}H', *words)
    for name in body_order:
        assembled += blocks[name]
    output = Path(output)
    output.write_bytes(bytes(assembled))

    # Verify against the subset compiles with the generator's inspectors.
    reference_tones = _inspect(generator, subset_files[0][0], '--inspect-mdx', timeout)
    if _inspect(generator, output, '--inspect-mdx', timeout) != reference_tones:
        raise LayoutError('Assembled tone table differs from subset compile')
    expected = {}
    for sub_mdx, active in subset_files:
        sequences = _command_sequences(
            _inspect(generator, sub_mdx, '--inspect-commands', timeout))
        for index in active:
            expected[_track_label(index)] = sequences.get(_track_label(index), [])
    actual = _command_sequences(
        _inspect(generator, output, '--inspect-commands', timeout))
    for letter, sequence in expected.items():
        got = actual.get(letter)
        if extended and letter == 'A':
            # The PCM-mode marker is a layout property of the extended
            # form, not track content: subset compiles may or may not
            # carry it depending on the route that produced them.
            if sequence and sequence[0][0] == 'PcmMode':
                sequence = sequence[1:]
            if got and got[0][0] == 'PcmMode':
                got = got[1:]
        if got != sequence:
            raise LayoutError(f'Assembled track {letter} commands differ')
    for sub_mdx, _ in subset_files:
        sub_mdx.unlink(missing_ok=True)
    return {'layout_fallback': True, 'tracks': len(letters),
            'subsets': len(subset_files), 'size': output.stat().st_size,
            'max_start_offset': max([tone_offset, *offsets.values()])}


def validate_assembled_layout(raw, *, active_tracks=('P',)):
    """Envelope check for a fallback-assembled extended MDX.

    The stock validator assumes offsets ascend with track index;
    the assembled layout deliberately permutes them. What must hold
    instead: sixteen tracks, the PCM-mode marker on track A, every
    start offset within the 16-bit limit, and no undeclared PCM
    track carrying content.
    """
    _, tone_offset, entries, _, segments = _parse_mdx(raw)
    if len(entries) != 16:
        raise LayoutError('Assembled MDX does not have 16 tracks')
    if tone_offset > 0xFFFF or any(o > MAX_OFFSET for o in entries):
        raise LayoutError('Assembled MDX has an out-of-range start offset')
    if not segments.get(0, b'').startswith(PCM_MODE):
        raise LayoutError('Assembled MDX lacks the initial PCM-mode marker')
    for index in range(8, 16):
        if _track_label(index) in active_tracks:
            continue
        if segments.get(index, STUB) != STUB:
            raise LayoutError('Assembled MDX has an undeclared active PCM track')


def assemble_mdx(mml_path, pdx_path, output, *, generator, timeout=1200):
    """Assemble an oversize song's MDX via --compile-only subsets."""
    mml_path = Path(mml_path)
    text = mml_path.read_text(encoding='utf-8')

    def compile_subset(sub_mml, sub_mdx):
        _run([str(generator), '--compile-only', str(sub_mml), str(sub_mdx)], timeout)

    with tempfile.TemporaryDirectory(prefix='mdx-layout-') as temporary:
        work = Path(temporary)
        if pdx_path is not None and Path(pdx_path).is_file():
            shutil.copyfile(pdx_path, work / Path(pdx_path).name)
        return _assemble(text, output, generator=generator, timeout=timeout,
                         workdir=work, compile_subset=compile_subset)


def _timing_total(sequence):
    """Track ticks with finite repeats expanded.

    Mirrors the generator's own timing walk: a repeat body counts
    (count - 1) full passes plus a final pass that stops at the
    escape point when one exists. A plain census sum undercounts
    any track that uses repeats.
    """
    total = 0
    stack = []
    for kind, _opcode, operands, ticks in sequence:
        if kind in ('Note', 'Rest'):
            total += int(ticks)
        elif kind == 'LoopStart':
            stack.append([total, int(operands[0:2], 16), None])
            total = 0
        elif kind == 'LoopEscape':
            if stack and stack[-1][2] is None:
                stack[-1][2] = total
        elif kind == 'LoopEnd':
            before, count, escape = stack.pop()
            last = escape if escape is not None else total
            total = total * (count - 1) + last + before
    return total


def _probe_track_ticks(generator, workdir, head, tracks, timeout):
    """Total ticks per track from solo compiles (exact, loop-aware)."""
    totals = {}
    for letter in sorted(tracks):
        probe_mml = workdir / f'probe_{letter}.mml'
        probe_mdx = workdir / f'probe_{letter}.mdx'
        probe_mml.write_text('\n'.join(head + list(tracks[letter])) + '\n',
                             encoding='utf-8')
        _run([str(generator), '--compile-only', str(probe_mml), str(probe_mdx)],
             timeout)
        sequences = _command_sequences(
            _inspect(generator, probe_mdx, '--inspect-commands', timeout))
        totals[letter] = _timing_total(sequences.get(letter, []))
    return totals


def assemble_pcm_mdx(fm_mml_path, manifest_path, output, *, generator, timeout=180):
    """Assemble an oversize typed-PCM MDX via --compile-pcm subsets.

    Subset compiles run beside the manifest so its sample references
    resolve exactly as in the stock compile. The tick-longest FM
    track rides along in every subset: the PCM compile requires the
    FM document's maximum end_tick to equal the plan's on every run,
    and text size does not predict tick length (long tied notes are
    compact), so the passenger is chosen from solo-compile probes.
    """
    fm_mml_path, manifest_path = Path(fm_mml_path), Path(manifest_path)
    text = fm_mml_path.read_text(encoding='utf-8')
    work = manifest_path.parent
    head, tracks = split_mml(text)
    totals = _probe_track_ticks(generator, work, head, tracks, timeout)
    passenger = max(totals, key=lambda letter: totals[letter])

    def compile_subset(sub_mml, sub_mdx):
        _run([str(generator), '--compile-pcm', str(sub_mml),
              str(manifest_path), str(sub_mdx)], timeout)

    return _assemble(text, output, generator=generator, timeout=timeout,
                     workdir=work, compile_subset=compile_subset,
                     passenger=passenger,
                     mdx_workdir=Path(output).parent)
