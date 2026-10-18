# PCM round-trip validation and an independent reference

Japanese original: [pcm_roundtrip_validationJ.md](pcm_roundtrip_validationJ.md).

Findings from 2026-10-09. This is a validation design, not an implementation or success report for PCM round-trip validation.

2026-10-10 addendum: Normal MDX generation with PCM now uses the 16-track + E8 PCM extension route confirmed by listening.
The standard 9-track/PCM1 reference below remains a candidate for independent validation, but validating current output
requires a separate profile that also fixes the PCM extension version and execution route. The six successful playback/stop
cases are individual listening results; they do not establish successful A/B/C round trips or guarantee reset behavior,
consumed nibble counts, or mid-playback pan. See [pcm_pdx.md](pcm_pdx.md) for current generation conditions and CLI,
and the [field note](../field_notes/2026-10-09_pcm_mxdrv_roundtrip_review.md) for the investigation evidence.

## Goals and problem categories

The goal is a semantic round trip: `VGM -> PCM IR -> MDX+PDX -> VGM`.
OPM uses the existing musical generation route. PCM retains encoded samples and playback information in the IR,
then projects them into MDX PCM commands and PDX. PCM MML text is optional readable output, not a mandatory intermediate format.
Direct PCM MDX output and strict/best-effort projection assessment are implemented. An independent playback reference and A/B/C comparisons are not implemented.

| Layer | Problem | If PCM MML is omitted |
|---|---|---|
| MML/compiler | Notation, numeric sample notes, tie placement, and mmlx selecting 16 tracks even for P alone | Avoids problems originating in text conversion or the compiler |
| MDX runtime expressibility | When and what F7 hold, FC pan, and ED rate affect in standard MXDRV | Remains. Writing MDX directly does not change command semantics |
| MDX+PDX playback converter | Lost cursor, missing stop output, fixed rate/pan, incorrectly reconstructed decoder state | Remains. Also validate original MDX that has not passed through MML |

Do not classify all reported tie problems as originating in MML. soundlog losing its raw cursor on non-Note commands
is an MDX runtime problem. F7/KeyOffDisable, FC/pan, and ED/F are also MDX binary commands.
If mid-playback pan does not affect effective output in the standard environment, changing the playback converter to apply it
immediately is not correct. Diagnose that difference as a known semantic loss in target projection. Conversion need not always
be rejected; strict and best-effort use different artifact-generation policies.

In the ordinary PCM1 route of MXDRV 2.06+17 Rel.X5-S examined here, FC and ED save track state and take effect at the next
new ADPCMOUT. Inserting FC during a hold does not issue an immediate pan change to IOCS.
Earlier tie + mid-playback pan output is not evidence that this version reproduces the original VGM's immediate pan changes.
Current projection rejects this in strict mode; best-effort retains the starting pan and records the loss interval.

Stream expansion for finite bank `0x04` was implemented and validated as a transfer sequence based on a fixed libvgm profile.
This does not validate decoder consumption or execution by standard MXDRV; `consumed_nibbles=None` is retained.
Unsupported compressed banks/stream modes are also diagnosed explicitly. See [PCM/PDX](pcm_pdx.md) for details.

## strict / best-effort and four assessment outcomes

An additional user policy is that inability to represent something perfectly on the target must not automatically reject all conversion.
MDX target projection determines loss/eligibility from the source IR, target profile, and verified rules.
Do not change the original pan, rate, reset/continuation, times, or bytes in the PCM IR.
Retain source-level unobservability and unresolved interpretation as source evidence; do not conflate them with losses imposed by target specifications.

| Item outcome | Meaning |
|---|---|
| `pass` | Semantics that should match in the specified scope/profile do match, including the necessary evidence and validation |
| `lossy` (`known loss`) | Target constraints and the selected approximation identify which semantics are lost and how |
| `unverified` | Behavior or agreement cannot yet be judged because of IOCS, source interpretation, insufficient observations, unperformed validation, etc. |
| `fail` | A mismatch where agreement is required, a defective implementation of the selected approximation, an invalid artifact, etc. has been confirmed |

