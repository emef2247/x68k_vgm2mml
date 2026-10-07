# MDX duration spelling, bounded correction and relative setters

User requests: native track comments, readable note values, optional length
correction reusing established MGSDRV processing, and short relative octave /
volume setters. Macroization remains excluded. Private derived MML and traces
remain ignored under `outputs/`; this note records aggregate findings only.

## Source and target findings

- The current shared `note_normalization.infer_timing` matches the sibling
  MSX implementation. OPM rising Key edges can supply its attack anchors.
- A musical fit nominates a timer but does not prove native MDX boundaries
  remain representable. Applying MGSDRV phase/grid onset snapping to the
  selected long case would collapse 144 short/gated intervals; that approach
  was rejected. The implemented target uses absolute nearest MDX ticks and
  checks every positive boundary interval before accepting the whole song.
- Ordinary native timing inference remains strict (six samples). Explicit
  normalization uses the shared fitted bound, checks actual MDX sample errors
  and records rejected candidates. It does not infer `q` or prune OPM states.
- MDX note values include triplet divisors and one/two-tick spellings. Local
  mmlx compilation probes confirmed 3/6/12/24/48/96/192; mdxtools's decompiler
  also recognizes those values. MGSC's restricted divisor list is not the
  native MDX vocabulary. Remaining exact durations use step notation.
- Long note chunking uses 192-tick whole notes with ties. Compaction keeps the
  trailing tie inside each repeated body, preserving compiler lookahead.
- MSX's current relative helper uses delta one, while old helpers allow delta
  up to three. The user's MDX rule accepts delta one/two when the token is no
  longer. Coarse/fine volume modes remain separate and loop entries absolute.
- The generator uses mmlx 0.2.0 and soundlog 0.15.0. mmlx `FineVolume(N)` is
  `255-N`; soundlog's fine-volume relative up decrements that encoded operand.
  This supports exact one/two-step fine-volume replacement without changing
  inferred chip/operator values. Other MML compiler dialects are not asserted
  equivalent by these tests.

## Verification scope

- Native OPM unittest discovery: 75 methods pass after the relative change.
- Focused compaction: 16 methods pass, including mode switches, raw/voice
  invalidation, absolute loop entries, duration expansion and depth limits.
- Earlier targeted 74 methods passed for normalization, renderers, routing,
  shared MGSDRV normalization and reference preparation (overlaps the above).
- Four independent old-step-vs-named-duration external tests pass, including
  long held/released tails, controls, nested ties, and dotted/triplet lengths.
- Six independent absolute-vs-relative external tests pass. All comparisons
  require exact Key write timestamps/masks, zero effective-state differences
  at the union of boundaries, and exact end samples. Intermediate/redundant
  register writes may differ at the same sample; full byte identity is not
  claimed. Windows without the Linux compiler cleanly skips these checks.
- Public native renderer/compiler checks use all nine original `from_mdx`
  cases, separately from the four independent decompiler-reference cases.
- Three selected local normalization checks passed: one is rejected because
  its candidate collapses an interval; the other two are accepted. A jittered
  original synthetic source is accepted and has fewer distinct note-unit
  keys and shorter output, with exact loop expansion and native evidence intact.

The selected long song retains 23,251 native Segments and 2,159 note units.
It nominates multiplier 26, has zero collapsed positive intervals and a worst
actual correction of 135 samples (about 3.06 ms), under its 587-sample fitted
bound. Its source-unit loop applications remain 244; shorter output in this
case is not evidence that more musical loops were discovered. The emitted
chunk-loop count falls when fewer fine-clock chunks are needed.

Final user-facing replay passed after the relative change: projected Key
sequence and end match exactly, effective-state differences are zero, and
raw/state trace bytes plus native Segment cells match the conventional run.
Both current before/after MML use 361 relative setters. Normalization reduces
structured text from 41,856 to 33,577 characters and emitted step-duration
note/rest tokens from 1,650 to 165 (named-duration tokens 1,583 to 2,110).
These are emitted-text counts, not expanded performance-event counts.
The final nine public native compiler/player checks also all passed.

Evidence locations (ignored): `outputs/mdx-note-lengths/` and
`outputs/mdx-relative-setters/replay/`. User-facing output is under
`outputs/python/`. Inspect normalization JSON/CSV, native raw/state/Segment
CSV, uncompacted/final MML and compaction decisions together. Final replay
checks the actual user-facing file, not a separately generated approximation.

No hardware/audio check was performed. The inherited full suite was not
re-run: previously reproduced allocation/private-OPLL/GD3 failures remain
documented in `2026-10-07_x68k_frontend_baseline.md`.
