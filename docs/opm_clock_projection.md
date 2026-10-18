# OPM clocks and MDX pitch correction

Japanese original: [opm_clock_projectionJ.md](opm_clock_projectionJ.md).

The MDX playback target is the X68000's 4,000,000 Hz YM2151. A VGM declaring a
different positive YM2151 clock is corrected at the target boundary when it uses
a single instance. Raw, State, and Segment clocks, timestamps, and KC/KF values
remain unchanged.

## Correction boundary and calculation

`opm_mdx.project_segments` is the shared entry point. Structured and legacy note
notation, registers notation with channel or conductor layouts, and the FM part
of mixed PCM output all use the same projection. PSG/SCC OPM projection already
generates a 4 MHz target, so it needs no additional pitch change.
Pitch correction remains enabled with `--no-normalize-lengths`; it is separate
from timing normalization.

```text
pitch offset in 1/64-semitone units = round(768 * log2(source clock / 4,000,000))
target pitch = source KC/KF pitch + offset
```

Pitch positions use KC gaps/aliases and the upper six bits of KF. A lower input
clock requires lower output KC/KF values to counteract the pitch increase caused
by the target clock. At 3,579,580 Hz the correction is -123/64 semitones.
KC-only and KF-only updates are supported; when a carry is needed, both
registers are emitted from the same source event. `target_sequence` retains
command order. Command values from 4 MHz inputs remain unchanged.

In-range calculations use nominal logarithmic pitch, with a maximum rounding
error of 0.78125 cents. Out-of-range clamping is a separate loss and can exceed
that error. These values are not measurements establishing identity with the
physical chip's frequency ROM or audible playback. The KC/KF indexing and
clock-scaling reference is the
[mdxtools YM2151 implementation](https://github.com/vampirefrog/mdxtools/blob/master/ym2151.c).
The logarithmic formula is implemented independently; no ROM table or emulator
code is incorporated.

## Unknown initial values and out-of-range pitches

- Only for inputs with a different clock, unwritten KC/KF values use an explicit
  target-side reset-zero assumption. The original State keeps `None`. Both KC
  and KF required for the first attack are set before Key-On, without relying
  on pre-existing MXDRV values.
- The normal 96-note KC range and the alias at the uppermost KC `0x7f` are
  handled. KC bit 7 and the lower two KF bits do not contribute to pitch;
  original bytes remain in the CSV.
- The default `--opm-pitch-policy clamp` selects the nearest KC/KF at the range
  boundary. Pitch differences, counts, and source events are recorded as losses.
  At 3,579,580 Hz with KC/KF=0, clamping to the lower bound introduces about
  +192.252 cents of error.
- `--opm-pitch-policy error` retains strict range checking. Out-of-range setup
  before the first Key-On can be deferred, but it is an error if unresolved at
  the attack. Out-of-range updates after the first attack, including release,
  are errors.
- This range is the KC/KF register range. It is not a custom tolerance around a
  Segment's pitch, nor an assessment of all hardware possibilities such as
  changing the voice's frequency multipliers.

## Inspectable evidence

`--dump-passes` saves:

- `.opm.segments.csv`: unchanged input Segments.
- `.mdx.pitch.csv`: source events/Segments, input clock and original KC/KF,
  assumptions for unwritten values, output KC/KF, nominal pitch error, clamping,
  and deferred initialization.
- `.mdx.controls.csv`: output commands in `register,data`; original commands in
  `source_register,source_data`. Added KC/KF writes retain their source-event
  provenance.
- `pitch_projection` in `.mdx.timing.json` and `.mdx.normalization.json`: the
  correction summary.

In the TXT report, see `OPM clock and pitch projection`. Clamped events under
`Pitch range policy` count pitch-update/Key-On evaluations, not notes. Ordinary
rounding errors and clamp errors are shown separately. Assumption counts are
numbers of affected events, not channels. Roundtrip comparisons check the
corrected expectation, applying the complete KC/KF pair for a source event before
comparing it.

## Correction limits

DT1 detune in Hz, EG and key scaling, LFO, noise, and chip timers are not retuned.
Matching pitch registers does not establish acoustic equivalence of timbre,
modulation, or release. PCM rates and encoded bytes are unchanged. Dual-chip
inputs and different chip types remain outside this scope.

## Protected interval tick allocation

Separately from pitch correction, `py/opm_output_normalization.py` assigns
boundaries to a shared FM/PCM clock during timing normalization. The approach
introduced on 2026-10-11 now uses `allocate_tick_domains` in the shared helper
`py/ordered_timing.py`. Source State, Segments, PCM IR, and original timestamps
remain unchanged.

- Ordered allocation is attempted only when nearest-tick rounding collapses a
  protected positive interval. It uses the same absolute boundary-movement
  allowance: `floor(44100 * --normalization-ms / 1000)` source samples, 352 by
  default.
- Each boundary receives a strict integer tick domain whose projected integer
  source-sample timestamp lies within that allowance. The MDX wrapper fixes
  source origin 0 at tick 0. It solves a DAG requiring adjacent boundaries to
  be nondecreasing and each protected interval to end at least one tick after
  its start. Intermediate ordinary control boundaries may share a tick.
- Protected intervals include the whole song, surviving FM gates, held partial
  Key operations and retrigger intervals, rests longer than the allowance,
  positive side-effect pulses, surviving PCM gates, PCM rests longer than the
  allowance, and valid song-loop intervals. Unclosed terminal gates are also
  surviving gates. Do not omit a short Segment or an unfinished gate as though
  it were a completed short note.
- If no solution exists within the domains, the helper returns `None` and the
  candidate is rejected. Invalid input arrays or interval references raise
  `ValueError`. After allocation, boundary errors, origin, global order, and
  positive lengths of protected intervals are independently rechecked. The
  allowance is not relaxed to force acceptance, and loops or gates are not
  silently discarded.
- If no other candidate is feasible, conversion returns to the original
  structured projection and shared clock. Candidate-side short-gate omissions
  are not adopted either. Candidate-specific PCM failure is distinct from
  source eligibility failure; normalization does not establish that the latter
  has been resolved.

Accepted `boundary_ticks` are stored in the projection. FM, PCM, validators,
and pass dumps use the same mapping. `.mdx.normalization.json` records
`boundary_allocation`, `adjusted_nearest_boundaries`, protected intervals, and
rejected candidates. `.mdx.normalization.csv` traces original timestamps,
candidate ticks, and errors. See [Note lengths and normalization](opm_note_lengths.md)
for short-gate omission and candidate selection.

## Implementation cross-check and historical scope

This document's KC/KF correction and pitch policy were cross-checked against
`py/opm_pitch_projection.py`; timing allocation was checked against
`py/opm_output_normalization.py` and `py/ordered_timing.py`.
Existing `tests/scripts/test_opm_pitch_projection.py` covers all notation/layout
variants, unknown initial values, clamp/error, out-of-range updates after
release, source preservation, and paired writes.
`tests/scripts/test_ordered_timing.py` covers feasible/infeasible constraints,
nonadjacent intervals, fixed anchors including the origin, non-mutation of
inputs, and strict MDX domains. These tests were inspected but not rerun for
that review.

The range-error-only policy from 2026-10-11 predates the current default clamp
policy. Implementation-time checks, private listening results, and trial
history belong in the external note
`field_notes/2026-10-11_opm_clock_projection.md`. Its success counts and listening
results are not specifications verified for the current code or every driver.
