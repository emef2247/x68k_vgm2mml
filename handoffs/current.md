# English documentation checkpoint (2026-10-18)

User requested English canonical docs before further enhancer work. Translated
10 Japanese/mixed docs at original paths, preserving exact original bytes in
<stem>J.md. Existing psg_pcm_J.md renamed byte-identically to psg_pcmJ.md; existing
scc_fm_projectionJ.md retained. All12 English/Japanese pairs have original links.
No Japanese text remains outside J-suffixed docs. Original hashes verified;
headings, existing link targets, numeric/code identifiers and command examples
retained. Only2 shell comments translated in a fenced MGS example. Markdown
hardbreak trailing spaces replaced with backslashes in translated MGS narrative.
No converter/source/test changes or conversion/test executions; no Git mutations.
User handles commit. Translation is not an implementation/specification refresh.
Next: resume scc_vgm_enhancer Segment->VGM design when user requests; inherited
native/MML validation limits and pending regression remain as recorded below.

--- Previous checkpoint ---

# Song-loop assembly fix and MUCOM research (2026-10-18)

User authorized only the typed FM/PCM song-loop assembly fix; SW-envelope/size
optimization stays deferred. scripts/mdx_fixture_generator/src/main.rs now
resolves source L from a separately compiled prefix and checks prefix equality.
Only the pinned mmlx0.2.0 duration-first + later-finite-repeat two-byte F1
adjustment is corrected. No guard weakening, nearest-boundary guessing, source
IR modification or loop removal. Log relocation in existing .pcm/mdx_build.log.
Nested/multiple/unreachable L and cross-L context changes remain errors.

Three authored test groups plus six existing directPCM tests pass (9 total),
including valid-but-wrong legacy target, multiline inherited state, serialized
FM/P loop matching, unchanged good offsets and malformed rejection. Boundary/
timing verification only; no two-pass PCM playback certification. Release
helper rebuilt for user regression. Saved authored structural reproduction under
outputs/diagnostics/pcm_song_loop_20261018: release helper compiled the pair;
inspected commands.csv and mdx_build.log, FM A/B and PCM P F1 targets land on
note/rest command starts. No private song reruns/listening or Git
stage/commit/push. External field_notes/2026-10-18_typed_pcm_song_loop_relocation.md
records evidence. Native buffer/capacity problems are not repaired by this fix.

Next: user runs --force regression on the same inputs. MUCOM SCC->OPNA remains
research/design, keeping PSG->SSG and fm-additive preference. Findings saved in
sibling mucom88_vgm2mml/docs/scc_opna_design.md; no SCC MUCOM implementation yet.

--- Previous checkpoint ---

# Latest native regression diagnosis (2026-10-18)

User resumed after pause with full-song PSG->PCM regression and asks whether
SCC growth/missing macros causes MADRV track-buffer shortage. Read-only diagnosis
completed using existing CSVs/MDXs/commands/structures; no conversion/test rerun,
no source/test edits, no Git stage/commit/push.

Source data confirms failed native-load MDXs are dominated by SCC FM command
bytes; PCM P command track is tiny. Finite repeats already emitted. MSX @e curve
sharing differs from current MDX @v/hold trajectory encoding. Lexicalmacroization
alone is not a verified standardMDX binary compression solution (mmlx has no
runtime phrase call). Exact MADRV installed buffer settings remain unknown.

Existing failures are distinct: MDX track-start >0xfffe and typed FM song-loop
outerboundary guard. --force was a separate shellcommand, not applied; it does
not waive either nativecapacity or loop construction. See external
field_notes/2026-10-18_psg_pcm_full_song_capacity_regression.md forprivatecounts.
Next implementation needs user direction; do not conflate loopguard bug with
capacity or silently truncate/retrigger sources to fit. Prior balance can use
existing --psg-gain0.5 or --scc-gain0.25; no defaults changed in this diagnosis.

--- Previous implementation checkpoint ---

# PSG continuous PCM implementation checkpoint (2026-10-18)

First user priority is complete and saved: source-only aliases, automatic SCC
bank, canonical defaultFM+additive, README. See checkpoint below. User explicitly
asked to resumePSG->PCM afterward; that implementation is now saved in x68k.
No agent stage/commit/push/branch operations; user staging observed during work and preserved. No private regression or listening here.

Opt-in --psg-output pcm (defaultopm), requires --pcm-policy best-effort.
--psg_only can select PCM-only; --scc_only+PSGPCM rejected. Bothselectorsretain
source State/Segments/music. PSG directedtoPCM freesits oldOPMreservations.
External pinnedMIT emu2149 under.tools via scripts/setup_psg_pcm.sh; fullsetup
--with-psg-pcm supported. New authored Cwrapper renderscontinuous44100 AYtype0,
oneinstance, flags0..3; sharednoise/EG and same-valueR13 once perorderedrawwrite.
RawWAV, orderedwriteCSV, gates, core/inputhashes and assumptions inspectable.
Existing MSX note/run/structure audits retained, no pernote runtime reset.

