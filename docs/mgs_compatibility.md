# MGSDRV compatibility

Japanese original: [mgs_compatibilityJ.md](mgs_compatibilityJ.md).

Explicitly select `--target mgs` for the inherited PSG/SCC/OPLL path.

# vgm2mml
Generates MGSDRV MML from PSG/OPLL/SCC VGM files.
MGSDRV MML can be copied and pasted into https://msxplay.com/editor.html for playback.

## Feature overview
- Analyzes VGM (MSX-Music / SCC) and automatically generates MGSDRV-format MML\
- Outputs MML faithful to register accesses

## Command list

| Command | Supported chips | Overview |
|----------|----------|------|
| `vgm2mml.py` | PSG, OPLL, SCC | Outputs MGSDRV MML |
| `py/vgm_reader.py` | PSG, OPLL, SCC | Outputs input logs/traces |

---

## vgm2mml.py

### Usage
```bash
python vgm2mml.py --target mgs [-h] [--outdir OUTDIR] [--dump-passes] [--debug] [--raw-ticks] vgm
```

### Basic example
```
python vgm2mml.py --target mgs stem.vgm
```

Example output:
```
stem.mml
```

### Options
| Option | Description |
|-----------|------|
| `--outdir OUTDIR` | Specify the output directory for the MML file |
| `--sync-min-gap N` | Minimum spacing between sync comments (in output MML steps; default 1000). Set 0 to show every sync point that does not split loops/macros. Start and end are always shown |
| `--dump-passes` | Save event logs/traces, PASS0-3, PSG/SCC Segments, and SCC waveform CSVs |
| `--vgmticks` | Include original VGM sample times before rounding in trace/pass/Segment output. Also specify `--dump-passes` to save Segments |
| `--debug` | Output debug files |
| `--raw-ticks` | Output note lengths in `%` tick format (e.g. `c%%N`); note-value notation is the default |
| `--normalize-lengths` | Infer a shared note-length basis from OPLL attack intervals and correct lengths/gates. Disabled by default. Songs that cannot use it retain conventional output. Incompatible with `--raw-ticks` |
| `--legacy-loops` | Disable reversible PSG/SCC/OPLL loop structuring and use conventional loop/envelope processing |
| `--legacy-macros` | Disable the default macro enhancement that searches inside loops and use conventional macro processing |
| `--enhance-macros` | Explicitly enable macro enhancement (currently the default). With `--dump-passes`, save selected macro CSVs and character counts for candidate plans |

PSG/SCC processing is divided into event CSV → Segment → MML stages.
See [PSG/SCC Segment pipeline](psg_scc_segments.md) for the structure and intermediate formats.
Step comments in merged MML are inserted automatically where note/rest boundaries align across all playing channels.
PSG/SCC omit rest-only channels and unnecessary settings during rests, and extract volume trajectories at constant pitch into software envelopes.
With `--dump-passes`, extracted intervals are saved in `*.target_notes.csv`, and per-chip MML after application in `*.target.mml`.
See [sync points](mml_sync.md) for the specification and output examples.
Run tests at the repository root with `python -m unittest discover -s tests/scripts -v`.

### Note-length correction

```bash
python vgm2mml.py --target mgs tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm \
  --outdir outputs/sample-normalized --normalize-lengths --dump-passes
```

Correction happens during MML generation without rewriting original `vgmticks` or Segment CSVs.
The note-length basis and safety are assessed automatically for each song; when correction cannot be applied,
all parts retain conventional output. OPLL rhythm also uses the shared basis.
PSG/SCC note lengths are converted to the basis inferred from OPLL, while software envelope
frame settings are preserved. **PSG/SCC-only songs currently receive no correction.**

The console and `<stem>.normalization.json` record `applied` or
`unchanged`, together with the reason. With `--dump-passes`,
MML before correction, corrected-note CSVs, and loop decision CSVs are also saved.
See the [note-length correction specification](note_normalization.md) for details.

### Batch conversion and MGS compilation

```bash
# Conventional conversion
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs/opll

# Enable note-length correction for comparison
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll \
  --outdir outputs/mgs/normalize-lengths/opll --normalize-lengths
```

