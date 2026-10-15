# Force README clarification (2026-10-16)

User regression is ongoing. Expanded README Troubleshooting with an export
--force example, omitted/approximated feature and part diagnostics, preserved
source IR, and separate best-effort/compiler limitations. Documentation only;
no conversions or tests, no stage/commit/push.
PCM quality controls and capacity/rate estimates were discussed, not implemented.
Current derived PDX waveform uses mono 15625 Hz, fixed eight-second packaging;
lower rates reduce bytes but do not alone resolve the 96-sample binding limit.
Do not equate the separate MUCOM 256 KiB payload limit with a PDX total limit.

# Shared PSG/SSG force omissions (2026-10-16)

Latest user requests unsupported hardware envelopes, noise and channel shortages
be force omissions with clear skipped output. OPNA already covered these; this
checkpoint also wires standalone PSG/SCC MDX --force through common PSG target
projection. SSG now delegates its unsupported-interval decision to that same
function rather than maintaining a separate muting policy. No noise/envelope
synthesis was added.

Registry summaries now name parts (PSG1/SSG3/FM3/PCM/shared). Existing OPNA
FM-priority capacity policy is unchanged; force lists omitted SSG parts clearly.
Standalone PSG force keeps native pass dumps and .psg_force skipped-register
CSV/JSON, with empty event IDs where source Segments lack such metadata.
Both CLI paths, batch output and TXT consume the same summary.
Four minimal authored checks passed: PSG source preservation/release-restart,
PSG CLI force/strict retry, explicit SSG3 capacity label, and existing SSG source
preservation check. One authored canonical PSG run saved and inspected native
noise/EG Segment CSV, forced registry, MML and TXT under outputs/psg_force_check.
No private regression/listening/MDX compilation.

Working-tree changes only; no stage/commit/push/branch changes. User owns
regression. Compiler fallback, new noise/EG synthesis and OPM-to-OPNA remain
outside this checkpoint. Details in docs/opna_force.md and external
field_notes/2026-10-16_shared_psg_ssg_force.md.

# Force partial-output checkpoint (2026-10-16)

Latest user authorizes --force for unsupported OPNA HW effects broadly, with
readable skipped-register listing (canonical CLI and each batch result), and PCM capacity omissions. Compiler-limit
fallback is explicitly deferred by latest user choice. Source corruption,
unresolved evidence, unsupported input routes and compiler failures still fail.

Implemented native source-preserving unknown-effect omission, CH3/CSM/FM SSG-EG
output gates with ordinary keys preserved, known-unsupported DELTA whole-part
omission, and common PDX capacity selection. Keep first-use whole samples up to96
slots/verified65535-byte scope; skip excess references as rests preserving end/L.
Normalization-omitted notes do not consume slots. All-PCM-omitted output has no
empty PDX or false artifact paths. Final PDX counts are capacity-selected.
See docs/opna_force.md and external
field_notes/2026-10-16_force_partial_hw_and_pcm_capacity.md.

Saved before verification. Six force +six PCM-HW omission checks passed.
Capacity's seven initial authored checks and one added normalization-slot check
passed. One authored canonical MML/CSV/JSON/TXT run inspected under
outputs/opna_force_check. No private regression, listening or MDX compilation.
Focused review fixes (null PDX, actual sample count, normalization capacity) are
applied. Existing unrelated earlier worktree changes are preserved.

No staging, commit, push or branch changes. User handles private regression.
Next allowed action: user retries SNATCH07 with --force and existing PCM/compiler
flags. Do not resume compiler fallback, OPM-to-OPNA or preview-VGM automatically.

# Scoped OPNA force checkpoint (2026-10-15)

User approved --force before further bidirectional FM policy work. Added scoped
OPNA-to-MDX SSG noise/hardware-envelope interval omission, CLI/export forwarding,
unchanged native SSG dump and per-interval CSV/JSON/TXT loss reporting.
Only the target view is muted; ordinary tone intervals, timing and PCM IR remain.
Unknown FM/CH3/CSM/streams, PCM capacity and compiler failures still block.
See docs/opna_force.md. Existing earlier worktree changes are retained.

