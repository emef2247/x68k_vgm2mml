# Source-aware MDX CLI and normalization defaults

## Accepted scope

Normal conversion is `python vgm2mml.py input.vgm --outdir OUTPUT`.
Separate source usage, target format, chip projection/model, fidelity policy and
diagnostic/compatibility controls. Do not add a public articulation option.
CLI cleanup must not implement PCM Data Bank/DAC Stream decoding or rewrite
source IR. The independent MXDRV/IOCS/MMDSP PCM stopping investigation is paused.

## Implemented behavior

- `--target` describes MDX/MGSDRV format. Old `opm`/`opm-additive` values remain
  deprecated aliases restricted to their previous PSG/SCC source scope. The
  additive alias preserves its gain/pitch defaults and rejects an explicit FM
  model conflict.
- Inspect actual commands before routing: OPM/PCM use the native path; supported
  PSG/SCC use the usual structured OPM generation path. Ignore unused clock
  declarations, including invalid unused type/dual flags. Missing declarations
  for used chips, unsupported chips/instances and unsupported used combinations
  remain explicit errors.
- Preserve existing inactive OPLL initialization and undeclared zero-volume SCC
  initialization handling. Report these exceptions with reasons and command
  counts rather than removing evidence from the source inventory.
- OKIM6258 banks/stream controls still reach the existing PCM assessment. Other
  used DAC stream destinations are explicit unsupported-stream errors. A data
  block alone for an unrelated chip does not fabricate that chip's playback.
- Group help and README into normal, compatibility, advanced/fidelity and
  diagnostic use. Record source inventory and route in `*.conversion.json`.
- Structured MDX normalization defaults ON, with explicit ON/OFF forwarding
  through export and verification utilities. `--no-normalize-lengths` preserves
  the previous timing projection. MGSDRV remains opt-in; legacy/registers are
  OFF by default.
- A rejected correction returns to the same structured projection and clock.
  Record requested/enabled/adopted, rejection reason, before and selected clock.
  Keep source timing/state/Segments and all diagnostic pass dumps.
- PSG/SCC correction additionally checks original source boundaries after the
  intermediate OPM lattice; reject collapsed intervals and excessive cumulative
  error. Source-loop validity remains part of the check.
- PCM correction currently retains the established shared OPM/PCM clock and
  records that PCM-aware normalization has not been verified. Default ON is not
  an error. Target loss/eligibility remains separate from normalization adoption.
- Registers-held behavior is named internally as `held-register-compatibility`;
  structured projection uses `musical`. No independent public articulation
  switch was justified for the current supported combinations.
- PCM helper/policy configuration on a non-PCM input is recorded as inapplicable,
  with a message. This permits a common batch configuration without silent use.

## Preserve reference material on reruns

Cleanup may invalidate this tool's current MML and target reports before source
preflight, but stem/extension alone must not authorize deletion of MDX/PDX.
Default output is the input directory and an original MDX+PDX may be adjacent to
its derived VGM. Previous PCM binary cleanup therefore requires a generated
assessment, matching saved path and matching SHA-256. Preserve missing-record or
modified binaries and record them as retained existing artifacts. Typed PCM
generation reports an artifact conflict if it would overwrite them; use a
separate `--outdir`. This is not a source eligibility restriction.

Regression coverage includes both successful FM conversion and unsupported
preflight with adjacent sentinel MDX/PDX, modified previous output, matching
generated output cleanup, PCM overwrite refusal, and source-file preservation.

## Validation

- 150 focused tests passed across CLI routing, native/projected OPM, PCM IR and
  target projection, normalization, export/roundtrip and MXC adaptation.
- Actual default-MXC public OPM roundtrip: 9/9 success.
- Actual default-MXC public PSG export: 11/13 success. The other two inputs
  retain their known noise/hardware-EG conversion errors; no compiler failures.
- Public MGSDRV regression passed during a broad suite run. That run was
  interrupted during the optional private OPLL catalog and is not a full-suite
  success claim.
- Authored native OPM and PSG jittered scores adopt correction. Their source
  bytes and Segment CSVs remain identical with correction ON/OFF. PSG maximum
  cumulative error is 67 samples within the existing candidate bound (741).
  An authored positive-interval collapse case declines correction and has
  byte-identical structured MML to explicit OFF.
- Local BOSCON01 remains blocked/unverified with existing
  `unsupported_pcm_data_bank`/`unsupported_stream_control` diagnostics, retained
  source evidence and runtime `not_run`; no source decoder was changed.
- DSLY4_02 listening artifacts regenerate successfully. MXC title adaptation
  restores 103 CP932 bytes from an empty native header; the entire data suffix
  is byte-identical. See `2026-10-09_mxc_title_boundary.md` for the independently
  authored 64/65-byte compiler/runner tests. Native GUI behavior is unverified.

Ignored evidence lives in `outputs/cli_cleanup_2026-10-09/`: `focused_tests.log`,
`opm_roundtrip/results.csv`, `psg_export/results.csv`, `boscon01/`,
`normalization_evidence/inspection.json` and corresponding before/after CSV/MML,
and `listen_dslayer02/`. Private/generated music and tool binaries stay ignored.

## Next time

Use the canonical normal command and inspect `*.conversion.json` plus
`*.mdx.normalization.json` before overriding controls. Keep target-clock adoption
distinct from semantic validation status. Do not weaken a comparator to make
lossy/unverified PCM pass. Any Data Bank/DAC Stream implementation is a separate
task with its own source evidence and independent PCM reference. GUI/PCM stopping
research requires the user's explicit resumption.
