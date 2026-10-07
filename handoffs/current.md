Project: x68k_vgm2mml

Latest layout change: all 62 top-level test/helper Python files moved to
tests/scripts/. Repository-root references and documented discovery commands
were updated; fixtures remain in place. Run
python -m unittest discover -s tests/scripts -v.
Before/after discovery has the same 444 test IDs with no import errors.
After moving, 75 OPM, six SCC-header and ten external replay tests passed.
This change is already visible from the same WSL working tree.

Current task: readable native MDX MML, optional length correction and short
relative octave/volume setters. Implementation and focused tests are complete;
final user-facing replay and focused architect review passed. Work is complete.

User decisions:
- Reuse established MGSDRV/shared processing where native semantics fit.
- Length correction is opt-in with --normalize-lengths.
- Track comments and exact musical length spelling apply to normal output.
- Use at most two relative octave/volume symbols when no longer than absolute.
- Exclude MDX macroization; preserve compatibility-target macro support.

Implemented:
- /* Track A */ through /* Track H */ comments in native renderers.
- Shared exact MDX duration spelling and tied whole-note chunks.
- OPM adapters for the existing shared clock estimator. One actual MDX timer
  uses absolute nearest ticks, with all control/Segment/Key/end/loop boundary
  errors bounded and positive intervals retained. Whole-song fallback with
  explicit reasons; no source mutation, phase/grid onset snapping or pruning.
- Normalization JSON; with dump-passes, candidate/control CSV, before-MML and
  before/after structure counts, plus all established native/pass dumps.
- Target compaction uses known-state relative o/v/@v changes of one/two steps.
  Absolute loop entries, volume mode changes and voice/raw-state invalidation
  remain visible. Relative setter decisions are saved in compaction CSV.
- Optional compiler/player tests for long duration/tie and relative-state
  equivalence, with clean skips if the external Linux tool is unavailable.

Validation:
- OPM discovery 75 methods and compaction 16 methods pass after relative changes.
- Independent external comparisons: four duration and six relative cases pass.
- Final public native compiler/replay checks: all nine from_mdx cases pass.
- Normalization checks on three selected local sources and jittered original
  synthetic source pass; one local candidate is correctly rejected.
- Selected long case retains 2,159 note units, max correction 135 samples under
  587 bound, zero collapses. Source-unit loop applications remain 244.
- Actual output at outputs/python/M_G2_01S.mdx.mml was regenerated with
  --normalize-lengths --dump-passes after the relative change. Final replay
  comparison in outputs/mdx-note-lengths/final-output-replay/ passed: Key/state/
  projected end exact; native raw/state bytes and Segment cells unchanged.
  Relative setters: 361; step note/rest tokens 1,650 -> 165; chars 41,856 -> 33,577.
- Details: docs/opm_note_lengths.md and
  field_notes/2026-10-07_mdx_note_lengths.md.

Next allowed action:
User is preparing to add all related files and commit. The working tree is
directly shared with WSL at /mnt/i/wsl/repositories/emef2247/test/x68k_vgm2mml;
changes and final tests are already reflected there. No separate copy is
needed for that path. An English commit message is supplied in chat; staging,
commit and publication have not been performed.

Must not happen next:
Do not feed reference MDX/MML into VGM conversion, force reference-text matching,
change native Segments/traces to pass, discard dumps, apply MGS gate/pruning
rules to OPM, or claim fitted-clock error equals actual timer error. Do not
commit private fixtures or their MML. Macroization remains excluded.

Prior context:
MDX independent reference preparation is complete; see
field_notes/2026-10-07_mdx_decompiler_references.md. Canonical frontend migration
is complete. Eight inherited failure records in seven methods remain
(allocation/private OPLL/GD3), reproduced in source repo. Do not describe the
full inherited suite as passing; see 2026-10-07_x68k_frontend_baseline.md.

Environment:
WSL available; I: access works through approved commands. External generator
uses pinned mmlx 0.2.0 / soundlog 0.15.0. mdxtools reference tool remains pinned
at 9c8539fec2757fcf7c85d1986171b50ebe2ef1e5 under ignored outputs.