Recursively converts VGM/VGZ files beneath the input directory and compiles them to MGS,
preferring native `mgsc` on PATH. Specify an executable with `--mgsc PATH`.
Each song retains its MML and `convert.log`/`compile.log`; processing continues to the next song after a failure.
Check each song's `convert.log` and `<stem>.normalization.json` to see whether correction was applied.

`results.csv`/`results.json` record compilation results (`success`, `buffer_error`, etc.) and,
for successfully compiled songs, OPLL melodic KEYON totals, shortages, and excesses.
KEYON comparison requires Node.js and libkss-js. Specify
`--skip-keyon-counts` to omit comparison. Unperformed comparisons remain blank and are not treated as zero.
Use separate output directories for conventional and corrected runs to compare results.
See [batch execution](../scripts/README.md) for dependencies and details.

---

## Limitations
- The values in `#alloc` are character counts per channel. They may need adjustment to fit the buffer sizes after compilation

## Notes
MGSDRV MML requires **the total buffer size of all channels after compilation to be within 16 KB**. However, **this script does not account for that limit**.\
If generated MML is too large, adjustments such as the following may be needed:
- Manually adjust `#alloc` values\
- Use macros to reduce data size\

## License
MIT License

---


# vgm2mml
A script that converts VGM files for MSX-Music (PSG, OPLL) and SCC into MML for MGSDRV.
The generated MML can be copied and pasted directly into https://msxplay.com/editor.html for playback.

## Overview
- Automatic conversion: Parses VGM (MSX-Music / SCC) and generates MGSDRV-style MML
- Register-accurate output: Produces MML that closely reflects the original register writes

## Command Overview

| Command | Supported Chips | Description |
|---------|-----------------|-------------|
| `vgm2mml.py` | PSG, OPLL, SCC | Outputs register-accurate MML |

---

## vgm2mml.py

### Usage
```bash
python vgm2mml.py --target mgs [-h] [--outdir OUTDIR] [--dump-passes] [--debug] [--raw-ticks] vgm
```

### Example
```
python vgm2mml.py --target mgs stem.vgm
```
The output will be saved in `outputs/<stem>/<stem>.mml`.

### Options
| Option | Description |
|--------|-------------|
| `--outdir OUTDIR` | Specify the output directory for the MML file |
| `--dump-passes` | Output intermediate files |
| `--debug` | Output debug files |
| `--raw-ticks` | Output note lengths as raw `%` ticks (e.g. `c%%N`) instead of note-value notation |
| `--normalize-lengths` | Infer a shared musical clock from OPLL attacks and correct target lengths/gates. Disabled by default; uncertain/unsafe songs retain conventional output. Incompatible with `--raw-ticks` |

---

## Limitations
- The value set in `#alloc` is the character count per channel. You may need to adjust it to fit the buffer size after compilation.

## Notes
MGSDRV MML must satisfy the constraint that the total buffer size of all channels after compilation is within 16 KB.
However, this script does not take that limitation into account.

If the generated MML is too large, you may need to:
- Manually adjust the `#alloc` values
- Use macros to reduce data size

## License
MIT License

### Declared VGM loop inspection

`--dump-passes` (or `--debug`) writes `<stem>.vgm.loop.csv` with the
header loop address, declared sample count, observed start/end samples and
validation status. This records the source loop without repeating playback,
resetting chip state or adding KEYONs. Infinite MML loops and Segment loop
annotations are not emitted yet. See [VGM loop metadata](vgm_loop.md).

### OPLL Segment inspection

`--dump-passes` also writes `<stem>.opll.segments.csv`, including melody and
rhythm channels before target voice assignment. See `docs/opll_rhythm.md`.

The same option writes `.opll.rhythm.groups.csv`, `.opll.rhythm.patterns.csv`
and `.opll.rhythm.occurrences.csv` for lossless tick grouping and exact repeats.
These analysis tables do not yet change the generated MML.

The main converter now renders OPLL rhythm on track `f`, including simultaneous
hits, per-instrument volumes and exact finite repeats. Rhythm participates in
shared sync marks and the 15000 allocation pool. Source timing still uses the
existing 60 Hz analysis; no libkss timing correction is applied.

