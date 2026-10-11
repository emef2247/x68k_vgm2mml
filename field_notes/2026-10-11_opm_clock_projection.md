# Alternate OPM clock -> 4MHz MDX

GENPEI's existing conversion diagnostic declares 3,579,580Hz and was blocked
by the former requirement for a 4MHz source. No private source conversion or
game-derived contents were used in this change's validation.

Implemented a target-only nominal KC/KF projection, independent of time
normalization. Both musical renderers and register replay use the same controls
and target pitch-state view. Source State/Segments remain unchanged. See
`docs/opm_clock_projection.md` for assumptions and unretimed parameters.

## Verification

- 28 public/synthetic tests pass: `test_opm_mdx`, `test_opm_pitch_projection`,
  `test_opm_mdx_structure`, and the held-controls musical test.
- Eight new tests cover alternate clock ratios, aliases/rounding/octave carry,
  KC-only/KF-only updates, identity4MHz reserved-byte retention, target reset
  assumptions, range rejection including released tails, short-gate pruning,
  all notation/layout paths, target-state and strict replay comparisons.
- Public synthetic source `tone()+melody()` uses 3,579,580Hz. Target KC `0x48`,
  KF `20` replaces source KC `0x4a` and an explicitly assumed reset-zero KF.
  Nominal rounding error is about +0.064113 cents. MXC via run68 compiled all
  three notations; independent MDX->VGM replay had zero known-state mismatches.
- Public `opm_oki6258/opm_pcm_rates.vgm` copied to output-only test inputs with
  4MHz/3,579,580Hz OPM headers generated equal 896-byte PDX files. PCM rates
  and encoded bytes are unchanged by the FM correction.
- Inspectable outputs are under ignored `outputs/opm_clock_public_2026-10-11`.
  No native MMDSP playback or independent acoustic frequency measurement.
- Ordinary public `opm/from_fm/3ch_test/3ch_test.vgm` exported successfully
  through the default normalized MXC route. Its readable TXT reports 4MHz ->
  4MHz, `applied=False`, and no target reset assumptions. This checks report
  integration and an existing default-route export without a private batch.

## Traps fixed while checking affected paths

Generated pitch controls may share a source Key-On event ID. Short-gate
pruning must delete only the Key command, retaining injected pitch controls
needed by later surviving gates. Per-write normalization joins use event ID
plus target_sequence; source write counts use distinct source identities.

MXC v1.01 parsed inline `; event ...` after register commands as music. Register
MML provenance comments now occupy their own lines; no control-value change.
An old CLI test still expected only MML, although current CLI already emits
normalization and conversion diagnostics. Its expectation now covers those
existing artifacts explicitly.

## Next allowed action

User reruns the original GENPEI export command and listens in MMDSP. Preserve
the source IR and report any target pitch loss. No Git mutations without a new
explicit user instruction. The following follow-up supersedes the initial
range-error-only policy.

## GENPEI listening follow-up and target-policy correction

User reports 4/15 exports: GENPEI02,04,14 play and animate correctly; GENPEI15
sounds but freezes MMDSP without animation. Existing diagnostics show periods
15872,7168,15872,256 microseconds respectively. Failed tracks reject corrected
KC/KF below the target register range at 3,579,580Hz. Inspection of source
metadata shows KC=0 reinitialization after played channels; some low states
persist longer than 8ms, so treating every such update as a silent transient
would be unjustified. No private contents are reproduced here.

The user accepts nearest representable pitch for this register-range limit.
Native `--opm-pitch-policy clamp` is now the default, matching the existing PSG
FM policy. `error` remains available for strict rejection, including release
tails. Clamp audits retain source event, original KC/KF, target KC/KF and actual
nominal cents error. Counts refer to evaluated events, not unique notes. The
3,579,580Hz lower endpoint can differ by +192.251613 cents. This is a limit of
KC/KF-only retuning, not a claim that every possible hardware voice configuration
cannot reproduce the pitch. Regular retuning already changes note and octave;
the source State/Segment remains unchanged. EG/LFO/noise not being retimed is
reported as a limitation and does not itself reject conversion.

