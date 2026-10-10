Project: x68k_vgm2mml
Branch: codex/pcm-stream-support
Checkpoint: 2026-10-11

LATEST CHECKPOINT (supersedes all next-action/authorization statements below):
User requests committing current implementation before verification so they
can take over during the usage reset. Commit is authorized; push is not.
Complete <=8 ms gates are classified on original Key-On/Key-Off timing before
normalization; source Segment/State/PCM IR and PDX bytes remain intact.
PSG/SCC source-map timing is passed into classification. Short rests may
coalesce with both key requests retained; loss is explicitly reported.
Only minimal public checks are requested. Rebuild Rust release helper before
exporting PCM; do not run local_only or repair canceled clock patterns.
Commands and unverified limitations:
field_notes/2026-10-11_short_gate_checkpoint.md.

LATEST USER CHECKPOINT (supersedes clock next-action statements below):
All clock_control cases are inaudible in XM6 TypeG / MMDSP, counters advance,
and MMDSP remains responsive during playback. The user ended this experiment;
do not repair or regenerate authored clock patterns. Responsiveness is the
only positive native result; the timer hypothesis remains unproven.
Active work: fix public opm/from_fm routing failures without ignoring active
chips, and apply output normalization across structured MDX source paths
including shared OPM/PCM timing. Source times, Segments, PCM IR and sample
bytes remain immutable; fallback retains structured baseline timing.
No local_only conversions or commit/push authorized.

LATEST CLOCK FAILURE CHECKPOINT (supersedes listening-ready statements below):
User reports canonical CLOCK.mdx no-song-data/file-read-error; all four old
CLK references load but are inaudible and have no animation. Record in public
clock_listening/listening_results.json; unchanged failed bytes archived under
outputs/listen/clock_failed_20261010/. mdxinfo Success and identical FMSTATE/
CLK8192 voice bytes do not establish native validity. No timer/voice-format
cause found. Do not present old clock package as a working baseline.
New generator generate_fmstate_clock_controls.py uses exact proven public
FMSTATE copy, FMONLY PDX-header-only probe and five equal-time repeated phrase
clock cases with baseline voices/A/P. outputs/listen/clock_controls/ is the
separate new package; native outcomes unverified. Next allowed action: user
checks FMSTATE -> FMONLY -> FM4096 -> remaining clocks. No production timing,
sourceIR, end or command-order change; no local_only conversion. Details:
field_notes/2026-10-10_clock_baseline_failure.md. Do not use mdxtools mdx2pcm
WAV duration as oracle: it saves only half each interleaved sample block.

NEW PUBLIC CLOCK/LISTENING CHECKPOINT:
User's vgm-conv NEMESIS inputs still show frozen GUI after multi-dot filenames
are manually corrected. Both GRA1_01 paths select256us; ARMBS1 selects8192us.
The vgm-conv source has onlyinitialKeyOn and nativeoutput rawheldregister/rest
commands; inspectclock andarticulation separately. No productiontimingfix.
Authored tests/fixtures/public/opm/clock_listening/CLOCK.vgm is sparseFM,
8notes/~8.4s, from16384us reference; canonicalprojection selects8192us.
Four fixedclockrefs256/2048/8192/16384us preservephysicalscore expectations.
outputs/listen/clock_listening_reference/ and clock_native/ are listening-ready,
nativeoutcomes unverified. Use ordinaryNOTE comparisons before timerhypotheses.
export_mdx CLI nowpublishes singleextension shortnames undertracks/<safe>/,
preservesportable8char names, stagesidenticalsourcebytes, keepsdiagnostics
separate andconsistentPDXreference. Source/name/hash mappinginmanifest/results.
No binarypatching, no diagnosticdeletion; reportgenerationstatus separate from
artifactstatus. Details inREADME and latestlisteningfollowupfieldnote.
Validation:42export/report/listeningtests+13Rusttests pass. Realshortnamepublic
PCMexport11/11; independent11/11source/name/hash/PDXreferenceaudits pass.
CLOCKcanonicalMXCexport1/1 with8NOTEcommands/@t224. NativeGUI/endresults
remainusercheck; no claim that timerhypothesis orARMBS1ending was fixed.

LATEST FOLLOW-UP (supersedes earlier next-action lines): production listening
results are recorded in field_notes/2026-10-10_mmdsp_listening_followup.md.
BOSCON04/06/08 play/stop; other successful BOSCON files exceed native track
buffer. Public tiny stream fixtures contain their expected 2-4 byte payloads,
but reported PCM load failures remain unresolved. Long PDX names are a candidate
to isolate, not a proven cause. ARMBS1 has no PCM, animates but leaves sound;
NEMESIS plays/stops but has no animation and blocks user controls during play.
Fast MDX clock/driver load is a hypothesis only. Existing finite_end_tail passes
remain valid. Do not rerun local_only conversions automatically or change source
IR, clock, end gates or MML command order from these observations alone.
export_mdx.py writes per-input TXT statistics and keeps diagnostic artifacts.
Rebuild helper for --inspect-commands. Next: public short-name/load probe and
longer authored listening cases; inspect FM end boundary before a stop fix.
No deletion/commit/push requested.

