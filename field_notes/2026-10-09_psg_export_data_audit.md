# PSG export failures and independent OPM data audit

## Scope and checkpoint

The user reported 8/82 successful exports, larger replay VGMs than independent
vgm-conv output, and MMDSP highlighting tracks without keyboard/volume animation.
They prioritized correct generated data and paused the separate PCM stopping
investigation. This audit fixes CSV evidence handling and retains comparisons;
it does not certify native playback or repair GUI behavior.

Work continues on `codex/psg_data_quality`. During work the user switched/pulled
`main` to merge commit `e12ca07`. Its tree matched the previous `cdc7065` tree;
the working changes survived and were moved to the new branch without resetting
the user's checkout history. Windows and WSL use the same repository files.

## Export failure and evidence preservation

The previous batch had 8 successes, 50 CSV field-limit failures and 24 explicit
noise/hardware-EG rejections. `_mark_projected_evidence` reread generated structure
CSV containing entire note trajectories with Python's default 131072-character
field limit. The large fields are valid evidence, not malformed input.

`_read_generated_csv` temporarily raises the limit to at least the containing
file's byte size, consumes the complete reader and restores the process-wide
limit in `finally`, including iteration failures. No provenance is truncated,
and no source PSG/SCC CSV or conversion semantics changes. The current caller
runs sequentially; parallel threads would require coordination of this global
CSV setting.

The full batch was rerun in a fresh directory:

```sh
python scripts/export_mdx.py tests/fixtures/local_only/psg/vgmrips.net \
  --target opm --outdir outputs/listen/psg_data_2026-10-09
```

Results: **57/82 generated**, 24 noise/hardware-EG conversion failures, and one
compiler failure (`XANADU14`, track 8 offset exceeds `0xfffe`). The last case
retains MML; this is the observed serializer/track-offset constraint, not proof
of a universal 64 KiB MDX file limit. No CSV field-limit failures remain.

The previous eight successful MML/MDX/VGM triples are byte-identical after the
fix. A formerly failing representative's structure field contains 803728
characters; all original cells were preserved except the intended
`state_origin=projected_opm` annotation. Ignored evidence:

- `outputs/psg_data_2026-10-09/provenance_preservation.json`
- `outputs/psg_data_2026-10-09/existing_artifact_preservation.json`
- `outputs/listen/psg_data_2026-10-09/results.csv` and `_errors/`

The diagnostic roundtrip script also had an obsolete success-summary lookup
for `expected_controls`; structured verification uses a different schema.
The summary now describes the actual state/Key comparison without depending on
that legacy field. This does not relax verification.

## Independent VGM comparison

`scripts/compare_opm_vgm.py` uses the existing OPM reader and Segment builder.
It saves both raw/state/Segment streams, absolute-sample interval comparisons,
ordered Key events, unknown fields, nominal pitch deltas, command counts, wait
encoding bytes and loop metadata. Released/muted states and same-sample Key
events remain inspectable. The comparison horizon is the shorter stored
traversal; unequal ends and unmapped keyed channels are reported separately.
Shared LFO/timer/noise state remains in the dumps but is outside the focused
field comparison. Per-channel PMS/AMS are compared. The Key list does not compare
instantaneous state/order at each Key; use the separate strict roundtrip verifier
for that. This is a diagnostic report, not a waveform oracle or pass criterion.

