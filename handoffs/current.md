# OPN2 S3: DAC bridge to MSM6258 (2026-11-02, branch claude/opn2, f7c5840)

py/opn2_pcm.py bridges the YM2612 DAC to the PCM/PDX target, on by
default (--opn2-dac / --no-opn2-dac). Both real-world encodings
decode into one byte timeline: 0x2A write runs (gated by the
analysis's DAC-enabled spans) and DAC streams (type-0 blocks,
0x90-0x95 setup, 0x93 autonomous starts on the libvgm phase model,
0x95 fast starts arming 0xE0 seeks / 0x8n plays). Lessons baked in:
seeks/plays often come with NO setup commands (Bloodlines, Shinobi)
and bind to one implicit bank context; stream supplies are NOT
gated by the DAC enable bit (Time Trax never sets it yet streams
its whole soundtrack); Bloodlines' entire DAC activity is a tick-0
artifact (240 wait-0 plays + silence writes) that correctly yields
no playbacks. Runs split at >10 ms gaps and at the song-loop
boundary, dedupe by waveform hash; decode notes ride in the PCM
analysis observations (any entry in issues blocks the planner as
"not representable"). Verified: Burning Force 03 MML/MDX
byte-identical to S2; Shinobi 06 (with --force for DCSG) gives 518
playbacks / 63 samples, PDX 148,389 B, MDX 33,802 B compiled. Time
Trax 01 decodes fully (1.58M plays, expanded) but its continuous
stream is one waveform per traversal and exceeds PDX capacity
(2,080,280 B needed) — phrase-level slicing of continuous streams
is the remaining DAC gap, alongside the known FM MML capacity wall.
Next stage is S4 (DCSG destination, decision at the gate with the
duty measurements already in opn2_source summaries).

# OPN2: DAC stream recognition + Time Trax survey (2026-11-02, branch claude/opn2)

Time Trax (Prototype, MD; the user's next target after Burning
Force) cannot even be routed before this change: its DAC traffic
is the VGM stream encoding — 852,695 play commands (0x80-0x8F)
and 35,348 seeks (0xE0) against a single 280-byte data block in
track 01 — and the frontend filed every one as an unsupported
command (route blocked; the conversion report ballooned to
146 MB). The frontend now attributes seek/play commands to the
OPN2 DAC when the source uses one and aggregates them in
usage['dac_stream'] (play/seek counts only). opn2_opm refuses
stream playback without --force (S3 will decode it) and records
the omission under force. Related refinement: 0x2A DAC data
writes while the DAC is disabled are inert (initialization
blips; Time Trax has 2) and no longer require --force.

Survey facts for Time Trax 01: DCSG unused, no CSM, FM is 21k of
942k events. With --force the FM part converts, but the MML
(175 KB) fails MDX compilation: track 7 offset exceeds 0xFFFE.
So this target has two walls: the stream DAC voice (a continuous
wavetable-style voice streamed from a tiny block, not one-shot
drums) and MDX capacity on long dense songs.

# OPN2 (YM2612) S2: FM -> OPM projection (2026-11-02, branch claude/opn2)

py/opn2_opm.py projects the S1 analysis in the opna_opm shape
(vgm-conv mapping, OPNA channel map: FM 0-2 -> OPM 0-2, FM 3-5 ->
OPM 4-6, OPM ch3 reserved). Ch3-special/CSM reject without
--force (OPNA precedent). While the DAC is enabled, ch6 FM output
is gated from state; DAC sample playback itself (S3) and audible
DCSG (S4) are --force omissions recorded in the settings JSON
(<stem>.opn2-opm.json) and printed. One real-data correction:
operator registers with channel bits 3 (0x30-0x9F, &3==3) select
no channel on hardware — drivers upload padded voice rows — so
the projection classifies them as known no-ops counted in the
losses, mirroring opna_opm's slot classification (field note
2026-11-02_opn2_unmapped_operator_slots.md).

Verified: Burning Force 03 Bay Yard (the user's pinpoint target;
the whole 16-track pack is FM-only: no DAC writes, no audible
DCSG, no CSM) converts without --force and compiles to an
18,835-byte MDX with the real fixture generator. 12 OPN2 tests
pass (6 S1 + 6 S2). Remaining stages: S3 DAC bridge, S4 DCSG
destination (decided from measurements at that gate).