Working-tree edits only; no staging, commit, push or branch change.
User owns private regression/listening. Do not run private conversions or a broad
regression. Three new authored checks passed (including unchanged source evidence,
silent target intervals with release/restart edges, dump serialization, and CSM
still rejected; forced success followed by strict rejection clears stale
omission CSV/JSON). One authored canonical CLI generated MML, native SSG CSV,
omission CSV/JSON, target performance CSV and TXT under outputs/opna_force_check.
Inspected two omissions (noise and hardware envelope). No private conversion or
MDX compilation; timeout180 is unchanged. Focused review identified stale omission
reports on rejected retries; converter/frontend/export cleanup was added and the
new retry check passed. No other review issues were identified.
Next allowed action: user retries gh002 with --force and existing PCM options.
Do not resume OPM-to-OPNA or the paused preview-VGM feature implicitly.

# PCM interoperability checkpoint (2026-10-15)

Shared musical planner, integer-domain allocator and native ADPCM-B epoch
interpretation were backported from mucom88 without changing MDX clock policy.
Continuous DELTA level/pan/rate/pause now feed a nominal waveform and shared
MSM6258 target engine; original independent DELTA and Sega adapters remain.
See docs/pcm_interoperability.md. OPM-to-OPNA has been considered but is not
implemented; proposed first scope is six used FM channels, explicit pitch and
operator maps, with DT2/noise/LFO gaps reported rather than silently dropped.

Working-tree changes only. User owns private regression/listening. Focused
public checks and one authored DELTA canonical conversion were run; no private
conversion, broad suite, staging, commit or push. Default timeout180 remains.
Next action: user regression; address reported defects only when requested.
Do not resume the paused VGM-output feature or integrate OPM projection implicitly.

# Current checkpoint: SegaPCM to PDX (2026-10-13)

User finite-output retry resolves two preceding song-loop validation failures,
but reports PCM inaudible in one generated song while FM plays. Read-only
inspection finds nonzero native/decoded PCM, complete PDX samples,16-track/E8
MDX with active P notes and matching PDX name. Copied MDX/PDX hashes also equal
the generated pair. Runtime PCM output versus relative loudness remains
unresolved; do not attribute it to missing extension or declare playback fixed.
Asked user to test the existing authored SEGAONE pair; await that result.
No private reconversion/recompile or changes to currently running exports.
Details: field_notes/2026-10-13_segapcm_pcm_inaudible_triage.md.

Latest user full-PCM regression: four failures reach typed FM/PCM song-loop
validation (outer command-boundary resolution or shared loop start/end mismatch),
despite L being emitted on every FM track. Nine others hit the180-second outer
conversion budget. Saved artifacts distinguish unfinished source runtime,
initial PCM bridge and final shared-clock re-encoding. Python per-frame mixing
and16-candidate per-sample ADPCM encoding are likely costs; no runtime profile
or private rerun was taken. This is diagnosis only; exact loop discrepancy and
performance fixes remain pending. Default timeout unchanged. Details external:
field_notes/2026-10-13_segapcm_pdx_regression_triage.md.

The user authorized SegaPCM PDX implementation after the FM-only regression.
Default mixed OPM/SegaPCM now reconstructs native playback, then projects mono
F4/15625Hz MSM6258 chunks to the existing single-P/16-track MDX/PDX path.
Use --pcm-policy best-effort; strict blocks the explicit transcoding losses.
--fm-only retains the preceding comparison route without rendering SegaPCM.

New modules: py/segapcm_playback.py and py/segapcm_pcm.py. Original observed
State/control Segments remain intact. Native stereo waveform, inferred runtime
gates/events and target mapping CSV/JSON are emitted separately. Active voices
are mixed, chunks split at8seconds/L/EOF, short packaging tails are protected
from whole-note omission, and final sample counts follow the shared MDX clock.
ROM coverage, stereo folding, clipping, resampling, independent decoder resets,
requantization and fixed recorded-loop phase are explicit diagnostics.