The eight independent files supplied by the user use tone channels 4..6,
whereas generated files use 5..7 (zero-based). The correct mapping is
`5:4,6:5,7:6`. This was confirmed from the installed vgm-conv converter's
`OPM_CH_BASE=4` and initialization/write trace. Source reference:
[AY8910-to-OPM converter](https://github.com/digital-sound-antiques/vgm-conv/blob/main/src/converter/ay8910-to-opm-coverter.ts).
The installed implementation was inspected; no external implementation was
copied into the project. Earlier exploratory comparisons with channels 0..2
are not used as evidence of correctness.

Final results are retained under
`outputs/psg_data_2026-10-09/vgm_comparison_channels_4_6/`, with a compact digest
in `outputs/psg_data_2026-10-09/comparison_brief.json`.

- Replay VGM sizes are 10.0..43.6 times the independent files, median 21.4.
- Stored-traversal end differences are -5..+5 samples. This does not establish
  timing equivalence at every boundary.
- For each file, at least 99.865% of mapped samples where both Keys are held
  and routed have nominal pitch differences of 0 or -1.5625 cents. The latter
  is one KF step and is consistent with differing rounding. Other differences
  and short boundary intervals remain visible; no tolerance silently passes them.
- vgm-conv holds one Key-On per tone channel and uses carrier attenuation for
  silence. Musical output has inferred attacks/releases and routing mute.
  Those differences are intentional under the user's articulation preference;
  oscillator phase and acoustic equivalence are not established.
- The reference's extra keyed channel 7 has observed C2 TL127 throughout its
  keyed intervals. Unwritten unused-operator parameters remain unknown rather
  than being assigned convenient reset defaults.
- Three reference files retain VGM loop headers; the generated target plan
  explicitly uses one stored traversal. This audit does not validate source
  loop preservation or loop seams. Finite phrase folding is a separate feature.

## Why the replay VGM is larger

The relevant writer is soundlog 0.15.0 MDX replay in the Rust helper, rather than
`opm_target_vgm.write_target_vgm`. In the pinned `mdx/convert.rs`, each MDX tick
calls `emit_wait_chunks`, which emits `WaitSamples`; adjacent tick waits are
not coalesced there. For one representative, 100007 three-byte wait commands
occupy 300021 of 329429 bytes, versus 9725 OPM writes. Repeated pitch/voice/level
writes also contribute. Their presence is diagnostic, not permission to remove
commands with possible side effects.

An inspectable IR-to-OPM-VGM stage already exists before normal OPM conversion.
Adding another emitter is not necessary to explain these sizes. Lossless wait
packing could be considered separately with event/timing equivalence checks;
no replay writer or packing optimization was changed in this checkpoint.

## Compiled MDX and strict verification limits

Independent mdxtools `mdxdump` parses all eight successful MDX files with exit 0
and no undefined commands. Static totals are 4139 Note commands and 1840
SetVolume commands, excluding repeat expansion. Therefore these files contain
normal MDX notes and volume commands. This does not demonstrate MMDSP display
updates. Logs/metadata are ignored under
`outputs/psg_data_2026-10-09/mdx_audit/`.

The formerly failing `DSLY4_01` passes actual structured target state/Key/end
verification. An additional representative `GRA1_01` fails the strict Key-point
check: all positive-duration states, Key command times/values and end agree,
but one Key-Off has six raw/decoded pitch-field mismatches. Inspection shows
the target updates KF immediately before Key-Off, while MDX replay updates it
immediately after Key-Off at the same sample. The existing musical renderer
places terminal zero-duration controls after the note's automatic release.
This is recorded as a genuine strict comparison failure, not waved away because
the interval state recovers. Do not change source IR or weaken Key-point checks
to obtain a pass. Evidence is in
`outputs/psg_data_2026-10-09/verified/{DSLY4_01,GRA1_01}/` and the latter's
`keypoint_audit/`.

The batch's `success` means artifacts generated; it does not mean all 57 files
passed a semantic roundtrip or native MMDSP validation. Next data work should
resolve release-boundary ordering through the normal note path, then assess
source loop handling and the remaining track-offset capacity case. GUI diagnosis
must use an observed native playback profile rather than infer behavior from
compiler output alone. PCM stopping remains paused unless the user resumes it.

## CLI proposal

Separating target machine/profile and output format is clearer than mixing
`--target mdx` with `--target opm`. A future interface could use
`--base-machine x68000 --format mdx`, detect the source chip from the VGM header,
and retain existing `--target` spellings as compatibility aliases. `--psg-model`
still describes projection, independently of output format. Future Z_MUSIC
should have its own target profile/format consuming source IR, without using
MDX text or PDX allocation as its common representation. This is an assessment;
the proposed machine/format flags were not implemented during the data audit.
The later MXC export-compiler selection is recorded separately in
`field_notes/2026-10-09_mdx_compiler_baseline.md`.

## Checks

56 focused tests passed: CSV provenance (2), OPM diagnostic comparison (7),
diagnostic summary (1), and existing PSG/SCC target, FM profile, performance,
state, target-VGM and export tests (46). The full private batch and the two
strict representative checks have the distinct outcomes stated above. No
all-suite or all-song roundtrip success is claimed. Private source music and
generated scores remain outside Git.

After the compiler switch passed public checks, the user reconsidered closing
the roundtrip-validation phase and explicitly requested that MDX-to-VGM and
roundtrip comparison remain available. The final change is to the FM compiler,
not removal of replay or validation. See
`field_notes/2026-10-09_mdx_compiler_baseline.md`. The paused PCM stopping
investigation and native GUI diagnosis were not resumed.