# OPN2 (YM2612) S1: frontend + native analysis (2026-11-02, branch claude/opn2)

User-approved port of mucom88_vgm2mml's OPN2 support (design study:
~/workspace/x68k_opn2_study/DESIGN.md in the agent workspace). S1 only:
py/opn2.py is a port of mucom88's musical_hal opn2.py with one
adaptation (DAC enable 0x2B bit 7 is channel-6 state, not an
unmodeled write; DAC data 0x2A stays unmodeled-retained).
py/opn2_source.py builds the register-evidence CSV, dumps
states/segments/unmodeled CSVs, and measures DAC encoding (0x2A runs
vs stream controls) and DCSG duty for the later stages.
conversion_config inventories 0x52/0x53 (second instance 0xA2/0xA3
unsupported), reads the clock at 0x2C, retains YM2612 DAC stream
controls as evidence, and routes {'opn2'} / {'opn2','dcsg'} to
'opn2-to-opm', which currently stops after analysis with an explicit
S1 message. 6 synthetic tests pass; the full-suite failure set is
unchanged (27 names, same VM).

Burning Force (MD, 16 tracks, user's target pack; track 03 Bay Yard
is the pinpoint goal) measured FM-only on every track: no DAC
writes, no audible DCSG, no CSM. S2 (FM->OPM) alone makes the pack
play. Next: S2 projection in the opna_opm shape, OPNA channel map,
ch3-special/CSM reject without --force.

# Export CLI defaults (2026-10-30)

User requested MDX export defaults: pcm-buffer-kib1200, pcm-policy best-effort, no-vgm=True. Explicit values and --vgm still override. Defaults resolve only for MDX so inherited OPM diagnostic routes retain behavior. Canonical/direct Python API defaults unchanged. Export34tests pass; no music conversion. Direct loader +4096margin gives1224704B PDX budget.

# Commit checkpoint (2026-10-30)

MSM6295 source/bank support and shared buffer-derived PCM capacity are being saved together. Current final policy: --pcm-buffer-kib determines the PDX budget after loader overhead/margin; no independent --pdx-limit-kib and no1.2MB fixed ceiling. Omitted buffer defaults to315122B. Latest capacity/export checks:54passed. Earlier MSM6295/reference validation is recorded below. User owns local listening/regression. Private scan metadata and music stay outside the public commit; related field notes are committed separately. No push requested.

# Supersedes independent PDX limit (2026-10-30): user requested buffer-derived limit only. --pdx-limit-kib removed. --pcm-buffer-kib minus overhead/margin is the PDX budget; no1.2MB cap. Default315122B retained. 54 checks pass; no commit/push.

# Explicit PDX size override (2026-10-30): --pdx-limit-kib added to export/canonical/batch; keeps315122B default, permits explicit higher file limits, honors configured resident overhead/margin. 54 focused checks pass. No guest config or source changes.

# Default PDX budget reduced for user playback trial (2026-10-30)

- Default table-inclusive PDX cap is now315122B:312KiB initial MXDRV reference -270B MXCTRL -4096B headroom.
- Explicit resident settings still permit larger budgets up to the separate1200000B operational ceiling.
- Does not detect installed driver RAM or change guest configuration; runtime playback remains unmeasured.
- Existing budget96/force selection and final packing guards consume the shared policy; source evidence untouched.
- Multiple96-slot banks are deferred: loading all banks can still exceed resident total.
- Preserve preceding uncommitted MSM6295/resident-budget changes; no commit/push requested in this turn.

# Optional PCM resident-buffer budget implemented (2026-10-27)

User approved the capacity-plan implementation. Added immutable target-only
PcmCapacityPolicy; default remains1,200,000B. Canonical and export CLI accept
--pcm-buffer-kib, --pcm-loader direct|mxctrl and --pcm-buffer-margin-bytes.
MXCTRL overhead270B and default configured margin4096B give315122B PDX for
an explicit312KiB resident buffer. This does not identify installed MADRV/MXDRV
settings or establish safe total RAM. Nondefault margin requires buffer input.

