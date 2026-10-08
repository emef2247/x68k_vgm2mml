Project: x68k_vgm2mml

Latest user observation (2026-10-09): MMDSP playback of generated long_hold_stop
and reset_pan_hold reportedly does not stop and keeps sounding noise. Cause is
unconfirmed; do not claim the pair is runtime validated. Read
field_notes/2026-10-09_mmdsp_pcm_stop_observation.md first. User confirmed XM6
TypeG3.32, MXDRV30.x with resident PCM8, MMDSP driver display MXDRV, and audio
remaining after the display indicates ended/stopped. AUTO/REPEAT is still
being checked. Actual resident versions/modes are not pinned: backup binaries
contain MXDRV2.06+16 Rel.3 / PCM8Av0.60 banners, but may not be the loaded files.
Original pairs have F100 on all9tracks, valid PDX refs and ~0.13s nominal duration.
Native operandFF/byte-counter0 is valid256ticks. Existing native-port sequencer
terminates for all3pairs, but its PCM stubs make it unsuitable as IOCS/VGM oracle.
Bounded instrumentation confirms END intents and cleared channel masks: global
end at ticks522/522/11 for long_hold_stop/reset_pan_hold/opm_pcm_rates. Actual
IOCS/DMA/audio stopping remains unknown. Logs: outputs/research/mdx2vgm_stop_probe/.
Diagnostic base/split255/tempo224/both pairs plus ZIP are in ignored
outputs/pcm_stop_2026-10-09/. Timer224 probes stretch instructions32x (~4.27s),
not faithful conversion fixes. Canonical production code has not been changed.
Next action: obtain timer224 probe stop result and AUTO/REPEAT setting, pin the
actual resident profile, distinguish completed sequencing from ongoing PCM
audio, then implement an evidenced fix. Do not infer current MADRV from a
backup startup script; user confirmed current MMDSP display is MXDRV.

Current checkpoint (2026-10-09): PCM policy/report and typed direct MDX+PDX
generation are implemented and verified; related files are staged, uncommitted.
Independent runtime R, source stream expansion and A/B/C comparator remain
unimplemented. This checkpoint is not a PCM roundtrip success report.

User objective: VGM -> PCM IR -> MDX+PDX -> VGM with semantic OPM/PCM comparison.
PCM MML is optional. Preserve existing OPM musical generation and inspectable
raw/state/playback/sample evidence. Future Z_MUSIC uses its own target/profile.

Additional agreed policy: do not reject every target limitation. Strict
disallows known loss; explicit best-effort may emit usable MDX+PDX with a
defined fallback and source-linked loss diagnostics. Keep pass/known-lossy/
unverified/fail separate from artifact generated/blocked/error. Unknown IOCS
is not known target loss. Modes/report are implemented. Common IR must
retain original semantics. Strict is not a claim of runtime certification.

Read first:
- docs/pcm_roundtrip_validation.md (independent R, C0/C1, A/B/B_ref, acceptance)
- field_notes/2026-10-09_pcm_mxdrv_roundtrip_review.md (pinned source evidence)
- field_notes/2026-10-09_pcm_target_projection.md (current implementation/checks)
- docs/pcm_pdx.md (current implemented scope and CLI)
- docs/project_knowledge.md
- field_notes/2026-10-08_pcm_pdx_implementation.md (historical code/checks)

Implemented previously:
- OKIM6258 header0x90/0x94, direct B7 evidence, immutable encoded samples and
  playback records. Consumption is unknown; nominal_nibbles is calculated.
- Initial source scope: single chip,4-bit low-first/10-bit, regular delivery,
  known starts, exact F0..F4. Stream/bank raw evidence is preserved and rejected.
- PCM-only/OPM+PCM MML+PDX, bank0/96 binding, shared clock, exact PDX packing.
- Compile-only helper validates PDX references and typed standard9track MDX.
- PCM VGM replay unavailable, MDX+PDX retained, stale VGM removed; FM available.
- Previous relevant Python123/Rust8 passed; public native OPM9/9 passed.
  Those checks do not certify standard PCM runtime/pan/reset/audio.

Implemented in this checkpoint:
- --pcm-policy strict (default) / best-effort; scope/status/source-linked
  JSON+CSV assessment even on blocked/helper failures. Artifacts, projection
  and runtime validation states are separate; runtime stays unverified/not_run.
- Strict blocks held-pan loss; best-effort retains onset pan, records affected
  intervals including mute, adds no artificial attacks and sets next onset pan.
- Native sample length<=65535; larger lengths have known constraint/no fallback,
  blocked in both modes. Unknown source vs invalid source stays distinct.
- A single typed PCM target command list drives readable MML and target.tsv.
  Canonical PCM duration chunks currently have no repeat compression.
- --compile-pcm FM_ONLY.mml PLAN.tsv OUTPUT.mdx: existing FM compiler, preserved
  FM tracks/tones/title/finite repeats, direct typed PCM via existing MdxBuilder,
  standard9tracks, shared tempo/end and PDX references checked by reparse.
- vgm2mml emits readable MML+MDX+PDX in one invocation for eligible PCM.
  Export uses --from-mdx, preserves that pair and reports replay guard separately.