Always record the assessment scope. A target eligibility `pass` is not a PCM runtime round-trip `pass`.
Do not promote successful generation, parsing, or static reference checks to runtime outcomes either.
A known loss that blocks generation under strict policy is a `lossy` diagnosis, not a playback implementation `fail`.
Here, `lossy` assesses the planned projection, not execution validation of a generated artifact.
Also record `artifact_status=blocked` and `validation_run=not_run`, leaving the runtime outcome unverified.

| Conversion policy | Artifact handling |
|---|---|
| `strict` | Do not output a projection with known semantic loss. Retain source evidence and the reason |
| `best-effort` | When explicitly selected by the user, output generatable MDX+PDX with defined approximations and loss diagnostics |

strict means “do not allow known loss”; it does not mean certification in an independent environment.
If a concrete, internally consistent target plan can be made but IOCS or other details remain unverified, the result stays `unverified` even if artifacts are generated.
If unknown decoder consumption or similar issues prevent defining the target plan itself, generation may be deferred even in best-effort mode.
best-effort does not unconditionally ignore unknown behavior, broken PDX, missing references, or unimplemented source analysis.
If an approximation cannot be defined or output cannot be generated, record the reason and scope.

The current CLI is `--pcm-policy strict|best-effort`, defaulting to strict.
Successful conversion exits with 0; blocked generation exits nonzero. The four assessment outcomes are saved in `*.pcm.assessment.json`/CSV.
Batch processing status and semantic assessment use separate columns. PCM replay unavailable remains in place.

Store artifact-generation status separately from semantic outcomes.
The report design includes `policy`, `target_profile`, `artifact_status` (generated/blocked/error),
per-item assessments, `known_losses`, `unverified_items`, `unexpected_mismatches`,
assessment scope, and validation execution status. Generation alone must not yield `pass`.
The overall validation status is `fail` if there is an actual failure; `unverified` if any required item is unverified;
`lossy` if everything else is verified and known losses remain; and `pass` if all required items match.
Do not hide known losses when unverified items make the overall result `unverified`. Do not mark unperformed comparisons `pass`.

### Best-effort projection of mid-playback pan

When mid-playback pan is confirmed not to apply in the specified ordinary PCM1 profile,
a candidate approximation retains pan from the new note start and does not apply changes during the hold to the target.
Explicitly set the source pan current at the next new note start.
Do not add artificial retriggers or decoder resets to imitate pan changes.
Retain the source pan trajectory unchanged in the IR; emit the target plan and diagnostics separately.

Diagnostics must include at least:

- Loss code/cause (`target_constraint`), the verified profile and evidence, and the selected fallback rule.
- Source playback/event ID, original times and affected intervals, and source/projected values.
- Lost pan changes/mute intervals and the resulting differences in audibility.
- Preserved items such as sample/cursor/timing, and separately unverified items such as reset/consumption.

Record how each interval is planned to play, rather than merely saying “pan commands were dropped.”
Known-loss diagnostics are based on the target plan. If runtime confirmation is pending, record that lack of confirmation too.
Other constraints such as sample length require separate fallback rules and validation; do not truncate unconditionally.

## Separate playback states

The following states are distinct:

1. MDX notes, gate/keyoff requests, F7, rests, and pan/rate/bank settings.
2. MXDRV sample selection, hold state, IOCS calls, and driver ticks.
3. IOCS/DMA transfer ranges, cursors, completion/interruption/resumption, and rate/pan settings.
4. Chip PLAY/STOP, data input, nibble phase, decoder state, and effective rate/pan.
5. VGM data banks, stream start/stop/position, and write frequency.

VGM `0x94` stops a stream; it does not directly mean chip STOP. `0x95` is not chip PLAY or reset either.
`0x92` is write frequency, distinct from the nibble consumption rate of 4-bit ADPCM.
Record cursor movement to the sample start, note re-requests, and decoder reset separately too.
Verify STOP/PLAY-related reset in the selected chip model; do not add a reset per note by inference.

## Missing pieces