The same resolved policy reaches source-validation target views, reducer/repair,
force, native/parallel binding, normalization preflight and actual final packer.
PSG PCM keeps its continuous-mix semantics and final budget guard. Slots/sample
lengths remain separate. Metadata/console/CSV distinguish configured capacity
checks from unmeasured playback. No automatic rate-profile retries or changed
default fidelity. Existing source protections/strict and force meanings retained.

256 focused authored/public checks pass across native PCM, Delta-T, SegaPCM
shared helpers, C140/MSM6295 conversion, PSG PCM, CLI/export, stats, packing and
standard/EX-PDX. Two existing multitrack tests failed with HEAD pcm_mdx too;
they now explicitly request standard PDX for their65535B-overflow premise.
New tests cover actual packer padding, representative repair, parallel force,
normalization, immutable per-run settings and no-input mutation.

Ignored outputs/diagnostics/pcm_resident_budget_20261027/ contains test logs,
the old-module failure reproduction, authored source/pass CSVs and summary:
legacy PDX1280B/2assets/2events; configured1KiB PDX1024B/1asset/2events with
explicit forced replacement. Input/source evidence unchanged. Runtime playback
unmeasured. See docs/pcm_playback_budget.md for current usage and scope.

Preserved all pre-existing uncommitted MSM6295 work; no stage/commit/push.
No private regression or player/config changes. Next:user runtime regression;
adaptive low-rate candidates and PSG gate-aware bank extraction are separate
follow-ups. Do not claim generated-size fit proves playback success.

---

# MSM6295 initial bank route implemented (2026-10-25)

Saved single-chip MSM6295/OPM+MSM6295 source + cached PCM8/EX-PDX projection.
Source commands/ROM/State/Segments and inferred assets/playbacks/requests remain
separate; source assets converted once, gain/stop reuse full samples. Exact
origin auto policy selects best-effort. Independent pinned reference and hashes
under ignored.tools; see docs/msm6295_design.md and external field_notes/
2026-10-25_msm6295_initial_implementation.md.

Final24MSM6295 checks +21C140 checks pass,public3/3batch passes. Existing CLI25,
export31,stats4,policy6 pass; VGM I/O title-space expectation fails also with
HEAD baseline (unrelated,unchanged). Final EOF/restart boundary regressions and
native-IR-before-target-failure test pass; authored pass CSVs inspected.

Authorized private finite batch(no-force):FFIGHT01/02/03 allsuccess;01 five
samples/216playbacks,PDX14893B;03 six/73,PDX17533B;zeroomitted.02 FM-only.
Outputs:outputs/diagnostics/msm6295_impl_20261025/FFIGHT/tracks.
Default song-loop FFIGHT03 remains blocked by held-PCM continuation guard;
recommend --no-song-loop for user listening/regression. Do not fake attacks.
Dynamic rate/bank/NMK/liveROM changes are MVP limitations with explicit errors.

README unchanged,no staging/commit/push. Private/generated assets ignored.
Next:user full local_only regression/listening. Do not expand C140 analysis
(user requested completed regression record only); retain C14048m budget.

---

# MSM6295 design; C140 regression recorded (2026-10-25)

BURNFC.log recorded only:30 inputs,14 success/16 pcm_projection_blocked;
user explicitly requests no further C140 analysis. Preserve48m capture cap.
See external2026-10-25_c140_user_regression_complete.md.

MSM6295 design only: docs/msm6295_design.md and external field_notes/
2026-10-25_msm6295_design.md. Only FFIGHT01/02/03 inspected (no conversion).
01/03 use5/6 short source samples, preliminary peak2;02 contains no B8 writes.
03 has nonzero actual loop-entry and replay-seam state; no fake reattack.
Plan uses native source evidence + source sample/playback separation, assets
converted once per dependency/rate identity, shared PCM8/96slot/EX-PDX target.
Pin core+decoder and compare authored native-frame timing before implementation.
Inspector data/counts are preliminary, not independent oracle validation.

No production code, README or test changes this design task. No staging/commit/
push. Next: user design decision, then scoped implementation. Full listening/
local_only regression remains user-owned; preserve all existing work.

---

# C140 capture budget retained at48m (2026-10-25)