Main OPLL target output uses MGSDRV ROM voices @0..@14 and explicit user
voice definitions starting at @16. Long notes use exact lengths and tied
continuations when split. --dump-passes includes `.opll.target_notes.csv`
with the selected target voice and source patch bytes for each sounding Segment.

## Rhythm notation optimization

Final rhythm MML omits redundant instrument-volume commands and selects a
single default length when it reduces text size. Exact patterns still come
from Segment analysis; this pass does not discover new loops or macros.
`--dump-passes` retains `.opll.rhythm.before.target.mml`,
`.opll.rhythm.after.target.mml`, and `.opll.rhythm.optimization.csv`.
See docs/opll_rhythm.md for scope and validation.

## Melody pattern analysis

`--dump-passes` also writes per-chip `.melody.patterns.csv`,
`.melody.occurrences.csv` and `.melody.markings.csv`. These describe exact
adjacent Segment repeats and retain source-row references. Eligible candidates become finite MML loops without changing expanded commands; see [melody pattern analysis](melody_patterns.md) for equality
rules, reconstruction and the limits of these loop candidates.

### Output metadata and default artifacts

By default, `vgm2mml.py` produces only `<stem>.mml`. Both the player metadata
`;[name=<stem> lpf=1]` and `#title` use the input filename without its extension.
Use `--name "Player name"` and `--title "Song title"` to override them independently;
These options do not rename the output.
`--dump-passes` retains analysis artifacts; `--debug` retains legacy MML variants.

```sh
python vgm2mml.py --target mgs song.vgm --outdir outputs/song --name song --title "Song Title"
```

With `--dump-passes`, `.performed.units.csv` and `.performed.loops.csv` expose
complete-note/percussion candidates and nested loops. Segment CSVs also carry
performed-unit IDs and hierarchy paths. PSG percussion grouping is conservative:
noise-containing intervals with a trailing rest are candidates, not inferred
original driver macros. Exact command-preserving nested loops support PSG/SCC
and OPLL melody; see `docs/melody_patterns.md` for limits.
# Automatic MML macros

Normal target output now shares repeated PSG, SCC and OPLL melodic command
sequences, including OPLL rhythm, through MGSDRV macros. Candidates are ranked by source-character
savings across tracks (no fixed chip priority). Existing synchronization marks,
loops and allocation remain intact. Up to 32 non-recursive definitions are
emitted, only when the resulting file is smaller. Rhythm and melody use separate
candidate pools to retain their distinct syntax. Macros reduce source length, not
necessarily compiled track memory. `--dump-passes` retains the pre-macro chip
outputs; the merged MML contains the final definitions and calls.
# Batch MGS compilation

Batch regression also exports each compiled MGS through libkss and reports
OPLL melodic KEYON totals, shortages and excesses in `results.csv`/`results.json`.
Use `--skip-keyon-counts` to compile without playback comparison, or
`--libkss-module` to select the installed playback module. See
[batch dependency setup](../scripts/README.md).

Use `python scripts/batch_vgm_to_mgs.py INPUT_DIR --outdir OUTPUT_DIR` to
recursively convert VGM/VGZ and compile MGS. Native `mgsc` on PATH is preferred;
use `--mgsc PATH` to select it explicitly. The mgsc-js fallback is also available.
Intermediate MML and per-file conversion/compiler logs are retained on failure,
and later inputs continue. Results are recorded in `results.csv`/`results.json`;
buffer allocations are not adjusted automatically after compiler failures.

```bash
# Conventional conversion
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs/opll

# Opt-in musical normalization; use a separate output tree for comparison
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll \
  --outdir outputs/mgs/normalize-lengths/opll --normalize-lengths
```

Each song's `convert.log` and `<stem>.normalization.json` report whether correction
was applied. Successful compilations also report source/export OPLL melodic
KEYON totals and per-channel count shortages/excesses summed over the song.
Unperformed comparisons have blank counts, not zeros. Compare conventional and
normalized `results.csv` files to inspect changes in `buffer_error` and counts.
See [setup and usage](../scripts/README.md).

# GD3 titles