| Subject | Required implementation/evidence | Current gap |
|---|---|---|
| Start/hold | Execution rules for F7, gate, key-on delay, same/different samples, and rests | raw cursor and logical hold lifetimes do not match in soundlog |
| sample/cursor | PDX ranges, transfer position, nibble phase, EOF, early cutoff, transition to next sample | Supplied bytes are retained, but actual consumption is unresolved |
| PDX length/bank | Separately validate container storage capacity and the selected native version's read capability | The examined PCM1 route uses the trailing 16 bits of length. The packer's 24-bit limit does not guarantee native playback |
| Completion/interruption/resumption | Requests from MXDRV to IOCS and effective DMA/chip behavior | Correspondence between stream stop, DMA completion, chip STOP, and keyoff has not been independently verified |
| reset/continuation | State transitions separating predictor and step, cursor, and PLAY state | Original VGM reset relationships cannot be reproduced, and the standard IOCS reference is unresolved |
| rate | When ED settings take effect, OPM CT output/PPI/divider, exact rational rates | Comparing F numbers alone is insufficient. Write frequency and consumption rate must be separated |
| pan | FC requested values, effective application time through IOCS/PPI, mute and decoder continuation | Current tie + pan mid-playback changes are unverified in effective playback |
| Time | Tempo/timer across all tracks, synchronization/gate/delay, DMA and decoder clocks, same-time order | MDX boundary quantization checks alone do not guarantee transfer/consumption |
| VGM output | Mapping block IDs to PDX slots, stream/direct writes, chip-control consistency | The Leonardo version has fixed rate/pan and a stop stub. soundlog is also uncertified as a reference |
| VGM input | Expansion of streams into actual data writes, order relative to direct writes, supply/consumption state | Currently stream/bank handling only retains raw data and rejects it |

## Independent execution reference R

The first candidate is environment R, running a specific native MXDRV version on real X68000 hardware or an independent full-system emulator.
Limit its scope to standard 9-track/PCM1 without PCM8, and fix and record at least:

- MXDRV version, executable binary hash, and documentation/disassembly sources.
- Machine model, ROM IOCS version/hash, and whether replacements such as PCM8 or XAPNEL are present.
- OPM/ADPCM clocks, divider, initialization/start procedure, and loop count/end condition.
- Emulator version/commit, chip/DMA model, and trace observation points and clocks.

Because ROM IOCS behavior is included, do not label the reference merely “standard MXDRV.”
Native disassembly of MXDRV 2.06+17 Rel.X5-S was examined as evidence,
but execution reference R using that binary and ROM has not yet been prepared or run.
Available traces from hardware/an independent emulator also need investigation.

The disassembly of this version shows that F7 suppresses gate keyoff; a subsequent note request for active PCM
returns before sample lookup; FC/ED carry forward to the next ADPCMOUT;
new PCM1 start uses ADPCMMOD(0)→ADPCMOUT; and gate keyoff conditionally uses ADPCMMOD(1)→(0).
This supports the driver/IOCS request layer of C1; it does not guarantee a physical reset inside IOCS.

IOCS calls alone cannot prove physical PLAY/STOP/reset or actual consumption.
In R, observe timestamped OPM/PPI/ADPCM writes and DMA data transfers.
Assessing consumed nibble counts also requires observation of decoder input position/state or a separately certified chip model.
Items that cannot be obtained remain unverified. Retain audio comparison and listening comparisons on hardware separately as supporting evidence.

Use NanoDrive8, a separate player driving physical sound hardware, for state design and difference investigation.
Its control differs from native MXDRV + ROM IOCS, so it is not the standard oracle.
portable_mdx/MXDRVg are candidates for auxiliary host references, but adopt them only after checking correspondence to the original driver,
IOCS-equivalent processing, and state/timing on the X68Sound side.
Do not count multiple codebases of the same origin as fully independent evidence.
Do not use soundlog or the unmodified Leonardo version to generate expected values.

## A/B/C and isolating failure locations