User requests keeping the relaxed conversion limit despite BURNFC03 playback
reporting an MXDRV track-buffer shortage. MAX_TOTAL_FRAMES now48,000,000
(previous32m); per-gate/completion/target/PDX limits unchanged. docs/c140.md
updated. This retains the successful diagnostic conversion condition; it does
not fix or diagnose the reported native track-buffer error. No private rerun.
README unchanged; no staging/commit/push. Full regression remains user-owned.

---

# BURNFC03 capture-budget investigation (2026-10-25)

User requested focused investigation; BURNFC03 source/probe now authorized.
Existing total_resource_limit gate2400 is the32m aggregate native-frame guard,
not ROM/PDX limits. Algebraic accounting:35,058,325 frames over71.102s;
reproduces64.65s rejection. Two held internal-loop voices last37.854s each.
An in-process48m override with force + finite pass succeeded in597s:
80 samples/1988 retained playbacks;694 omitted (all8-voice allocation);
MDX49978 bytes,EX-PDX808873 bytes. Outputs separate under
outputs/diagnostics/c140_burnfc03_20261025/expanded_budget. Not a batch mmlx
rerun or listening check. Default and conversion code unchanged.

See external field_notes/2026-10-25_burnfc03_capture_budget.md and ignored
analysis_ja.md. Next possible change: bounded configurable capture budget;
longer-term incremental capture/reuse. No other BURNFC files investigated.
No staging/commit/push; preserve all previous C140 working-tree changes.

---

# Initial C140 bank implementation (2026-10-25)

Saved native C140 System 2/21 source evidence, pinned runtime voice reconstruction,
and shared PCM8/EX-PDX bank projection. See docs/c140.md and external field_notes/
2026-10-25_c140_sample_bank.md. Auto selects best-effort for this exact source.
No mix fallback; unsupported variants and missing observed ROM remain explicit.
Optional one-shot completion is cached/budgeted and falls back on unavailable
unplayed tails. Native source evidence remains separate from target capacity.

Validation:21 authored C140 checks passed, including pinned C-core oracle and
three public binary conversions. Relevant existing exporter/route/policy/stats
checks passed. Authorized BURNFC01 default succeeds; BURNFC02 requires --force
--no-song-loop for finite output (81 samples,295 retained/125 omitted playbacks,
110902-byte PDX). Normal song-loop continuation remains guarded. User owns full
local_only regression/listening. SALAMAND.log records10/10 user successes.

README unchanged; no staging/commit/push. Private/generated/reference-core data
remain ignored. Do not begin OKIM6295 or silently fake loop-seam attacks. Next:
user regression; investigate reported target/projection issues from diagnostics.

---

# PSG PCM auto policy and FM compiler consistency (2026-10-25)

Saved: auto selects best-effort for exact projected_msm6258_from_psg origin;
explicit strict and native/direct/DAC selection retain their rules. The typed
PCM compiler's FM-only rebuild now receives the same short_state_samples as
the readable MML, including configured threshold and normalization OFF. This
fixes a missing-option path, not a new musical approximation. Source evidence,
PCM assets/typed commands, baseline dumps and README are unchanged.

SALAMD01's existing diagnostics showed MDX track2 offset >0xfffe with a
476015-byte FM compiler input versus54548-byte readable MML. Its694338-byte
PDX fit the configured byte budget. Do not claim the file-size budget guarantees
playback memory. No local_only reconversion; user owns regression/listening.
Authored focused tests passed:6PCM policy,3PSG PCM,10FM short-state checks.
Public PSG+SCC batch validation and final review are recorded in the private note.
No staging, commit or push. Preserve earlier staged curve-backport changes.

---

# Shared PSG/SCC source-curve backport (2026-10-25)

Changes saved for: PSG/SCC -> OPM, including the existing SSG-to-PSG adapter; PSG -> PCM packaging.
Shared pure engines are synchronized with MSX; native adapters call analyze /
project at44100Hz before existing structure and target projection. Source
Segments/controls remain intact. Source-SSG register labels are mapped explicitly;
mixer writes stay protected. MGSDRV syntax/bank/tie rules were NOT transplanted.
DCSG and inherited MGS extract_notes are unchanged.

