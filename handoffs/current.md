Project: x68k_vgm2mml

Current checkpoint (2026-10-09): approved CLI cleanup implemented. The canonical
normal command is python vgm2mml.py input.vgm --outdir OUTPUT. Actual VGM commands
select native OPM/PCM or PSG/SCC-to-OPM, unused declarations do not change routing,
and unsupported used chips/streams cannot silently produce partial success.
Structured MDX normalization defaults ON; --no-normalize-lengths disables it.
Declined correction keeps the same structured renderer and original clock, with
adoption/reason/before/selected diagnostics. PCM retains its shared clock and
records PCM-aware normalization as unverified; default ON alone never blocks it.

Latest user scope: no public articulation option, no source IR or PCM stream
decoder rewrite in CLI cleanup. Registers-held behavior is separated internally.
Compatibility/advanced/diagnostics are separated in help and README. Retain
MDX-to-VGM and semantic roundtrip verification. Native GUI and the separate PCM
stopping investigation remain paused/unverified.

MXC title investigation is complete for the selected MXC v1.01 + run68 pair:
64 CP932 bytes survive, 65 become empty despite the intact #title and unchanged
native arguments. The adapter restores only empty titles above this threshold,
preserves the complete data suffix, validates the result and saves native MDX
plus audit metadata. No MMDSP display fix is claimed.

FM export/roundtrip still default to MXC. Explicit --compiler mmlx remains
available without fallback. PCM retains typed MDX+PDX generation whose FM portion
uses mmlx, reported as typed_pcm_mmlx. Compilation, semantic validation and
native display are separate results.

Branch: codex/psg_data_quality. The accidental git switch main / git pull was
audited: the pulled merge had the same tree as the previous state and working
changes survived. No reset or rollback was performed. The workspace is shared
with WSL; no copying is required. Current CLI/title changes are unstaged and
uncommitted; the prior MXC-default checkpoint was committed by the user.
Tool binaries, generated music and private evidence are ignored, not staged.

Read first:
- docs/project_knowledge.md
- field_notes/2026-10-09_cli_cleanup.md (current implementation/validation)
- field_notes/2026-10-09_mxc_title_boundary.md (title evidence and adaptation)
- field_notes/2026-10-09_mdx_compiler_baseline.md (tools/path/dialect/checks/scope)
- field_notes/2026-10-09_psg_export_data_audit.md (batch, size and Segment audit)
- docs/psg_scc_opm.md
- field_notes/2026-10-09_mmdsp_pcm_stop_observation.md (paused runtime problem)

Implemented in the current checkpoint:
- py/conversion_config.py inventories source usage and resolves format/routing
  without changing chip decoders. Deprecated target aliases preserve their
  source scope and model defaults.
- Compact conversion and normalization JSON are written for ordinary conversion;
  source/state/Segment and detailed target dumps remain first-class artifacts.
- PSG/SCC correction checks cumulative error against original boundaries. PCM
  correction declines with a reason, preserving the shared clock and outputs.
- Failed preflight invalidates owned target MML/reports. Adjacent reference
  MDX/PDX must survive; previous generated binaries may be deleted only when
  assessment path/status/hash match. PCM refuses unowned binary overwrite and
  reports an artifact conflict, independent of source eligibility.
- Compiler title audit preserves canonical UTF-8 MML, exact prepared CP932/CRLF
  input, unmodified native .mxc.mdx and .mxc.metadata.json.

Earlier implementation retained:
- Large PSG projected CSV provenance fields are preserved, with the process-wide
  field limit restored after reads/errors. No field truncation or source IR
  rewrite. The earlier private82-file mmlx batch improved from8 to57 artifact
  successes;24 explicit unsupported inputs and1 track-offset capacity failure.
- scripts/compare_opm_vgm.py: explicit zero-based channel mapping, union of
  positive-duration state/Segment intervals, separate Key command events,
  nominal pitch and command/wait-size diagnostics. Raw/state/Segment/interval
  CSV and hashes retained. This is not the strict instantaneous-Key comparator.
- Fixed psg_scc_to_mdx.py's obsolete summary key for structured verification.
- scripts/mdx_compiler.py: short isolated invocation, strict CP932/CRLF,
  errors/missing output/parser rejection before publication. Exact prepared
  input saved under _compiler_inputs/, canonical UTF-8 MML unchanged.
  Preparation joins ties, splits long rests, and uses o8 at a known relative
  octave8 ascent for a verified MXC v1.01 defect. No source/IR pitch clamping,
  and unknown octave state is not inferred.
- Export CSV records selected/effective compiler and compiler_input. Missing
  tools and stage failures remain explicit; validated MDX survives replay
  failure. The compiler column on conversion failure does not mean it ran.
- OPM roundtrip CLI uses MXC for both initialization and converted MML, then
  --from-mdx replay and the unchanged comparator. Native input and selected
  compiler are recorded. Existing internal diagnostic callers keep mmlx.
- README documents native dependencies, explicit mmlx and the PCM exception.

