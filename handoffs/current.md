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