CURRENT PRODUCTION CHECKPOINT (supersedes pending/paused statements below):
User confirmed all six current16-track/E8 finite_end_tail rootMDX play and stop
correctly. New hashes/listeningpass are recorded, oldstandard9failures retained.
Production --compile-pcm now selects16/E8 with onlyP active, Q-W finiteends;
typedcommand/title/tone/PDX preservation is checked. Python layout guard rejects
oldhelpers. Rebuildscripts/mdx_fixture_generator beforeWSL use. NeutralPCMIR,
samplebytes/sharedclock/sourceinterpretation are unchanged. Longerthan65535
samples stayblocked asunverified scope, not assertedextendedformatloss.
export_mdx.py --no-vgm generates MML/MDX/PDX withoutreplay; defaultreplay and
roundtrip remain. Public inputfixtures movedto tests/fixtures/public/opm_oki6258.
138public/authored tests and12Rusttests pass; actual11-inputpublicbatchsuccess,
10pairs independentaudit16/E8/validbindings. mdxinfoSuccess/title/PDXresolved,
butzero-toneoffset triggersitsTracks=-1limitation; nofalsemodeverificationclaim.
See field_notes/2026-10-10_pcm_extended_production.md forcommands/evidence.
Next: userlocal_only conversion/listening. Do notrunlocalchecks automatically,
resumeorderingresearch, changePCMsourceIR orclaimruntime/roundtripcertification.
No commit/push requested.

CURRENT LISTENING CHECKPOINT: per user request, extra ordering investigation is
paused. finite_end_tail root now contains six16-track/E8 versions, preserving
all original notes/control order/time/tones/MML/PDX. Failed9-track generation
and its listening evidence are archived under original_standard9/. New bytes
have native outcomes unverified; mdxinfo Success/16/PCM8=1 for all six. See
validation_extended.json and expected_extended/. User will test animation,
natural ending and sustained silence. No production conversion change.

RayForce full-bank audit: RAY01C has3banks64/66/26 populated slots, uses0/1;
RAYFOR has1bank28 populated slots. All360/446 interpreted PCM requests bind.
Existing soundlog0.15 PdxBuilder repacks BOTH entire PDX byte-identically.
The new data chain is nativeMXC9 output -> typed soundlog extended-mode
projection, with fixedPDX; a separate mmlx default16 RATES also preserved
requested events/used voice, retaining one unused extra voice. Neither new
chain has yet passed user listening. Limited pre-note ordering probes passed;
do not expand them now. Relevant23 tests passed. Details/reproduction:
field_notes/2026-10-10_rayforce_extended_structure.md.

Do not rerun historical tail generators/recording helpers on the updated root
package: they may overwrite16-mode data or mislabel new bytes with old failures.
generate_mdx_extended_tail_trials.py safely consumes archived9-mode originals.

LATEST LISTENING FOLLOW-UP: all six MDX files in finite_end_tail leave continuing
noise: RATES, RATESF, RATESP, FS432, FS432F and FS432P.
Trailing-rest extension is a failed remedy. RATES later emits scale-like sounds
with rising octaves while the GUI remains stopped; whether this is FM is not
established. Final explicit clarification: both RAY01C and RAYFOR0 in
finite_end_references end normally. These two originals are now user-confirmed
finite-ending references; earlier ambiguous replies are superseded. Recorded
static and listening outcomes remain separate; package listening_results.json
retains chronology.

Focused encoded comparison: RAY01C, RAYFOR0, HOLDEND, RATES and FS432 all end
each track with F1 00 within its boundary; no bytes remain after that ending.
First 96 PDX slot ranges are valid. Finite originals have 16 tracks and E8;
trials/HOLDEND have 9 and no E8. The difference is not a proven cause: HOLDEND
already stops with 9 tracks. Private results: outputs/reference_validation_
2026-10-10/ending_structure/. Production remains paused. Do not add more rests
blindly or attribute the noise to source IR or runtime from these facts alone.

LATEST UPDATE: user reports original FF4SIREN loops and F7 duringplay stops;
RATES and all three private finite phrases leave the same noise after natural
completion, while F7 during replay stops. RATES F7 after noise starts fails.
RATES already ends with72ticks rest onA/P. Cause remainsunknown; buffer overrun
is a hypothesis. New native-MXC diagnostic trials extend onlyA or onlyP by
equal silent intervals, preserving originals/PDX/prefix: RATESF/P add4.194s;
FS432F/P add5.210s. See outputs/listen/finite_end_tail/README.md. All static
checks pass; native tail outcomes unverified. No production change.