Working-tree changes only; no stage/commit/push/branch switch. User owns private
regression and listening. No private inputs were converted or compiled.
14 focused authored SegaPCM checks passed. Three tiny authored public fixtures
generated MDX/PDX/MML/TXT successfully under outputs/segapcm_pdx_check. Inspected
native gate CSVs, target sample mappings, loop L and exact PDX payload equality.
One-shot source stop is1.048576seconds; all three selected16.64ms/tick and
aligned target duration errors were0F4 samples. Native playback remains untested.
Focused review found a stale fractional address after natural stop; it now
clears before restart, matching the referenced playback model. Added and passed
an authored natural-stop/restart check. No further review blockers identified.

Next allowed action: user regression/listening with full PCM output; address
reported defects. Do not optimize compiler capacity, modify default timeout180,
or run private regression without a new request. Existing FM target offset
limits remain unchanged. Field notes remain external and may name local_only.

# Previous checkpoint: SegaPCM source and OPM-only MDX (2026-10-13)

User requests native OPM+SegaPCM source support, then an explicit FM-only MDX
checkpoint before starting SegaPCM->PDX. Source collector reads C0/type80 in
the shared traversal and saves immutable raw/State/control Segment/ROM history
with exact timing/loop provenance. Runtime address/natural stop/audio gates
are unmodeled. Default mixed CLI produces source_analyzed only; --fm-only
retains native evidence and uses existing OPM target projection/compilation,
reporting SegaPCM omission in JSON/TXT. No SegaPCM PDX work has started.

Implementation is in the working tree only. No commit, staging, push or branch
change is authorized. User owns private regression/listening. Minimal authored
checks passed (5 new source/CLI/export tests and26 existing exporter tests).
One authored mixed input generated MML/MDX/TXT via native MXC/run68 without
PDX. Equivalent OPM-only and mixed FM-only inputs produced identical MML with
declared loops. Native CSV, sparse ROM payload and TXT omission were inspected
under ignored outputs/segapcm_source_check. No private source conversion or
native playback was run.
New notes are external: ../my-external-intelligence/x68k_vgm2mml/field_notes/.

Exporter interruption recovery: an unregistered _source_inputs file may be
adopted without overwrite only when identical to the current input. Registered
modified staging and unowned differing staging/publications remain protected.

User FM-only regressions expose MXC duration/capacity failures and runtime
buffer/display issues. Target duration rendering now splits over256-tick
rests as well as tied notes, preserving source timing and safe compaction.
MXC adaptation also splits dotted long rests in older scores. All38 focused
duration/compaction/compiler checks passed. Two authored native MXC builds
(newly split score and older dotted rests) each preserved960 encoded ticks.
--timeout is wall-clock stage budget, not song duration/timer.
No private reconversion or SegaPCM PDX work is authorized at this checkpoint.
External private field notes may name local_only fixtures per the user's
2026-10-13 instruction. Public documents still omit private identifiers.
Detailed regression findings: external field_notes/2026-10-13_segapcm_fm_regression.md;
an ignored human-readable copy is outputs/opm_segapcm/fm_regression_summary_2026-10-13.txt.
Latest user mmlx export improves the mixed FM-only corpus. Remaining compiler
errors explicitly report track-offset and loop-position representation limits;
the conversion timeout remains separate. Existing results/logs were inspected
read-only, without private reruns. README TROUBLE SHOOTING now recommends
--compiler mmlx for compilation_failed, without documenting timeout values.
Subsequent user retry with a600-second budget completed the previously timed-out
conversion and exposed another song-loop offset limit. Finite output using
--no-song-loop is the next user regression; its success is not yet verified.
Latest finite-output user regression resolves two previous failures. One source
now completes conversion within the existing budget but exceeds a track-start
offset limit; extending timeout cannot fix that diagnostic. README TROUBLE
SHOOTING includes --no-song-loop and its finite-output semantics. Default
timeout remains180 pending the user's follow-up decision. No private reruns.
User now explicitly retains default timeout180. Read-only investigation of the
remaining finite-output failure confirms cumulative encoded register data before
the failing track already exceeds its16-bit start-offset range. This is target
capacity, not timeout/PCM projection or a malformed loop. Details are external;
optimizing-compiler integration remains deferred. Stop for user next action.

