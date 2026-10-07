# MDX note lengths and optional correction

```sh
python vgm2mml.py input.vgm --outdir outputs/input --normalize-lengths --dump-passes
```

Each native track begins with `/* Track A */` through `/* Track H */`.
Structured and legacy note rendering use exact MDX duration values without
requiring normalization. The whole-note basis is 192 ticks. Supported values
include `1`, `2`, `3`, `4`, `6`, `8`, `12`, `16`, `24`, `32`, `48`, `64`, `96`,
`128`, `192` and representable one/two-dot values. A duration of 13 ticks uses
`%13`. Long notes use whole-note chunks joined by ties; a held slice also ends
with a tie so that a control change does not create a new attack.

This formatting preserves tick lengths. `--normalize-lengths` is a separate,
opt-in timing correction and requires `--notation structured` (the default).
It runs after native analysis and before note/trajectory keys and loop planning.
Reference MML is never an input. MDX macroization remains outside the task.

## Reuse and target boundary

`py/opm_note_normalization.py` feeds native OPM rising Key edges into the shared
MGSDRV estimator in `py/note_normalization.py`. The current estimator uses
clustered attacks, at least 16 anchors, candidate tempos 80..200, and 12/6-step
grids. It requires at least 95% anchor coverage. Its correction tolerance is
the smaller of 735 samples and a quarter of the smallest usable inter-onset
interval. These are estimator heuristics, not YM2151 timing specifications.

The fitted tempo/grid nominates one actual MDX timer multiplier, rounded from
the fitted sample period per score step. Every target boundary then uses the
existing nearest absolute MDX tick conversion on that timer. The source origin
remains sample zero. The fitted phase and grid are recorded but are not used to
snap individual attacks. MGSDRV gate inference, `q` generation and short-state
pruning are specific to that compatibility target and are not applied to OPM.

The candidate is accepted only if all Segment starts/ends, control writes,
Key edges, song end and valid declared VGM loop boundaries stay within the
correction bound measured against the actual MDX timer. Every positive interval
between these source boundaries must stay positive. Same-time control order,
source event IDs and register values remain intact. An invalid declared loop,
unreliable fit, unrepresentable timer, excessive correction or collapsed
interval rejects the candidate for the whole song.

Raw/state traces and native Segment fields retain observed values. Corrected
target ticks and source identifiers remain available for inspection. Normalized
note and control-trajectory keys go into the existing shared loop planner;
loop expansion must equal the uncompressed corrected target stream. A more
regular duration pattern can enable repeated units, but no loop-count increase
is promised for an individual song.

## Short relative setters

Target compaction after loop planning also chooses short relative octave and
volume commands. From a known value, a one/two-step change uses `<`/`>` or
`(`/`)` if its length is no greater than the absolute token. Equal values keep
the existing redundant-setter omission. Larger changes and unknown initial
values retain absolute commands. This runs with or without normalization.

The inspected MSX implementation has two rules: the current
`compact_state_token` selects only a one-step relative change, while older
MGS helpers allow up to three steps. MDX uses the user's requested maximum of
two characters. The coarse `v0..15` and fine `@v0..127` modes are tracked
separately; changing modes retains the first absolute command. In the tested
mmlx 0.2.0 compiler, `@vN` encodes `255-N`, and each relative volume step changes
that encoded value by one with the appropriate direction. This is target
volume state, not an inferred change to source operator levels.

Every finite-loop entry clears the compactor's known state so its first setter
is absolute for both initial and repeated entry. Voice loading and raw tone/TL
writes invalidate cached volume/pan state. Raw pitch writes retain their
explicit register spelling and do not alter the compiler's octave setting.
Before/after replacements and byte-saving estimates are recorded with action
`relative_setter` in `*.mdx.structure.compaction.csv`; the uncompacted MML
retains absolute setters. Two volume steps save text against `@vN` but can have
the same compiled byte cost as an absolute volume command. Octave syntax is
resolved by the compiler, so shorter octave text does not itself save MDX bytes.

Independent compiler/player comparisons cover octave changes, both volume
scales and their limits, mixed modes, nested repeats with different entry/end
values, held controls and raw writes followed by voice loading. Effective
state, Key timestamps/masks and the end sample must match the absolute version;
loop-token equality alone cannot establish relative-state equivalence.

## Reports

With the flag, `<stem>.mdx.normalization.json` records applied/unchanged status,
the reason, original and nominated MDX timing, fitted estimator parameters,
actual worst correction, boundary kinds and event IDs. Rejected candidates
retain collision count and up to ten collision examples where available.

With `--dump-passes`:

- `<stem>.mdx.normalization.csv` records source controls and end/loop boundaries,
  before/candidate ticks and sample times, errors and the acceptance status.
  Candidate columns remain candidate evidence if correction is rejected.
- `<stem>.mdx.before.normalize.mml` records the conventional target when
  correction is applied; the JSON then includes before/after structure counts.
- Existing trace, Segment, control, structure and timing dumps remain available.
  Integrated Segment-to-target membership may change while native fields do not.
  `score_clock_inference` is explicitly the conventional, pre-normalization fit;
  the chosen target clock is recorded in the main timing fields.

A new run clears old normalization artifacts first. A rejected candidate does
not leave an old successful before-MML behind. If fitting abstains before a
candidate exists, only the normalization JSON is written. No output is written
into source fixtures when a separate `--outdir` is supplied.

## Verification

```sh
python scripts/verify_opm_mdx_roundtrip.py input.vgm \
  --outdir outputs/input-check --normalize-lengths
```

The external check still requires exact projected Key edges, effective state
and target end time. With accepted normalization it uses the recorded source
correction bound for the explicit source-timing comparison. Conventional output
and rejected correction retain the existing six-sample source tolerance.
Normalization therefore proves a bounded timing change, rather than exact
source-time equivalence. The exact-formatting replay tests separately compare
old step chunks and named durations, including held controls and nested ties.
See [validation notes](../field_notes/2026-10-07_mdx_note_lengths.md).
