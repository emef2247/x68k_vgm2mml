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