```text
original MDX+PDX --R--> VGM0 --vgm2mml native analysis--> A
        |
        +--independent direct analysis--> C0 --validated semantics/profile--> C1

A --target projection--> generated MDX+PDX --R--> VGM_ref --analysis--> B_ref
                                     |
                                     +--player under test P--> VGM_P --analysis--> B
```

`analysis` extends through OPM/PCM source interpretation. Do not compare target-quantized/normalized output with source Segments.
R must use an execution route separate from the converter/P. Obtain B_ref from the first small fixture onward.

| Comparison | What it assesses |
|---|---|
| C1 and A | Whether VGM conversion of original MDX execution and VGM source analysis match direct analysis/the independent reference |
| A and B_ref | Whether projection from source IR into generated MDX+PDX preserves playback in the standard environment |
| B_ref and B | Whether P reproduces standard-environment behavior for the same generated MDX+PDX |
| A and B, C1 and B_ref/B | The final round trip, and whether errors across routes cancel each other out |

A/B agreement alone is evidence of internal consistency; it does not certify correct standard playback.
Also compare the first R→VGM0 stage with its trace before the VGM formatter.
If C1 and R reuse the same implementation, explicitly describe this as comparison through different observation methods;
do not count it as independent sequencer/IOCS evidence.

`C ≈ A ≈ B` is shorthand for the goal. Agreement within tolerance is not transitive,
so assess each route/item separately and compare each required pair above.

Do not omit A/B/C comparison for best-effort artifacts either.
Report known losses between A and B_ref as `lossy`; do not count them as strict round-trip success.
Separately validate that the approximation in the selected target plan is actually reproduced and unaffected items match.
Determine the expected target plan after fallback from rules and source evidence before inspecting the actual output being compared.
Distinguish source-to-expected-target-plan differences as known loss, and expected-target-plan-to-actual-output differences as validation mismatches.
Do not hide extra retriggers, resets, or timing defects by simply excluding loss intervals from comparison.
For B_ref and B playing the same generated MDX+PDX, source→target loss is not a reason to allow differences.
If the playback converter departs from the target plan/standard environment, use `fail`; if evidence is insufficient, use `unverified`.

## Direct analysis C of original MDX+PDX

Build C0 directly from MDX commands and PDX, without reverse-converting to MML.
Retain every PDX slot, original offset/length, and encoded bytes, plus MDX track/byte offsets.
Retain commands such as note/rest/F7/F8/FC/ED/FD, repeat/end/escape, tempo, synchronization, and delay.
Reading command sequences alone does not reveal playback times. Execution control must be interpreted to determine time across tracks.
OPM also requires execution interpretation, including voices, software LFO, and shared control.

C1 maps C0 to effective playback information according to verified rules of the selected MXDRV and the IOCS profile.
Separate requested pan/rate from effective pan/rate, note requests from sample starts, and gate requests from physical stops.
Leave unknown items marked unknown with their sources. Do not create a complete C through new guesses.

There is no need to uniquely reconstruct original F7, q, or F command placement from VGM.
Do not make those command sequences themselves mandatory A/B equality criteria; compare observable behavior after mapping to C1.
Different MDX structures, slot assignments, and loop representations that describe the same playback are acceptable.

## Semantic comparison items

Do not require matching source IDs, slot numbers, VGM block IDs, or Segment row counts.
Even if Segment boundaries differ, compare state intervals using common time boundaries.
Compare edges such as note starts, stops, and resets as separate ordered events; do not erase them by merging intervals.

| PCM item | Comparison method |
|---|---|
| sample | codec/bit order/output precision and actual bytes. Hashes are indexes; ultimately compare bytes |
| All assets and playback ranges | Distinguish all assets in the original PDX from prefixes/slices supplied/consumed in VGM. Do not treat an unplayed suffix after cutoff as missing |
| Start/end | Distinguish logical triggers, data supply start/end, physical PLAY/STOP, and audible start/end; compare times and order |
| continuation/reset | Separately compare continuity between playbacks, cursor rewind, decoder reset, and reset evidence |
| cursor/consumption | Byte offsets, nibble positions, and consumed ranges. Do not substitute supplied byte counts for consumption |
| rate | clock/divider, rational nibble rate, and effective change times. Compare stream write cadence separately |
| pan | Effective L/R/mute trajectories over time. Retain whether decoder/cursor advances during mute |
| End reason | gate, rest, sample EOF, explicit stop, song end, and ending/continuation due to loops |
| timing/loop | Common time origin, same-time order, tempo boundaries, and decoder/cursor state at loop entry/exit |

