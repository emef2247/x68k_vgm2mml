Project: x68k_vgm2mml

Status (2026-10-08): PAUSED at the user's explicit request after minimum public
OPM/MDX checks passed. Stop further implementation/research until the user asks
to resume. Workspace is shared with WSL; no separate synchronization is needed.
Current changes are local and uncommitted.

Current implementation:
- PSG/SCC default --target opm now feeds musical projected OPM VGM into the
  ordinary opm_conversion.convert path; no parallel Segment-to-MML renderer.
- User rejected raw y/whole-song tie mapping and explicitly chose musical
  articulation with documented oscillator phase changes.
- Audibility rise/fall infer Key-On/Off. Pitch/volume changes stay continuous.
  No periodic Keys for GUI. Source Segments and held baseline are preserved.
- py/opm_performance.py records inferred gates, baseline IDs and source rows.
  py/opm_target_vgm.py emits an actual target VGM and global command/address map.
- --dump-passes retains performance CSVs and projected_opm/ containing target
  VGM, source_map.csv, provenance.json and canonical OPM analysis/structure.
  Generated OPM CSVs mark state_origin=projected_opm. Original -> target -> final
  timing is mapped and checked directly within 12 samples, including the end.
- --notation registers preserves held replay; --no-loops is supported.
- Saturation-aware carrier volume spelling reproduces all TL/raw values exactly.
  The common native final renderer was extracted without initial output changes.
- scripts/export_mdx.py remains available for MML/MDX/VGM output-only listening.

Evidence:
- field_notes/2026-10-08_psg_opm_musical_connection.md: decisions, MSX/assets
  review, implementation, test scope and restart task. Read before resuming.
- Related 115 automated tests passed; modified validator regression separately
  passed in the five target-VGM checks. Full inherited suite was not rerun.
- Public native OPM/from_mdx 9/9 external roundtrips passed.
- Public PSG volume_sweep, scale_chromatic, short_pulses passed external known
  state/muted-state, exact Key command/time, Key-point state and end checks.
  Respectively 16/13/4 note units, no fallback; MDX bytes 1533/1329/546.
- Each PSG case's 27 original source/pass/held-baseline files are byte-identical.
- Results: outputs/opm/structured_psg_2026-10-08/final_public/ and final_native/.
- No local song, audio listening, MMDSP GUI or new vgm-conv size comparison was
  performed. No private fixtures/outputs are to be committed.

First allowed action AFTER user resumes:
Fix the all-silent-input regression in the new structured path. Performance
has no OPM writes, and project_segments cannot infer a chip from empty native
Segments. Represent silence through its explicit end without inventing attacks
or source OPM evidence, and add one focused conversion-level regression test.
This was identified in final review and deliberately left for resumption at the
user's requested public-test stopping point; README records the limitation.

Then:
Validate the already established local tonal cases (GRA1_03/05, DSLY4_04 and
GRA2_17), capacities, all known/muted states and Key points. Inspect player/audio
results from the user. Only then consider noise/mixed tone/EG and explicit
resource allocation; none were implemented here.

Do not:
- Resume work merely because a review tool or agent has further suggestions.
- Reintroduce whole-song snapshot/tie/raw mapping as the new normal renderer.
- Claim inferred OPM Keys were observed in source PSG/SCC or phase is preserved.
- Add arbitrary Keys to animate meters, rewrite source Segments, discard muted
  controls or zero-time evidence, or feed reference MDX/MML into conversion.
- Confuse minimum public success with GUI/audio/full-suite/capacity validation.
