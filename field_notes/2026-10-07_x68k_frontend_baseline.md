# x68k frontend migration baseline — 2026-10-07

## Scope and inventory

The user split x68k_vgm2mml from msx_vgm2mml. The working tree initially had
untracked source/tests/docs and a tracked LICENSE. Git diff alone therefore
cannot describe the migration; no files were staged or committed.

Read project_knowledge.md and current.md before changes. The handoff mentioned
MDX redesign, but the current user request explicitly deferred that work until
repository cleanup and canonical frontend integration are complete.

- Keep all chip analysis and inherited target modules: PSG/SCC/OPLL compatibility
  is intentional, and their tests share these implementations.
- Move native OPM orchestration from scripts/opm_to_mdx_mml.py into
  py/opm_conversion.py. Delete the duplicate script after updating all code
  consumers; it had no independent diagnostic responsibility.
- Move PSG/SCC OPM conversion into py/psg_scc_conversion.py. Retain the batch
  script for verification/comparison using that shared implementation.
- Restore missing diagnostic, regression, external compiler and fixture-generator
  dependencies. Retained scripts and their purposes are listed in scripts/README.md.
- Keep experiment tools explicitly classified as development aids and correct
  their MGSDRV frontend calls. Do not restore vgm2mml_grid.py.
- Keep fixture directories and the original conversion_baseline.json unchanged.
  The actual layout is tests/fixtures/public and tests/fixtures/local_only.
- Replace the root README with X68000 usage and keep detailed MGSDRV instructions
  in docs/mgs_compatibility.md. Update AGENTS navigation and stale grid references.
- Preserve the user's earlier docs/field_notes cleanup. No wholesale history
  deletion or chip-module removal is justified by the new project name.

## Frontend contract

Default / --target mdx: native OPM to MDX MML.
--target mgs: inherited PSG/SCC/OPLL to MGSDRV MML.
--target opm / opm-additive: inherited PSG/SCC to OPM MDX models.
Output defaults to the input directory; isolated checks always specify --outdir.
Existing native notation, tracks, loop controls and dump outputs remain available.
The unified --gd3-language option is forwarded to native title selection; explicit
titles take precedence. The default Japanese preference remains unchanged.

## Copied correction

The copied opm_mdx_music.py was missing the source repository's two-line raw TL
reserved-bit guard in volume projection. Its copied regression test failed.
Restored the existing source correction; no new MDX algorithm was designed.
All inherited py modules now match the source repository byte for byte.
The synthetic bits case retains four data=148 source rows, target writes to
registers 96/104/112/120, and all four explicit raw commands in final MML.
Evidence is under ignored outputs/migration-baseline/tl-reserved/.

## Validation evidence

- Public chords_mix and patch_change_midnote: 38 files per case are byte-identical
  between the source script and canonical frontend, including native/state/Segment
  CSVs, structural dumps, timing report and final MML. Segment row counts: 330, 317.
- Both cases pass the existing external MDX compiler/player roundtrip in WSL.
  This checks target/source behavior within the verifier's scope, not acoustic
  equivalence or the quality of future musical reconstruction.
- Native OPM tests: 68 passed. Canonical CLI route tests: 5 passed (including explicit SCC-gain rejection).
- Original full-suite process ended without a summary during the turn/session transition.
  Its log is partial evidence, not a completed run. 51 of 74 optional long private
  catalog/compression tests were observed passing; 23 were not completed.
- Final remaining run: 317 tests, 8 failure records across 7 methods, 1 skipped,
  no errors. The original completed portion includes 25 other normal tests.
  Do not describe the complete suite as passing.
- The exact seven failing methods were run in msx_vgm2mml: the same eight failure
  records reproduced. See ignored outputs/migration-validation/source-known-failures.log
  and verification-summary.json. No assertions or fixture goldens were replaced.
- Architect reviewed routing, converter extraction, documentation and option guards:
  no new migration blocker. Final --scc-gain handling preserves the compatibility
  default 0.125 and rejects an explicitly supplied value for native MDX.

## Inherited validation discrepancies to resolve separately

Five failure records concern allocation totals: implementation defaults to 16000,
while assertions and inherited documentation expect 15000. The correct allocation
policy requires its own review; migration preserves the inherited behavior.

Two optional private OPLL trace-reference tests fail at native timing comparisons,
including a one-sample startup difference. Investigate the actual source event and
reference provenance; do not erase the sample interval or regenerate expectations
solely to make these checks pass.

One GD3 formatting assertion expects no space after the system label; the inherited
formatter adds a space. Reconcile the expected formatting separately.

The migration is verified against the source baseline with these inherited suite
failures explicitly retained. This is not evidence that the inherited algorithms
or all reference expectations are correct.
- Private fixtures and generated outputs remain ignored by Git. No private
  fixture contents are included in this note.

Clarification after the migration: the existing MDX renderer already has attack
units, held-control trajectories and the shared MGSDRV loop planner. Calling the
next phase a mandatory "full redesign" overstated the remaining work. Further
MDX work should maximize reuse of established MGSDRV/shared processing and inspect
specific target-notation issues (including control-time slices/ties) before
choosing changes. Existing Segment semantics and source evidence must not be
reshaped merely to obtain cleaner MML or passing tests.