User command:
python scripts/export_mdx.py <input-directory> --outdir outputs/listen/segapcm_fm --fm-only --no-vgm

Next allowed action: stop and report this checkpoint.
Await user MDX/FM regression before implementing SegaPCM->PDX or other targets.

# Previous checkpoint: OPNA FM/SSG/PCM to MDX/PDX (2026-10-12)

Branch: codex/opna_to_opm. User confirmed the preceding FM/PCM MDX/PDX plays,
then requested SSG via the existing PSG FM method. The user accepts the same
noise/hardware-envelope restrictions and will generate/listen to songs.
Stop after repository reflection. No commit/push, branch switch, private song
build, playback or PCM MUCOM roundtrip is requested.

Native FM -> vgm-conv OPN/OPM mapping and ADPCM-B -> MSM6258 -> existing PDX
remain connected. New opna_ssg reads native OPNA raw CSV into immutable
PSG-compatible source Segments, with raw snapshots, exact sample boundaries,
original/expanded event IDs, envelope strobes and prescaler clock evidence.
New opna_ssg_opm reuses the existing PSG FM AL4/FB7/TL/performance model.

Whole-song any-FM-key use reserves the existing OPM0,1,2,4,5,6 mapping for used
FM parts, preserving release tails and output gating. Used SSG parts fill the
lowest vacant channels in source order. Six FM plus three SSG drops SSG2 with
an allocation reason. Register initialization alone does not reserve FM; its
unallocated target writes are filtered to avoid clobbering SSG. Every native
SSG part remains in source IR. Only allocated SSG parts undergo target mode
validation. Allocation CSV/JSON is always retained; --dump-passes keeps native
SSG and the reused PSG baseline/performance before final remapping.

FM and SSG writes merge by exact samples/event IDs/within-event ordinal before
existing OPM/PCM clock projection. Loops suppress synthetic SSG EOF release.
Prescaler changes use per-Segment master/4, master/2, master AY-compatible clock
and do not restart held gates. Source interpretation and target key inference
remain distinct. See docs/opna_ssg.md and README.md.

Checks:53 focused OPNA source/target/PCM tests,20 existing PSG FM/performance
checks and9 new SSG-allocation/merge/renderer tests passed. The9 include actual
WSL helper MDX/PDX generation on an authored FM+SSG+PCM input and independent
PDX target-byte equality. One previously played local source was parsed/dumped
only: five used FM plus three SSG fit eight OPM channels, without exclusions.
No song target binaries or native playback were run for the SSG change.
Source/mapping pass evidence stays in ignored local outputs. Read-only design
and final reviews found no blockers.

All46 local main MUC sources already have loops removed and MUCOMVGM VGM
created; org backups/MUB are preserved. Fixture scripts/manifests and the
FM-only diagnostic runner remain available. PCM MUCOM roundtrip is deferred.
Own chip/module/fixture names use MSM6258; external API names retain spelling.
Local copyrighted songs, external tools and outputs remain outside Git.

User command (WSL, existing helper):
python scripts/export_mdx.py input.vgm --outdir outputs/listen/opna --no-vgm --pcm-policy best-effort

Next allowed action: stop and await user build/listening results. Do not re-add
OPN/OPN2, run private song conversions or resume separate MUCOM work automatically.

# Previous checkpoint: OPNA X68000 FM projection and PCM IR (2026-10-12)

Branch: codex/mucom88. User requests repository registration without commit;
conversion/listening verification belongs to the user for this checkpoint.
Implement automatic OPNA FM -> native Segments -> OPM4MHz projected VGM ->
existing OPM MDX MML. Preserve original sample timing until downstream MDX
projection, event-aware replayed loops and RL output gating without key restart.
README and ISC reference notices now record vgm-conv register mapping.
Native ADPCM-B memory/control/decoder-epoch IR and explicit MSM6258 transcoded
target PCM IR are also generated. Use existing F0..F4 rates. Do not claim PDX,
PCM P-track integration or acoustic equivalence; those remain next-stage work.
See docs/opna_adpcm.md and field_notes/2026-10-12_opna_x68k_projection.md.
Only syntax/import and source inventory checks were performed; new focused
tests are supplied but conversion/playback/full-suite tests were not run.
Next allowed action: user validates FM MML and PCM IR, then address findings
and bridge target PCM IR to existing PDX/MDX PCM binding. MUCOM FM/SSG
validation and future mucom88_vgm2mml extraction remain separate work.
Do not commit/push, re-add OPN/OPN2, or stage external song archives or the
unrelated untracked AGENTS.mucom.md.