Current completed checks:
-150 focused tests passed, including reference binary preservation and PCM clock
 invariance. See outputs/cli_cleanup_2026-10-09/focused_tests.log.
-Actual default-MXC public OPM roundtrip9/9 and PSG export11/13; remaining2 are
 existing noise/hardware-EG conversion errors.
-Authored OPM/PSG correction adoption and positive-interval-collapse fallback
 inspected with persistent source/Segment/target dumps. Source bytes and Segment
 CSVs match ON/OFF; declined correction gives identical structured baseline MML.
-BOSCON01 remains blocked/unverified with original bank/stream diagnostics and
 runtime not_run. No new source stream decoding.
-Four authored native MXC title/parser cases passed; DSLY4_02 restores103 CP932
 bytes with identical native data suffix. GUI remains unverified.
-Public MGSDRV regression passed in a broad run interrupted later during the
 optional private OPLL catalog. Do not report the whole suite as passing.
-Architect final review cleared unused OPM declaration, stale target evidence and
 reference binary preservation fixes after focused regressions.

Earlier completed checks:
-79 focused Python tests passed:18 export,11 adapter,7 roundtrip-batch,
 43 PSG/OPM/audit tests.
-Actual MXC public OPM9/9 compiled, parsed and replayed.
-Actual MXC public OPM9/9 semantic roundtrip passed, maximum source timing
 error0samples, existing comparison conditions unchanged.
-Actual MXC public PSG11/13 generated; the other2 fail during conversion for
 existing noise/hardware-EG limits, with no compilation failures remaining.
-Independent mdxdump decoding of the public upper-octave case confirms all434
 note numbers/durations match canonical MML, including highest note93.
-Actual private DSLY4_03 MXC listening artifacts generated.
-Architect completion review found no blocking implementation issue; its
 requested decoded octave-boundary check was completed.
-Roundtrip review also found a failed-rerun stale-evidence gap. Cleanup now
 precedes conversion/preflight, the regression passes, and review is clear.
-No native GUI, all-song strict roundtrip or PCM runtime certification claimed.

Ignored evidence:
- outputs/cli_cleanup_2026-10-09/ (current checks and listening data)
- outputs/mxc_title_2026-10-09/recheck/ (authored native title boundaries)
- outputs/mxc_export_2026-10-09/public_opm_prepared/results.csv
- outputs/mxc_roundtrip_2026-10-09/public_opm/results.csv
- outputs/mxc_export_2026-10-09/public_psg_prepared/results.csv
- outputs/mxc_export_2026-10-09/block_boundary_fixed/note_fidelity.json
- outputs/mxc_export_2026-10-09/listen_dslayer4/tracks/DSLY4_03.vgm/
- outputs/mdx_compiler_2026-10-09/mmdsp_pairs.zip (reference pairs and native
  MXC/mmlx authored controls; GUI observation not_run)
- outputs/psg_data_2026-10-09/ and outputs/listen/psg_data_2026-10-09/ (earlier
  mmlx batch and comparison; do not label these MXC outputs)
- Native tools: outputs/research/mxc_tools/extracted/mxc.x and
  outputs/research/run68x/build/run68. Versions/hashes in compiler field note.

Historical findings retained for future requests, not current blockers:
- GRA1_01 strict Key-Off comparison differs because a KF write occurs before
  release in target and after release in replay at the same sample. Positive
  durations/end/Key commands match. Do not weaken the comparator or source IR.
- Source VGM song-loop emission is incomplete; finite phrase loops are separate.
- XANADU14 exceeds track offsets;8 earlier independent VGM comparisons show
  10-44x expansion, dominated by soundlog's per-MDX-tick waits. No packing fix.
- CLI format/projection/policy separation is now implemented. Future Z_MUSIC
  should consume source IR with its own target profile.

PCM investigation is explicitly paused. User environment: XM6 TypeG3.32,
MXDRV30.x+PCM8, MMDSP displays MXDRV, audio remains after ended/stopped for two
short generated pairs. Cause, resident profile and actual IOCS/DMA stopping
are unknown. Do not request further probes or change gate/EOF/reset until the
user resumes this work. Production PCM code was not changed here. Keep
strict/best-effort target-side loss assessment and unverified/not_run runtime.

For resumed PCM work read docs/pcm_roundtrip_validation.md, docs/pcm_pdx.md,
field_notes/2026-10-09_pcm_mxdrv_roundtrip_review.md and
field_notes/2026-10-09_pcm_target_projection.md. Independent runtime R, direct
MDX/PDX C0/C1, source stream expansion and A/B/C comparison are unimplemented.
soundlog/native-port stubs/NanoDrive8 are not a standard PCM oracle. Known loss,
unknown behavior and confirmed mismatch stay separate. Do not put target limits
into PCM IR or infer hidden F7/q and decoder reset from VGM/logical stop.

Do not commit or push automatically. The user authorized staging related files
and requested an English commit comment. Private fixtures and tool binaries
must remain ignored. Wait for the user's next work request after this checkpoint.