py/psg_pcm_mdx.py targetview:20HzACcoupling, centered63tap LPF at.45profileRate,
commonmono gain, existingMSM6258 waveformpackager; originalDACwaveformunchanged.
Filtertailcropping, FIRphase/bandwidth, externalcorequality1highpitch/DAClimits,
mono/resampling/ADPCM predictorreset/loopfreeze all documented. Actualencoded
chunkbytes dedup only; no fake equal-note reuse or runtime-memoryfit guarantee.

opm_target_vgm.write_target_vgm(exact_source_times=True) usedonlythismode,
resorts original(vgmticks,targetch,writeid), preservesEOF/loop exact, negative
waitguard. Existingroundedperformance trajectorydumps retainedandlabeledasnot
serializedtiming. Source-map and canonicalOPMtraces showexactstream. PCMoverride
andFMshareone expandedtimeline; no spoofend/remappingoriginalIR. Validator includes
PCMchunkbounds and exactoriginal->finalclock error; commonPCMclockpositivegate
and nearest-even selectedrate <=1sample durationrounding retained.

Savedthenchecked:2newexacttime/filter/profilechecks,4actualAYcoreauthoredchecks,
5existingSCCsource/voicechecks passed. Public-derivedmixedMIX withSCCadditive8+
PSGPCM ultra_low exportedtypedPCM MDX/PDXsuccess. AuthoredAYLOOP (loop997/end13001,
statecontinuousreplay) PCM-only canonicalMDX/PDXsuccess. Existing9PSG/SCCtarget+
5performancechecks passed as well (25focusedchecks total). Artifacts under
outputs/diagnostics/psg_pcm_20261018/{pcm_only_loop,listen_mixed}. No private tests.

Architectreadreviewfound gateIDnamespace mix onreplay and corehash mislabeledas
sourcehash: bothfixed,4runtimechecks passed again. Explicitfiltertail lossadded;
focusedrereview found no remainingblocker. AYLOOP regenerated:sourceandOPMEOF25005,
chosenL13001, multiplier65, maxsource->finalerror207samples withinconfigured8ms;
MML310bytes/MDX117bytes/PDX5188bytes hashesmatchgenerationassessment. Source10musical
units retained. README/docs/setup saved; diffcheckclean. Readyforuserregression. No broader PCM optimization/time-window/VGMexport work.

--- Earlier checkpoint ---

# Output source selection and automatic SCC bank checkpoint (2026-10-18)

User priority: finish --psg_only/--scc_only, default fm-additive and automatic
missing-bank fitting, README and save checkpoint BEFORE resuming PSG->PCM.
Implementation saved and checked:5authored source/voice cases pass; a small public-derived mixedPSG/SCC fixture generated MML with bothselectors, retained bothsourceCSVs, SCC-only defaultautobank exportedMDX successfully; PSG-only did not fit a bank. No Git changes.
Previous user mixed-song failures were read from existing CSV: MDX track-start
0xfffe offset overflow, not proof of channel exhaustion. User split6 blocks;
all4models6/6 generated with explicit FM bank; preferred FM+additive by listening.

Both hyphen/underscore source-only aliases added, mutually exclusive, MDX PSG/SCC
only. Native PSG/SCC note/Segment evidence retained; only target selection changes.
Automatic bank saves waveformCSV and bankJSON besideMML, cacheunder.tools; fitted
only sounding SCC if selected. Explicit bank remains supported. Canonicaldefault
fm-additive; old --target opm-additive keeps historical additive compatibility.
PSG-only inputs require no fitting. Userowns private regression and listening.

After first checkpoint verified/saved, next authorized work is opt-in PSG->PCM.
Architectplan: continuous orderedAY writes once, shared noise/EG runtime across
all3ch; do not render each inferrednote independently or replay3broadcastshape
writes. Reuse waveformPCM packager, sharedclock/loop and forcecapacity/profile.
Need exact intermediate timeline bridge: existing generatedOPM stream quantizes
sourceEOF/loop. Source-exact writer opt-in or explicit PCM boundary adapter must
be validated, never spoofEOFonly. Per-note drumreuse later needs explicit phase
reset approximation. WholemixchunkPCM reducesMML but may growPDX; no memoryfit
promise. Renderer/core choice still pending. No private batches or Gitmutations.

--- Previous SCC implementation checkpoint ---