- Stale outputs/target manifests invalidated; input alias protection and partial
  per-artifact failure reporting. Public long_hold_stop fixture added.
- Current focused Python PCM26/export13/OPM95 passed; Rust12 passed and release
  rebuilt. Native public OPM9/9 roundtrip passed. Actual public PCM3 pairs
  generated (boundary errors0/0/1 samples), batch guarded3/3 with no VGM.
  Architect completion review found no major correctness issue.
  Additional full-suite run was stopped during large private MGSDRV fixture
  conversion; it did not complete and is not reported as an all-suite pass.

New evidence and corrections:
- soundlog0.15 non-Note clears raw cursor; held same-block Note returns without
  restoring it. This is MDX replay behavior, not an MML notation issue.
- Native MXDRV2.06+17 Rel.X5-S disassembly was located/pinned (x68kd11s commit
  19a79218a4fbe0651371bd2f2d909a92897c8e52); source/provenance saved under
  outputs/research/x68kd11s/. No native binary/ROM/song was downloaded.
- In that PCM1 path, FC pan and ED rate latch until new ADPCMOUT. F7 suppresses
  gate keyoff; active PCM note requests return before sample lookup. New note
  requests MOD0 then OUT; gate keyoff conditionally MOD1 then MOD0.
- Former tie+mid-pan output was not faithful for that profile; strict/best-effort
  eligibility correction is implemented. Physical decoder reset still needs IOCS.
- Native PCM1 reads only the length low word; container/packer24-bit capacity
  is not playback proof. Target length eligibility now uses65535 native limit.
- NanoDrive8 is a separate firmware profile, with logical cursor stop but
  commented physical STOP/PLAY calls. Useful hints, not standard oracle.
- Leonardo mdx2vgm unchanged was built/run on two public pairs: payload exact,
  rate7813/pan0 fixed, STOP absent/stubs. Correct headerclock0x90=8MHz;0x98 is
  OKIM6295. Its output must not generate PCM expected values.
- XAPNEL/IOCS replacements demonstrate runtime-profile differences. Pin MXDRV,
  machine/ROM IOCS and PCM8/XAPNEL absence for the standard baseline.

Next allowed actions:
1. Fix/reference a native MXDRV+ROM IOCS execution profile R and establish
   time-stamped chip/PPI writes plus DMA transfer observation. IOCS calls alone
   cannot certify decoder consumption/reset. Determine available emulator
   tracing before claiming a runnable workflow.
2. Use small original MDX+PDX fixtures to validate F7/gate/rest/EOF, repeated
   same/different sample, pan/rate latching, delay/tempo/sync and sample lengths.
   Projection/length reports are implemented; validate their chosen fallback
   against effective native playback, including affected mute/audio intervals.
3. Add independent direct MDX/PDX analysis C0 and evidence-backed C1; preserve
   command intent separately from effective playback. C and R code reuse is
   not a second independent oracle. Never reconstruct hidden F7/q from VGM.
4. Add source stream expansion/consumption model against independent evidence.
   Direct PCM typed MDX output is implemented; retain its common binding and
   ordinary OPM path. Optimize target repeats only after native behavior checks.
5. From the first fixture, obtain original->R->A and generated->R->B_ref.
   Compare C1/A, A/B_ref and B_ref/B for player under test P; only then repair
   P to confirmed standard rules. A/B alone is insufficient; tolerances are
   per path, not transitive. No PCM validation CLI exists yet.
   A/B_ref known loss remains lossy, never strict success; verify the chosen
   fallback against a target plan fixed before observing actual playback.
   Blocked strict assessment is not runtime verification: record validation
   not_run/unverified separately. B_ref/B cannot excuse player mismatches
   with source->target loss. Unknown required items yield unverified; keep
   known_losses visible. Confirmed unexpected mismatch yields fail.

Do not:
- Assert every MDX note physically resets the decoder, or equate stream stop,
  gate intent, DMA stop, cursor restart and chip reset.
- Patch P for immediate held pan when the chosen native profile latches it.
- Treat PDX bytes/static commands/compiler exit0 as runtime equivalence.
- Apply six-sample note-boundary tolerance to supply/consumption/reset/order.
- Relax the KMSM009 cadence check just to accept it (12th delivery61 vs~62.0928).
- Rewrite source IR around MML/PDX slots, silently drop unsupported PCM, import
  a new compiler/player wholesale or commit ROM/private song/sample bytes.
- Treat best-effort as permission to hide unknown semantics, invalid output or
  unexpected mismatches; loss applies only to explicitly defined target rules.

Ignored evidence:
- outputs/pcm_pdx_2026-10-08/{native_regression,public,public_batch,external_acceptance}/
- outputs/pcm_target_2026-10-09/{strict,best-effort,batch,native_regression}/
- outputs/research/{NanoDrive8,mdx2vgm,mdxtools,x68kd11s}/

Workspace is shared with WSL; no copying is required. Previous user commit
35cd106. Agent has not committed current changes. Current docs reflect the
user's clarified goal, source review and implemented target checkpoint.