# Previous checkpoint: OPNA diagnostic FM roundtrip (2026-10-12)

Branch: codex/mucom88. User moved29 public OPNA patterns here and requests a
repository commit once VGM->Segment->MUCOM MML->VGM is runnable. That supersedes
the previous no-stage/commit constraint for this work; no push is requested.
Implemented typed Segment target projection, exact MUCOMVGM virtual-sample
timing, external runner and native state/control/edge/end comparisons.16cases
with active FM pass;13SSG-only inputs report no_active_fm. Known non-FM evidence
is retained but not compared. Unknown writes and unexpanded streams are rejected.
See docs/opna_mucom_roundtrip.md and its field note for commands and evidence.
MUCOM MML is a diagnostic target, not X68000 user output; README keeps WING's
acknowledgment and MIT notice without MUCOM-output usage instructions.
Next branches: consider extracting mucom88_vgm2mml around native analysis and
MUCOM-specific target modules; independently add OPNA->OPM(4MHz) using vgm-conv
and MSM6258 PCM IR, then integrate automatic chip routing/MDX MML output.
The next MUCOM milestone must include SSG as PSG-equivalent source behavior,
with inspectable Segments and FM/SSG MML roundtrip coverage. The user accepts
FM-only scope for this checkpoint; the13 SSG-only patterns remain future coverage.
Final focused run:29 tests pass, including external compiler and rejection cases.
Public/synthetic regression:654 tests,9 failures/11 errors/3 skips; the20 failure
identities match the previously reproduced HEAD baseline exactly.
Do not claim that X68000 import/mapping or PCM Segments are already implemented.
Do not re-add OPN/OPN2 or publish derived external MUCOM song material.
Keep private fixture checks outside this work. Third-party MUCOM archives under
tests/fixtures/public/opna/mucom88 remain local and outside the migration commit.

# Previous checkpoint: OPNA native source analysis (2026-10-12)

User scope is OPNA/YM2608 only: OPN and OPN2 excluded. Implemented reader raw
capture and standalone py/opna.py immutable FM State/Segment analysis, with
raw/state/segment/unmodeled/auxiliary CSVs and current-output JSON manifest.
Legacy eight-path reader return and target conversion routing remain unchanged.
PCM playback Segments and MUCOM MML rendering remain unfinished later stages.
Requested mucomvgm.exe found in wingghost/MUCOMVGM, separate from its Studio GUI
and official MUCOM88Windows; local portable0.0.5 installed under ignored.tools.
Self-authored MUC->VGM->Segment check passed, with correct two22050sample gates.
15 focused OPNA tests passed;29public fixtures retained in ignored outputs.
Broad public/synthetic 643-test run has 20 failures, all reproduced on HEAD;
baseline attribution recorded
in field_notes/2026-10-12_opna_source_segments.md. Do not claim fullsuite pass.
See docs/opna_segments.md for APIs, limits and actual tool invocation.
Next allowed source work: assess OPNA PCM evidence/Segment design or implement
Segment-to-MUCOM88 MML and FM roundtrip when requested. Do not re-addOPN/OPN2,
route OPNA through OPM merely for IR, or discard unsupported source evidence.
No Git stage, commit, push, branch switch or private fixture checks authorized.

# Previous checkpoint: declared VGM song loops (2026-10-12)

User approved reader-level loop expansion, reusing existing Segment structure.
Implemented default two traversals for native OPM and musical PSG/SCC MDX.
First traversal warms up state; second traversal has MML L and repeats.
--no-song-loop exports a finite source pass; --no-loops remains finite compression.
Raw/state/Segment provenance preserves original addresses/times and occurrences.
PCM shares replay cursor; independently playable notes loop, decoder continuation
across repeat boundaries is explicitly rejected. Legacy/held-register compatibility
requires finite opt-out for now; MGSDRV unchanged.
Public/synthetic validation only; native listening is next, performed by user.
No Git stage, commit, push, branch switch or private fixture checks authorized.
Keep private fixture names and paths out of field_notes.
See docs/vgm_loop.md and field_notes/2026-10-12_declared_song_loop_replay.md.