Minimal validation: 4 new native/packaging tests,2 existing PSG PCM,5 OPM performance,5 SCC projection tests passed.
No local_only fixture conversion or broad regression. The user owns listening
and full regression. Do not launch expensive compilers/emulators/catalog runs.
README unchanged. See docs/msx_curve_interpretation.md and external field_notes/
2026-10-25_shared_msx_curve_backport.md. No staging/commit/push. Preserve unrelated
working-tree files, including MUCOM's pre-existing -w.mub.

---

# Export package layout checkpoint (2026-10-24)

Default export_mdx now retains source-relative parent directories and publishes
flat tracks/ bundles, per-package diagnostics/source copies/manifests/results.
Omitted --outdir uses adjacent packages. Legacy manifests are protected, not
migrated. Failed reruns retain successful bundles and record latest attempt.
Validation: 51 focused tests passed. Independent public root/nested-package
checks passed, including repeated stems and partial reruns. Public CLOCK and
SEGAONE compiled; SEGAONE MDX references the adjacent flat PDX correctly.
No music interpretation or private-fixture conversion changed. See
docs/output_layout.md. No staging, commit or push.

# Active checkpoint: PCM auto policy and optional verification VGM

2026-10-23: requested changes saved in the working tree. No staging, commit or
push. The user owns local_only conversion/listening; no private VGM was
reconverted here. Existing staged and unrelated changes remain intact.

## Latest normalization sweep

User Nemesi95 sweep: normalization8/16/24/32/64ms, FM-state24 throughout.
All settings24/25 success; same NEME9525 variable-rate PCM blocker.
MDX totals (24 successful songs):275253/275081/275038/275205/279546bytes.
64ms reduces encoded loop pairs2059->1889 and omits2414 whole FM gates
versus1 at8ms. Five PCM-bearing PDX files have identical hashes across runs.
User reports no perceived listening issue; defaults remain unchanged.
Read-only aggregation, no private reconversion/code changes. See diagnostics
nemesi95_normalization_sweep_20261023 and external note
field_notes/2026-10-23_nemesi95_normalization_sweep.md.

## Latest user baseline (no normalization sweep)

Read-only results: Sion II 7/8 and Nemesi95 24/25 success (31/33 combined,
previously19/33). SIONII06 confirms FM-state24ms / normalization8ms in pass JSON.
SIONII06 retains one PCM sample/playback, PDX490861bytes within cap, but fails
MDX track8 start offset >0xfffe. NEME9525 playback0 includes rate change during
playback as well as irregular supply; current continuous-delivery fallback
handles irregular supply alone. Native issues=[]; variable-rate target playback
remains unimplemented. Do not simply whitelist the additional issue.
No private reconversion/listening or code changes in this baseline review.
See external field_notes/2026-10-23_sion_nemesi_default_baseline.md.

## Current defaults

- `--pcm-policy auto`: actual DAC supplies (including mixed direct B7 supplies)
  select best-effort; no actual DAC supply selects existing strict/direct
  handling. Unused declarations/setup do not select best-effort. Explicit
  strict/best-effort overrides remain. Non-DAC transcoding keeps prior strict
  behavior unless best-effort is explicitly selected.
- `export_mdx.py` and its API omit verification VGM by default. `--vgm` requests
  replay; legacy `--no-vgm` remains accepted. MML/MDX/required PDX still generate.
  Internal projected-source VGM evidence remains. API default is `no_vgm=True`.
- Earlier defaults remain: FM-state24ms (1058 samples), normalization8ms,
  stage timeout1200seconds, mmlx compiler, EX-PDX/optional standard PDX.

## Previous mixed-supply blockers and their correction

All14 new blockers had native issues=[] and only irregular_byte_supply on
playback0. Prior pan-upper-bit and unmapped0x17 corrections were applied.
All14 combine direct B7 and actual DAC supplies. The old continuous-PDX fallback
required every byte to be stream-derived, excluding mixed origin. The fallback
now shares eligibility across single/parallel PCM projection and size profiles:
known reset/pan, nonempty captured sample, no other source/playback issues and
consistent supply counts. Best-effort preserves bytes but loses supply timing;
strict rejects this explicit loss. No source flag is rewritten to eligible.

Source raw bytes, control times and prior cadence diagnostics remain intact.
The target assessment records direct/stream counts and
byte_supply_schedule_not_preserved. Sample length after reencoding/replacement
is not required to equal original supplied byte count. Unknown reset/play
state, missing banks, invalid codecs/rates and other source issues still block.

