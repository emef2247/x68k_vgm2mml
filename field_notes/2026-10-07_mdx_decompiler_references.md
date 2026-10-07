# MDX decompiler references and macro scope

User decision: exclude macroization from current MDX work, maximize reuse of
proven MGSDRV/shared processing, and use existing MDX binaries to obtain
independent structured MML references for test material.

## Confirmed implementation and experiment

Built unmodified vampirefrog/mdxtools revision
`9c8539fec2757fcf7c85d1986171b50ebe2ef1e5` under ignored
`outputs/mdx-reference-tools/mdxtools`. Only `mdx2mml` and `mdxdump` were built;
no global installation or third-party source in the converter.

`mdx2mml` renders finite/nested repeats, last-iteration escapes and song-loop
targets as brackets/counts, `/` and `L`. It reconstructs compiled structure,
not original formatting or macro names. Primary source links and exact commands
are in `docs/mdx_reference_mml.md`.

Four original MIT public cases under `tests/fixtures/public/opm/mdx_decompiler`
cover nested repeats, repeat exit, song loop and tied-note/control continuity.
All four decompiled MMLs recompile to byte-identical MDX and VGM using the pinned
mmlx 0.2.0 / soundlog 0.15.0 helper. All four source VGMs also pass the existing
native converter/compiler OPM roundtrip. This is validation within that tool
chain, not a hardware or acoustic result.

The song-loop example confirms instruction-relative origin: track A F1 at offset
23 has displacement -16 and targets offset `23 + 3 - 16 = 10`. The decompiler
restores `L` before the repeat at that offset. An initial concern about subtraction
by 65533 was resolved by the three-byte command-end adjustment; no upstream bug
was established.

Compiled MDX note numbers, target note spelling and observed native KC values
remain separate in the manifest. The fixture tests assert raw KC and authored
attack timing rather than imposing target labels on source state. No pitch
interpretation was changed.

## Local-only expansion and limits

Inventory found 50 local-only MDXs, of which 18 lacked same-stem source MML;
all 18 had same-stem VGM candidates. All 18 now have untouched decompiled MML,
command dumps, logs, executable/source hashes and structure reports under
ignored `outputs/mdx-reference-verification/local-decompiled`.

The limited repeat nesting/count/exit attachment and loop-marker audits agree
for all 18. All remain `needs_review` because the decompiler omits `PCM8Enable`.
This command warning must not be mistaken for a structural mismatch or waived
without checking the intended comparison scope.

Selected three cases with different depth/exit/loop characteristics:

- Original-MDX replay exactly matched all timed OPM writes and source end samples
  of their paired existing VGMs. Same-stem pairing is verified for these three;
  the remaining fifteen pairs are provisional.
- Decompiled-MML compilation succeeded. Key writes, their times and end samples
  match original-MDX playback, but complete OPM write lists differ. Keep both
  versions; this result does not authorize using the reference as a full chip
  behavior oracle. The causes of those extra/different writes are not resolved.
- Existing VGM -> structured MDX -> external replay checks passed for all three.
  Source analysis produced 23,251 / 12,000 / 13,767 Segment rows; state, integrated
  Segment, target-control and structure CSVs were retained and inspected.
- Original and decompiled playback state/Segment CSVs were retained separately
  to support future diagnosis. No original fixtures or reference traces changed.

## Added tooling and checks

`scripts/decompile_mdx_references.py` runs external tools into a fresh separate
destination, preserves failed/partial outputs, and records provenance. Its audit
is deliberately limited to structural delimiters/counts. It does not certify
note/control equivalence, exact exit position, or loop destinations. The public
song-loop test and compile/replay experiments supply additional evidence for the
selected examples.

Seven focused unittest methods pass, including structural mismatches, malformed
output, empty/unrecognized dump output, tool failure, timeout, output preservation,
fixture hashes, expanded attacks/timing and the F1 target. Four public and three
local native roundtrips pass. Reports and logs are under
`outputs/mdx-reference-verification`, including `verification-summary.json`
and `intermediate-inspection.json`.

No VGM conversion algorithms or compatibility behavior changed. The full inherited
suite was not rerun; the previously documented inherited failures are unchanged
in scope. Public test data is original, private data and derived MML stay ignored.

## Next use

Use these references to inspect encoded source structure when diagnosing a
concrete VGM-output problem. Compare expanded behavior separately, because a VGM
may admit multiple repeat factorizations. Do not force the converter to reproduce
the reference text or feed the MDX/decompiled MML into VGM conversion. Additional
pair/replay validation can expand beyond the selected three when a particular
problem needs it. Macroization remains excluded from current MDX work.