# Field-note privacy cleanup (2026-10-12)

Private fixture names, identifying paths and private binary hashes have been
removed from field_notes. Technical findings remain under anonymous case labels;
eight note filenames were generalized and their documentation links updated.
The label/placeholder convention is in field_notes/000_how_to_write_notes.md.
This was a documentation-only change; no conversion or playback was rerun.
Continue the previously agreed loop work only when requested. Keep private
identifiers in ignored local evidence and do not stage, commit or push changes
without an explicit user request.

Project: x68k_vgm2mml
Branch: main
Checkpoint: 2026-10-11

LATEST MDX LOOP LINE FORMATTING:
User requests a new physical line before each '[' and after ']'+repeat count.
Shared mdx_format.wrap_track now formats structured and legacy native renderers,
including their PCM additional tracks. Existing110-column word wrapping remains;
individual commands are never split. Source IR, timing and repeat structure stay
unchanged. Files were edited BEFORE verification, as the user explicitly requires.
22 existing renderer tests pass; public nested_phrase_loops before/after MXC
compilation yields byte-identical MDX. Evidence:outputs/mdx_loop_line_format_2026-10-11.
No Git mutation; no NOTE integration or VGM song-loop implementation.

LATEST POWERE COMPILER DIAGNOSIS:
Additional WBIIIA02 investigation: same native SIGSEGV/false unclosed repeat
on F, but mmlx explicitly rejects track6 start offset above0xfffe. F alone
compiles to50327-byte MDX and C to14384 bytes; full target exceeds offset
capacity. This is NOT fixed by switching compiler. Source/target4MHz,10240us
clock,no PCM. User defers size-dependent issues. Existing generated MML only
was compiled; no source reconversion or algorithm changes. See same field note.
User asks to investigate compilation_failed before implementing song loops.
Existing conversion succeeded (4MHz,7424us @t227,no PCM); native MXC/run68
crashes with SIGSEGV. Unbuffered stdout reveals false unclosed-loop diagnostic.
Balanced H alone and A-G together compile. Public no-loop raw-write MML
reproduces the size-dependent failure:43560-byte MDX succeeds,~45000 bytes
fails; larger whitespace-only input succeeds. Exact internal defect unlocated;
do not label this a format limit or a source-loop/pitch error.
Existing generated POWERE MML compiles with mmlx to54667 bytes and passes
command inspection; native listening is untested. Artifact in ignored
outputs/powere_compiler_check_2026-10-11. User workaround:export --compiler mmlx
--no-vgm to a separate directory. No private VGM reconversion, compiler fallback,
song-loop implementation or Git mutation. See POWERE field note.

LATEST USER COMMIT CHECKPOINT / SONG LOOP NEXT:
User confirms all15 GENPEI tracks play and animate in MMDSP. Residuals:
GENPEI10 animation briefly stalls near intro then recovers; GENPEI07 abruptly
ends mid-song and keeps sounding. Generated clocks:07=15872us,10=7424us,
15=11520us (@t211);15's former256us freeze no longer reported.
GENPEI07 source has valid loop entry937613/end2271552samples and all8 channels
still keyed at stream end. Current code observes loops but does not emit MML
song-loop markers. User chose DEFAULT ON for the future declared-song-loop
transfer. This feature is NOT implemented in the current commit candidate.
Next: review major loop plan, preserve command-position/same-sample ordering,
held gates/state carry/redundant first-pass writes and FM/PCM shared boundaries;
use minimal public multi-iteration tests. Song-loop opt-out must be distinct
from --no-loops finite-repeat compression. Do not fake source EOF Key-Off.
User asks to stop at this checkpoint to commit themselves. File edits only;
no Git mutations. Branch suggestion: codex/opm-clock-projection.
Commit suggestion: Support alternate OPM clocks and bounded MDX timing.
See field_notes/2026-10-11_opm_clock_projection.md for complete evidence.