Auto selection is recorded in assessment policy_selection, result CSV fields,
console and TXT reports. Effective policy is separate from requested policy.
See docs/pcm_source_and_target.md and docs/pcm_pdx.md.

## Verification

Authored mixed input: default auto -> best-effort, MDX/774-byte PDX, no VGM.
Authored direct input: auto -> strict, MDX/896-byte PDX, no VGM.
Authored DCSG with --vgm: successful verification VGM generated.
Inspected native observations, source supply counts, target loss and policy
selection. Artifacts/verification.json:
outputs/diagnostics/msm6258_mixed_delivery_20261023/
Read-only latest14 failure summary: existing_failure_summary.csv there.
186 relevant automated tests passed; the count is stored in verification.json.
Architect found no remaining material issue in scope (read-only review).
Successful compilation does not establish listening/timing equivalence.

## Preserve preceding work / next scope

Single/dual DCSG-to-OPM is implemented: six tones, one interval-allocated noise
lane, explicit approximation/force omissions, native latch-preserving loop
replay, shared MSX note/volume-run interpretation and ordinary OPM structure.
See docs/dcsg_to_opm.md. KNIGHT listening mismatch remains unresolved; the latest
user report supersedes the older no-perceived-difference impression. Sweep
size/loop statistics are not fidelity evidence.

96 slots and1200000-byte PDX cap remain. EX-PDX does not fix MDX16-bit offsets or
whole-PDX memory. AFBII01/GFII04 bank resource/ROM/internal-loop work, compact run
capture and true multibank/enhancer work remain unfinished. Terminal handling
keeps ordered release writes and required KC/KF/TL restorations in repeat keys.

After user regression: agreed MSX catch-up and concrete MGSDRV one-attack plus
typed control-curve prototype; loops before SW-envelope sharing. Feed validated
work back into x68k/MUCOM. Do not automatically prune source PSG/SCC curves at
24ms or claim the FM threshold extracts PSG drum banks. No MUCOM/MSX changes
were made in this task.

External note (separate private repository, uncommitted):
field_notes/2026-10-23_pcm_auto_and_mixed_supply.md
Earlier source-profile, audit, sweep and DCSG notes remain there.

Public CLI check: scale_rom1.vgm -> PSG-to-OPM MDX MML succeeded with --dump-passes; artifacts are under outputs/diagnostics/curve_backport_20261025/psg_opm. No private regression was rerun.

Final review: silent-channel rest groups are retained in PCM diagnostics but cannot block complete sounding-group cuts. Authored packaging coverage includes a long overlapping rest.

Final validation: public psg_scc_001 exported MDX/PDX successfully with --psg-output pcm --scc-model additive --no-song-loop and no policy override; auto selected best-effort. Focused review found no critical issue. SALAMD01 itself has not been reconverted.

User follow-up: SALAMD01 PSG-to-PCM conversion succeeded and listening was confirmed after the FM compiler-setting fix (12 samples/playbacks, 0 omitted; EX-PDX 694338 bytes). User rerun explicitly used best-effort; auto was covered separately by public/authored checks.

## 2026-10-27 PDX library audit (read-only analysis)

H:/_env/D/MDX: 853 files, 844 validated including 10 LZX files; no library
changes or conversions. See ignored outputs/diagnostics/pdx_library_20261027/
analysis_ja.md and external field_notes/2026-10-27_pdx_library_and_mkpdx68.md.
Confirmed reference MXDRV Rel.X5-S default: 312 KiB, distinct from the user's
NanoDrive8 1,200,000-byte policy. Installed resident driver/options unmeasured.
MXCTRL adds a 270-byte transfer wrapper and keeps temporary data until after
transfer. No converter budgets/defaults changed. mkpdx68 is a single-bank,
96-slot/u32 packer; it does not detect resident memory, reencode or deduplicate.
Do not replace the packer or set a universal library-derived byte cap.
User is running MSX run_test.sh; leave that checkout/execution alone pending
completion notice. Preserve unfinished native-layer integration and existing
MSM6295 work. No commits/staging/push performed for this audit.

---

# Export default: finite one pass; VGM song loop is opt-in (2026-11-02)