Without `--title`, the converter reads VGM GD3 metadata and generates
`[System] Name(Release date) Title Author`. `--gd3-language ja` (default) prefers
Japanese with English fallback for each field; `--gd3-language en` reverses
that preference for track, game and author. System always uses the English
field (omitted if absent). Release date is language-independent. Full-width
ASCII in System and Release date is normalized to half-width. Missing fields omit their
delimiters; absent, empty or malformed GD3 falls back to the input stem.
Explicit `--title` always wins. Metadata name (`--name`) and filenames do not
change. Merged MML is Shift-JIS (CP932) for MSX/MGSDRV display. Characters
not representable in CP932 are replaced with `?`. Intermediate CSV remains UTF-8.

Generated titles are sanitized for MML syntax and limited to 240 CP932 bytes
(whole characters), with a warning on truncation. This is a conservative MGSC
physical-line safeguard, not a fixed MGS title-field size. MGS stores its title
as a variable-length CRLF-terminated text field. MGSC 1.11 probes accepted a
240-byte title and rejected 250 bytes with the emitted header syntax. The
explicit `--title` override is not automatically truncated.
# Manual allocation overrides

Use `--alloc "9=1800, a=3780, b=1480, c=2850, d=4750, f=600"` to override
selected channels in the final merged `#alloc`. Unspecified channels retain
their automatic allocations. Channel letters are case-insensitive; duplicate
channels and invalid/non-integer values are rejected. Overrides are applied
after formatting/macros and are not redistributed to enforce the default total
budget. Actual compiler capacity is still checked by MGSC.

`scripts/batch_vgm_to_mgs.py` also accepts `--alloc`, applying the same overrides
to every input in that batch. Per-chip intermediate MML remains unchanged.

## OPLL key-on count checks

Compare source and exported VGM key-on counts, or supply a CSV of VGM pairs
for regression. Reports contain per-VGM totals and per-channel count shortages/
excesses summed over the song, without a quality score or timing comparison.
See [OPLL key-on counts](../scripts/README.md).

### Compressed VGM input

Input is detected by its contents: gzip-compressed VGM is accepted even with a
`.vgm` extension, as well as `.vgz`. GD3 metadata uses the same decompressed bytes.

## Optional musical duration normalization

`--normalize-lengths` estimates a shared clock from native OPLL attacks and
projects note lengths/gates before loop extraction. Raw sample times and Segment
CSV evidence stay unchanged. Uncertain or unsafe material keeps conventional
output. Use `--dump-passes` to inspect correction and normalized loop CSVs.
Batch conversion accepts the same flag. It is disabled by default and cannot be
combined with `--raw-ticks`. OPLL rhythm uses the shared clock; PSG/SCC durations
are retimed using that OPLL-derived clock while software envelope frame lengths
stay unchanged. **PSG/SCC-only songs currently receive no normalization.**

```bash
python vgm2mml.py --target mgs tests/fixtures/public/psg_opll/msxplay.com/sample/sample.vgm \
  --outdir outputs/sample-normalized --normalize-lengths --dump-passes
```

Each song is checked automatically. `<stem>.normalization.json` reports `applied`
or `unchanged`, with the reason for abstaining; the console reports the same.
With `--dump-passes`, conventional target MML, corrected-note evidence and loop
decision CSVs are retained alongside native Segment dumps.
See [usage and limits](note_normalization.md)
and [sample/grider/sx01v measurements](../field_notes/2026-10-02_note_normalization_benchmark.md).

### Comparing compression methods

Reversible loop structuring for PSG/SCC/OPLL and enhanced macros for all chips are enabled by default.
For PSG/SCC, repetitions of notes preserving their volume trajectories are structured first, then shared
software envelopes are selected. Reference MML is not used as conversion input.
`--dump-passes` saves note-to-Segment mappings, loop candidates/structures/output decisions,
and envelope candidate occurrence counts before and after structuring.
To compare against conventional compression, specify
`--legacy-loops --legacy-macros` in either normal or batch conversion. Note-length correction remains
enabled only when `--normalize-lengths` is specified.

```bash
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs/default
python scripts/batch_vgm_to_mgs.py tests/fixtures/local_only/opll --outdir outputs/mgs/legacy --legacy-loops --legacy-macros
```

For OPLL, songs using rhythm output 6 melodic voices + rhythm (`#opll_mode 1`),
while songs with rhythm OFF output 9 melodic voices (`#opll_mode 0`).