LATEST GENPEI FOLLOW-UP / TARGET POLICY:
User now reports15/15 GENPEI exports succeed after the fixes, using default
clamp/8ms and --no-vgm --pcm-policy best-effort. This is file-generation evidence;
latest native playback/display and GENPEI15 period are not yet reported.
Earlier user results: GENPEI02/04/14 play and animate; GENPEI15 froze at256us/tick.
Existing diagnostics:11 failures are KC/KF-only range underflow at3,579,580Hz;
unretimed EG/LFO/noise are not the rejection cause. User explicitly accepts
nearest pitch at range endpoints. Native pitch policy now defaults to clamp
with source-linked loss counts/cents error; --opm-pitch-policy error preserves
strict rejection. Retuning already changes note/octave, not only KF.
Normalization now tries bounded ordered tick allocation when nearest rounding
collapses protected positive intervals, including terminal unclosed gates.
Source State/Segment/PCM IR remains unchanged. FM/PCM share the allocated map.
40 focused public/synthetic cases pass in the final run;2 native MXC public exports
succeed. Terminal3/7/11sample public example uses12544us @t207, maxmove327<=352,
no gate omission. Agent did not regenerate private GENPEI; user completed that
batch. Outputs: outputs/opm_clock_followup_2026-10-11 (public) and user results
outputs/listen/opm/vgmrips.net/GENPEI/results.csv.
Native listening result and next allowed action are superseded by the checkpoint
above. Distinguish generated clock selection from measured interrupt load.
File edits only; no stage/commit/push/branch action. Preserve user's README.x68k.md.

INITIAL ALTERNATE OPM CLOCK TARGET PROJECTION (policy superseded above):
Added nominal KC/KF retuning from a single YM2151 source clock to 4MHz at
Segment->MDX projection. All notation routes and PCM FM output share target
controls/state views; source State/Segment is immutable. Added inspectable
pitch CSV, source/control provenance and TXT summary. Unknown KC/KF uses
reported target-only reset-zero assumptions; pre-first-Key-On out-of-range
setup may defer, but played/released out-of-range pitch rejects, never clamps.
28 focused public/synthetic tests pass. Native MXC compile/replay for the
3,579,580Hz synthetic case passes structured/legacy/registers comparison.
Public PCM rates at 4MHz and 3,579,580Hz produced identical 896-byte PDX.
Public from_fm/3ch_test default export succeeds, including the readable report.
GENPEI local_only was not converted; user can rerun their original export
command. DT1/EG/LFO/noise are not retimed; MMDSP listening remains user's step.
File edits only; no stage/commit/push/branch action. See clock projection doc
and field_notes/2026-10-11_opm_clock_projection.md for evidence and limits.

LATEST USER WORKFLOW / RESTORE CHECKPOINT:
User merged the release-preparation PR, fast-forwarded main to 0547259 and
applied the attribution stash successfully. The four attribution files are
present without conflicts. Future repository updates mean file edits only;
commit, push, PR creation, staging and branch changes require explicit user
instructions. Leave existing staged state untouched.

LATEST README COPYRIGHT UPDATE:
README now displays Copyright (c) 2026 emef2247 with a link to the MIT LICENSE.
Documentation-only edit; no stage, commit or push. No unfinished work for this request.

LATEST ACKNOWLEDGED TOOL LICENSE CHECK:
Checked installed mmlx0.2.0 MIT (Copyright2026 h1romas4), soundlog0.15.0 MIT
(Copyright2025 h1romas4), pinned run68x GPL2-or-later, and MXC1.01 freeware
redistribution statement and (c)1989 MFS soft, milk banner. Optional mdxtools'
LICENSE is GPL3. README separates MXC/runner and records tool license terms;
THIRD_PARTY_NOTICES.md retains exact direct-crate MIT texts and use/distribution
boundaries. No executable change or conversion test. Full Rust binary transitive
notice bundling remains required before binary redistribution, not completed
by this direct-tool check. File edits only; no stage/commit/push/branch changes.