User decision after the DQ3_06/DQ3_27 capacity failures: a first-time
user running the plain export should not hit compilation_failed on
popular songs. scripts/export_mdx.py now defaults to one finite
source pass; the declared VGM song loop (state-preserving second
traversal) is rendered only with --vgm-song-loop. --no-song-loop
remains accepted (it is the default). The canonical converter
vgm2mml.py keeps its own loop-on default; this is an export-layer
recipe default, like the C140 mix gain. README (ja/en) updated:
examples, option table, and the size troubleshooting note.

Measured effect (SMB3 World 1 Map, same input): default MDX
10,324 bytes with Song loop emitted=False; --vgm-song-loop
19,445 bytes emitted=True (~1.9x). The DQ3 failure analysis behind
this: compiled totals ~82 KB (06) / ~98 KB (27) against the
0xFFFE MDX track-offset limit, with the loop body (88% / 76% of
the song) stored twice and the busiest additive lane pair at
~61 KB on its own. One-pass estimates for DQ3 (from performed-unit
counts) are ~44 KB / ~55 KB, inside the limit; end-to-end
confirmation still needs the original DQ3 VGMs, which the user's
diagnostic archives did not include.

Verification: test_export_mdx (38) and test_opm_song_loop (6)
pass; full-suite failure set is the established 27 (a pristine
worktree shows 30 only because a fresh checkout lacks the .tools
setup -- SCC voice fitting core -- which is environmental).
Correction (2026-11-02): the "Missing PDX beside input" failure
once recorded here as a VM-only limitation was a misattribution.
It is a real bug, reproduced in the user's environment with
Gradius II (nearly every track): psg_scc_conversion._convert ran
the inner OPM conversion in projected_opm/ and lifted only the
MML and normalization JSON to the track folder, leaving the typed
MDX/PDX pair and the PCM assessment behind, so package assembly
could not find the PDX named by the MML. Any NES (or PSG/SCC)
conversion whose PCM bridge generates a typed pair was affected;
tracks without PCM references passed. Fixed on claude/nes-apu:
_convert now also lifts the pair (via the assessment's generated
artifact record) and the assessment JSON/CSV, and the tempdir
wrapper in convert() copies the same set. Verified: Gradius II
"Tabidachi (Air Battle)" went from compilation_failed to success
(typed_pcm_mmlx). Note a separate follow-on: tracks whose DPCM
playbacks contain stops/holds/resets still end as
pcm_replay_unavailable because soundlog 0.15.0 cannot preserve
them in replay verification; the MDX/PDX themselves are produced.

NES balance, third calibration (2026-11-03): BALANCE_GAINS pulse
1.3 -> 2.0 and noise 0.8 -> 1.2. Gradius II's own data caps pulse
volumes at 8 of 15, so the melodic lanes sat low against the ADPCM
hits even after the bridge went to 0.4; the lanes now rise toward
the PCM instead of only the PCM coming down (the SMB3 pattern from
the MSX route). Triangle 0.75 / dpcm 0.625 / dpcm_adpcm 0.4 are
unchanged. Full suite failure set identical before/after (28).
User's listening check on the regenerated Gradius II export is the
remaining step.

Target VGM deliverable (2026-11-03): --emit-vgm on vgm2mml.py and
export_mdx.py writes <stem>.target.vgm beside the MML for the
projected routes (PSG/SCC incl. NES, DCSG, OPNA): the projected FM
target VGM verbatim plus the PCM bridge's playbacks merged as
MSM6258 streams, minus the playbacks the binding omitted (read from
its omitted-playbacks CSV). New module py/target_vgm_emit.py; the
export publishes tracks/<stem>.target.vgm and records it in
results.csv. Native OPM routes print an explicit not-available note.
Validation: Gradius II Tabidachi FM sequence identical to the
projected target; 242/248 merged playbacks re-analyze issue-free
(the rest are retrigger cuts with sole irregular_byte_supply, which
the binding itself accepts); loop expansion lands exactly on
total + loop_samples; ymfm renders the finite export at 19.20 s.
OPNA real-data validation is still open (no YM2608 pack in the VM;
hook covered by unit tests). opn2_opm on claude/opn2 /
claude/opna-voice needs the same hook when the branches converge.
Full suite failure set identical before/after (28).