If IOCS prepends/appends stabilization data, record its origin as verified in that profile.
Do not remove fixed byte sequences such as `0x80` as generic silence.
For all PDX assets and unplayed suffixes unrecoverable from VGM alone, assess container information from C separately from playback agreement.
Requiring recovery of all assets for a general VGM round trip would require information that was never observed.

For OPM, compare effective states and times for each operator's key edges/masks, KC/KF, voice/operator parameters, volume, pan,
and LFO/noise/shared control.
Include post-KeyOff state and settings affecting release. Do not fill unknown source registers with invented known values.
Do not equate meaningful KeyOff/KeyOn or reset differences merely because the final state is identical.
Retain raw-sequence comparison for diagnostics, but do not substitute it for semantic acceptance criteria.

## Time and acceptance criteria

- VGM0→A and VGM_ref/P→B_ref/B preserve integer sample times and same-time order.
- Measure time rounding in R/P→VGM using the original trace clock and conversion formula.
  If rounding only to 44.1 kHz, within 1 sample is a candidate tolerance; do not guarantee it before checking the acquisition method.
- Store source/target times in separate columns for A→MDX projection boundary errors.
  The current 6-sample upper bound constrains note/control boundaries in this projection.
- Do not reuse the 6-sample tolerance for differences in decoder consumption, reset counts, sample bytes, same-time order, or supply intervals.
  Investigate cumulative drift from rate rounding during long playback and underruns separately.
- If excluding a startup warmup/initialization offset, use only one offset verified in the profile,
  and retain original times. Do not hide differences through per-track rebasing or arbitrary time warping.
- End loops after a specified count/time; also compare state and continuation relationships at that point.

Emit per-item pass/lossy(known loss)/unverified/fail outcomes.
For a strict round trip, lossy is not success; unknown required items also preclude a claim of successful PCM round trip.
Separate results for MML generation, MDX parsing, PDX bytes/static refs, semantic comparison, and audio/hardware comparison.
Alongside values, CSV must retain original/derived time, source offset, observation/inference/assumption,
profile, and reasons for unverified items. Add schemas without replacing existing raw/state/sample dumps.

## Next implementation and validation order

1. Fix the native MXDRV version and ROM IOCS profile, and confirm observation methods for independent environment R.
2. Use short self-authored MDX+PDX to investigate effective rules for single notes, same/different samples, long holds, before/after F7, rests, gates,
   EOF, mid-playback pan/F, delay/tempo/synchronization. Do not generate samples or handwritten expectations with soundlog.
3. Prepare direct C0 analysis, a limited evidence-backed C1 schema, and comparison information from R traces.
   Add the four assessment outcomes and loss reports to target projection, separating strict/best-effort.
   Assess expressibility and defined fallbacks for mid-playback pan and similar cases, and reflect them in current generation descriptions/target eligibility.
4. Retain the current raw/state IR while adding VGM streams and a consumption model; validate source interpretation against independent traces.
5. Add output that builds PCM MDX commands from the same sample bindings.
   Use the existing OPM route and typed MDX builder; do not require PCM MML or a new MML compiler.
6. Compare A/C1/B_ref starting with small fixtures to certify projection and source interpretation.
   Limit fixes to P to verified standard rules, and compare B_ref/B for the same generated MDX.
7. Expand public fixtures before extending to local original MDX+PDX and general VGM.
   Do not put ROM/song/sample bytes in git. Z_MUSIC consumes the same PCM IR through a separate profile/backend.

The current `verify_opm_mdx_roundtrip.py` validates OPM; this PCM A/B/C validation is not implemented.
Do not document new validation commands in README as though a usable CLI exists.