LATEST ATTRIBUTION UPDATE:
User asks about credit/license for the vgm-conv PSG FM reference. README credits
the AY->OPM parameters and volume/TL mapping; THIRD_PARTY_NOTICES.md retains the
exact upstream ISC notice and Copyright (c) 2023 Mitsutaka Okazaki and Contributors
at reference revision 780a20ed505e23eb21aa9c6ce3f349029718b5a0. Python module links
that notice. No algorithm change, commit or push for this documentation update.

LATEST RELEASE PREPARATION / USER NATIVE RESULT:
User explicitly requests no commit for these changes: leave working-tree edits
for their branch -> PR -> main workflow. Do not commit or push.
User confirms default PSG NEMESIS export14/14 succeeded and MMDSP animation
now works. Current GRA1_01 report:16128us @t193, max350sample boundary movement.
No agent local_only conversion. README now introduces --normalization-ms and
explains TXT reports in Japanese. scripts/setup_tools.sh installs persistent
MXC/run68/Rust helper; --with-mdxtools adds independent inspection tools.
See docs/mdx_compiler_setup.md and the release_setup_and_native_listening note.

LATEST DEPENDENCY RECOVERY:
User deleted outputs after a successful NEMESIS export. Subsequent compilation
failed with Missing --mxc tool because tools had lived in outputs/research.
Restored the same hash-verified MXC and pinned run68x under ignored .tools/;
default lookup now prefers persistent paths after explicit options and PATH.
Legacy locations remain a fallback. See docs/mdx_compiler_setup.md and
field_notes/2026-10-11_compiler_dependency_recovery.md. All18 compiler tests
and one public block_boundary export with default replay passed. No local_only
conversion was run. User can rerun their original NEMESIS command unchanged.

LATEST CLOCK OPTION/LISTENING UPDATE (supersedes next-action statements below):
User confirms from_fm controls responsive/counters moving, volume animation
still absent; BOSCON animates but sluggish. User local export9/12 succeeded.
--normalization-ms now configures original whole-gate omission and absolute
boundary movement across OPM/PSG/SCC/PCM; default8, OFF disables policy.
Saved old block_boundary256us reports predate short-rest coalescing. Fresh
public block_boundary8/16ms both10496us; PCM16ms32512us. Independent encoded
MDX periods match reports;22focused public checks pass. TXT is plain sections,
paragraphs and indentation. User may explore parameter values; no local_only
run or full regression authorized for agent. See:
field_notes/2026-10-11_clock_option_and_listening.md.

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
Implementation committed in 68b8411. After that checkpoint, 13 minimal
public/synthetic checks passed and Rust release was rebuilt. Public chords_mix
and opm_pcm_rates export successfully; independent MDX parsing confirms complete
9/16-track structures and Timer B 191 = 16.640 ms for both. PCM allocated sample
bytes match PDX. Native GUI/playback is untested; FM representative still uses
raw Key requests, so animation improvement must not be claimed. User can take
over public batches or local_only listening using the recorded commands.

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
roundtrip remain. Public inputfixtures movedto tests/fixtures/public/opm_msm6258.
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
field_notes/2026-10-10_pcm_reference_extended_structure.md.

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
- field_notes/2026-10-10_private_pcm_reference_phrases.md (latest results and scope)
- field_notes/2026-10-10_reference_expectations_public_patterns.md
- field_notes/2026-10-10_pcm_reference_converter_validation.md
- field_notes/2026-10-09_reference_compiler_validation.md (original native
  FF4SIREN MML reproduces working reference MDX exactly; PDX initially copied)
- field_notes/2026-10-09_pcm_stream_support.md
- docs/project_knowledge.md, docs/pcm_pdx.md, docs/pcm_roundtrip_validation.md

Native tools: outputs/research/mxc_tools/extracted/mxc.x,
outputs/research/run68x/build/run68, external helper under
scripts/mdx_fixture_generator/target/release/. Direct mdxtools source is under
outputs/mdx-reference-tools/mdxtools. Private fixtures/tools stay ignored.
Older handoff snapshot: outputs/reference_validation_2026-10-10/prior_handoff.md.