GENPEI15's old normalization rejects every nearest-tick candidate because
unclosed terminal gates are only 3,7,11 source samples. They are conservative
survivors, not complete Key-On/Off notes eligible for short-gate omission.
New normalization falls back to ordered allocation within the existing sample
movement budget. Exact integer tick domains, origin=0, adjacent order and
protected positive intervals form a DAG. Infeasible candidates still reject;
final errors/order/positive intervals are independently checked. The allocated
map is shared by FM, PCM and validators and exposed by normalization pass CSV.

Focused public/synthetic checks cover clamp at both ends, strict policy in all
notation/layout routes, native CLI, source preservation, exact-domain feasible
and infeasible cases, terminal gates, adjacent gates/rests, PCM shared timing
and TXT reporting. Forty selected test cases pass in the final focused run.
Two test issues were corrected: synthetic VGM waits must fit16 bits, and the
existing track-comment test must allow standalone provenance comments.

Two native MXC exports succeed under ignored
`outputs/opm_clock_followup_2026-10-11`: CLAMP explicitly reports pitch loss;
TAIL preserves all terminal key requests, selects12544us/tick (@t207), moves
at most327samples within352, and omits no gates. The source end748139 maps
to748466; terminal starts748128/132/136 map to tick1352 and end to1353.
Pass CSVs and readable TXT were inspected. Final review also fixed two timing
traps: retained pitch injection must not turn an omitted Key-On into an onset
anchor; nonchanging source events need allocated timestamps too, so validation
cannot reverse their order by falling back to independent nearest rounding.
Their regressions pass, including projected-state replay comparison. Final
MML after these fixes is byte-identical to the two compiled examples.
This is public authored evidence,
not a new GENPEI conversion or native MMDSP test.

Next: user regenerates GENPEI into a fresh outdir and checks the reported
periods plus native display/playback. The fixed period of GENPEI15 is not yet
measured; the public12544us example is not a claim about that private track.

## User batch result after the fixes

On 2026-10-11 the user reran `scripts/export_mdx.py` against local_only GENPEI
with `--no-vgm --pcm-policy best-effort`, using the default clamp and8ms policies.
GENPEI01 through GENPEI15 all report success:15/15 exported. The user's results
are at `outputs/listen/opm/vgmrips.net/GENPEI/results.csv`.
This confirms file generation for all previously failing tracks. The latest
message does not report native playback/display or the new GENPEI15 period;
those remain the next listening checks. No additional conversion/test or Git
mutation was performed by the agent for this result-recording update.

## Native listening result and next checkpoint

The user subsequently reports all15 tracks play and animate in MMDSP, with
two residual observations: GENPEI10 briefly stops animating near the beginning
and later recovers; GENPEI07 reaches a sudden mid-song end and keeps sounding.
The new generated reports specify GENPEI07=15872us (@t194), GENPEI10=7424us
(@t227), GENPEI15=11520us (@t211). These are encoded clock selections, not
measurements of interrupt load. The previous GENPEI15 freeze is no longer
reported. GENPEI10 is not simply a remaining256us clock case; its temporary
display issue needs separate investigation.

Read-only source metadata confirms GENPEI07 has a valid declared VGM loop:
entry937613samples (21.261066s), end2271552samples (51.509116s), loop length
1333939samples. All8 channels' last key masks are15 at stream end. Thus the
stream end is a loop seam rather than evidence of a natural Key-Off ending.
GENPEI10 and15 also declare valid loops. No0x12/0x14 timer control writes were
observed in these three source streams. No new private conversion was run.

Current code records the declared VGM loop and protects its timing boundary,
but does not transfer it into an infinite MML song loop. Finite-repeat
compression (`--no-loops`) is a different feature. User explicitly requests
declared song-loop transfer to be enabled by default for looped inputs.
Implementation is deferred at the user's usage-limit checkpoint; this commit
candidate contains clock/pitch/timing fixes and evidence, not song-loop support.

Next implementation must keep source IR intact, preserve loop byte-command
position and same-sample ordering, split held spans without invented Key-On,
respect chip/MML state carried across the seam, and account for source writes
that were redundant only on the first pass. Validate multiple iterations with
public authored cases and native compiler evidence before private listening.
Review the major loop plan with architect before implementation. Separate an
explicit one-pass opt-out from finite-repeat compression. Do not add an end
Key-Off as if it were source evidence or silently restart at song origin.