# SCC source units and optional two-lane OPM voices (2026-10-18)

Current user request: improve SCC->FM for both x68k and MUCOM, allowing an easier
first target, and reuse MSX SCC software envelopes/structure. The first target
is x68k. Changes saved to working files only; no stage/commit/push/branch changes.
User owns private regression and native listening. Root M_G2_01S.vgm is user
material and was not read or converted.

Implemented:
- py/scc_note_units.py reuses unchanged mml_envelopes.extract_notes('scc') on an
  original-sample view. Nonincreasing volume runs stay within one inferred gate;
  pitch writes (including zero-time), settings/wave changes and volume rises
  retain boundaries. Last known state can extend to explicit VGM EOF, separately
  recorded. Native SCC State/Segments/32-byte waves remain unchanged.
- Source musical rows and shared source_plan audit dumps; final output continues
  via explicit OPM performance VGM and canonical OPM music/control-run/structure
  rendering, using the shared MSX-derived exact loop solver. No per-row tied
  MML, no MGSDRV @e/bank rules imported into MDX.
- --scc-model additive (default) / additive8 / fm-additive / fm-fm, and
  --scc-voice-bank JSON. additive8 adds next four representable harmonics.
  Whole-rendered-traversal primary SCC and PSG/noise reservations protect source
  parts. Spare lanes ranked by duration*volume-squared*improvement. Lack of spare
  or lack of measured improvement falls back to one-lane additive. Fully silent
  fitted parts are removed before allocation; primary-only fits need no spare.
- Physical target channel participates in all opm_performance grouping/state.
  Both lanes share source note identities. FM software levels change carriers
  only; source wave changes select new explicit parameters. Gain has no per-wave
  normalization. Target phase and full spectral reproduction are approximate.
- Offline scripts/fit_scc_fm.py + authored C wrapper use locally installed
  external mdxtools YM2151 core. GCC/NumPy only needed for fitting. Five bounded
  candidate models, same-scale actual A+B render scoring, low/ref/high fixed
  voice transfer measurements; content/core/pitch/gain/version addressed cache.
- Bank loader checks target chip/clock, full wave hash, numeric/parameter bounds,
  carrier masks and core/wrapper/search/probe/calibration provenance shape.
  Banks portable without local matching core; provenance is not authentication.
- Nondefault models preserve .scc.voice_projection.json normally; --dump-passes
  saves source notes/structures, target lane/voice/Key trajectories. Existing
  default compact file contract retained. Export CLI forwards both options.

Saved then checked: 4 authored projection/allocation/bank cases, 2 actual-core
fitting/cache cases, 5 existing performance and 9 existing PSG/SCC target cases
passed (20 focused checks total). Only public/authored inputs used. Public SCC
volume_sweep canonical additive8 and fitted fm-additive emitted inspectable
passes and structured MML; both listening exports compiled with mmlx. Clock
16640us/tick in the additive8 listening report. Source decreasing-volume gate
has eight source runs; both target lanes have the same eight inferred attacks.
Fitted AL4 modulator TL32/24 stays fixed while carrier TL follows source volume.
Reference440.0206Hz spectral errors: baseline .3146864, FM+additive .1711754;
this is a limited ideal-staircase-reference metric, not native SCC sound proof.
Artifacts: outputs/diagnostics/scc_projection_20261018/{additive8,fitted_bank,
fm_additive,listen,listen_fm}. Authored sine/square comparison also remains under
outputs/diagnostics/scc_fm_fit_authored_20261018. No private batches or listening.
Architect read review identified silent-lane budgeting and provenance checks;
both fixed, matching checks passed; focused rereview found no remaining blocker.

Read docs/scc_fm_projection.md (Japanese workflow/scope), docs/scc_fm_fit.md
(probe/objective/dependencies) and docs/psg_scc_opm.md. External note:
field_notes/2026-10-18_scc_two_lane_fm_projection.md. Private repository has
unrelated prior changes; only the new note belongs to this SCC task.

Next allowed action: user private regression/listening with --scc-model additive8,
then optionally fitted banks. MUCOM SCC target remains the next implementation:
reuse source units/structural infrastructure, but supply OPNA6-channel budget
and YM2608-specific measurement; never label the YM2151 bank as validated OPNA.
Do not start private reruns or expand into PCM/time-window/VGM-output work.

Prior checkpoints retained: standard/low/ultra_low PCM profiles and batch600s
are already saved in both projects (docs/pcm_profiles.md); native ADPCM/track
buffers can still overflow. MUCOM dynamic force allocation of up to6 concurrent
OPM source voices was saved separately. --start/--end and optional VGM output
remain on hold. No Git mutation is authorized by this task.