Original reference audit:15decoded/alldeclaredPDXpairsfound,13loops/2finite.
RAY01C.MDX/RAY01C.PDX is finite with PCM U/V/W lastnote/q8release4080tick,
FM lastnote/release3864 with216ticktailrest; all16tracksend4080. RAYFOR0 is
also nominalPCMlast3192vsFM3122, but finalU/Vvolume0 andotherheldPCMnotes
prevent an acoustic-latest claim. Exactoriginalcopies are in
outputs/listen/finite_end_references/. FullCSV/JSON+compactoverview under
outputs/reference_validation_2026-10-10/original_end_timeline/.
Diagnostic reader now hasopt-in16tracks/E8/F2encoded-only; source IR unchanged.
17reference/audit tests+5selector/tailtests pass. See
field_notes/2026-10-10_finite_end_tail_and_reference_audit.md.
Next: user listening of tail variants and finite RAY01C original. Keep physical
cessation separate from gate/sequence intentions and manualF7 separate from
MDXholdF7. Historical generated-only native-unverified statements below refer
to initialgeneration; newlistening_results.json contains actualfailedendings.

Current scope: the user is validating generated MML/PCM data against working
references. Production conversion changes remain paused. Authorized validation
tools/assets and private reference-derived phrases have been created. Do not
repair unrelated replay tools or ask playback-environment questions as a
prerequisite. Do not commit/push automatically.

Latest user listening evidence (copied public reference files):
- All four files animate correctly in MMDSP and are audible.
- HOLDEND stops correctly.
- RATES leaves continuing noise after the data ends: retained runtime fail.
- GATEEND cessation was not separately reported.
- Cause is unknown; no compiler/player/sample/rate attribution established.
Public listening_results.json retains results separately from static checks.

Latest deliverables:
- tests/scripts/generate_local_mdx_reference_phrases.py creates private FF4SIREN
  FS432 (5.86 s/3 PCM requests), FS768 (10.42 s/30), FSONE (49.66 s/255).
- local_only/derived_mdx/FF4SIREN/ contains MML, PCM expectation JSON, native MXC
  MDX, exact regenerated original PDX, original/candidate JSON/CSV and provenance.
- outputs/listen/reference_ff4siren/ is the listening copy. Playback needs the
  three MDX files and FF4SIREN.PDX together. Disable automatic repeat.
- Short cases retain prefix timing/control execution and select shared event
  boundaries; finite repeats are expanded with source-line/iteration provenance.
  FSONE preserves original finite repeats and removes only song-loop markers.
- G's original r16 offsets it 12 ticks; D4 is detune. FSONE G ends3660, other
  tracks3648. No forced stop/extra silence/default PCM initialization is added.
- Whole-PDX bytes match the original; original slot1 and payload are preserved.
  Root JSON sample-relative paths resolve in the copied listening package.

Verification: three native builds, independent raw command/event/state/tone
comparison, PDX whole-file equality and mdxinfo titles/9tracks/PDX resolution pass.
Twelve reader/public tests plus three authored selector tests pass. Native
private display/cessation is unverified pending user listening. VGM capture and
vgm2mml Segment/PCM extraction comparison remain not_run. Source expectation is
MDX-requested performance, not invented source PcmAnalysis; reset/consumption/
physical stopping stay unknown. Effective LFO trajectories are not statically
certified. Architect review recommendations were addressed.

Timing correction: initial public seconds annotations used1024us per multiplier
instead of1024cycles/4MHz=256us. Corrected @t240 gives4.096ms/tick; HOLDEND
gate/end1.31072/1.572864s. Public MDX/PDX hashes are unchanged. RATES F4 naturally
exhausts before gate; F0 needs early gating. GATEEND short asset also needs gating.

Next allowed action: collect the user's private-phrase listening results, then
choose an evidence-based source/capture, IR, target/MML, tool-usage or PDX-packer
comparison. The primary objective remains vgm2mml Segment/PCM IR completeness.
Do not use faulty soundlog PCM replay as an oracle or call audible/static output
a completed roundtrip. Keep pass/lossy/unverified/fail distinct.

Prior source-stream implementation remains present on this branch, separately
from current validation-only changes: finite bank4 DAC supplies are source-derived
evidence, and stream STOP/exhaustion never creates chip STOP/reset. Strict vs
best-effort loss assessment is target-side. BOSCON06 cessation and PSG-generated
display failures remain unresolved; current public reference display success
does not establish their cause. Typed production PCM route still uses mmlx for
FM, while the validated reference builds use native MXC. No integration change
was authorized by this validation trial.

Read:
- field_notes/2026-10-10_ff4siren_private_phrases.md (latest results and scope)
- field_notes/2026-10-10_reference_expectations_public_patterns.md
- field_notes/2026-10-10_ff4siren_converter_validation.md
- field_notes/2026-10-09_reference_compiler_validation.md (original native
  FF4SIREN MML reproduces working reference MDX exactly; PDX initially copied)
- field_notes/2026-10-09_pcm_stream_support.md
- docs/project_knowledge.md, docs/pcm_pdx.md, docs/pcm_roundtrip_validation.md

Native tools: outputs/research/mxc_tools/extracted/mxc.x,
outputs/research/run68x/build/run68, external helper under
scripts/mdx_fixture_generator/target/release/. Direct mdxtools source is under
outputs/mdx-reference-tools/mdxtools. Private fixtures/tools stay ignored.
Older handoff snapshot: outputs/reference_validation_2026-10-10/prior_handoff.md.
