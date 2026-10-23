# Native PCM source evidence and target placement

Japanese original: [pcm_source_and_targetJ.md](pcm_source_and_targetJ.md).

For smaller PCM output, see [PCM profiles](pcm_profiles.md). The existing source/target boundary is preserved.

MSM6258 encoded sample identity uses codec plus exact supplied bytes. Decoder
reset/continuation, rational nibble rate, raw pan and source timing belong to
playback evidence, not sample identity. Hashes index candidates; actual bytes
resolve equality. Observed STOP/PLAY resets and a fresh-VGM initialization
assumption must remain distinguishable. Supplied bytes and nominal duration
do not establish measured decoder consumption or waveform equivalence.

Target-independent PCM records preserve source options, blocks/commands,
ordered B7 transfers and control/playback spans. MDX PDX bank/slot limits and
allocation belong to the target. PCM MML text is optional: target MDX commands,
PDX and any readable rendering must consume the same immutable binding.
Future Z_MUSIC output must consume source evidence with its own
placement; neither MDX text nor PDX slot numbers become the common IR.

## Automatic PCM policy selection

`--pcm-policy auto` is the default in the canonical converter and batch export.
It selects from actual captured DAC Stream Control supplies, not clock/header
flags or unused stream setup:

| Source supply | Effective policy |
| --- | --- |
| DAC supplies, including mixed direct B7 and DAC supply | best-effort |
| Direct writes without actual DAC supply | strict native/direct handling |
| Other projections without DAC supply | existing strict projection |

Explicit `--pcm-policy strict` or `best-effort` overrides automatic selection.
Auto never repairs an unresolved reset, unknown play state, missing data bank,
unsupported codec, invalid rate or malformed command. Those checks remain.
Low-rate transcoding remains a declared loss; auto permits it only when its
source supply selects best-effort, or when best-effort is explicitly requested.

The target assessment saves `policy_selection` (requested, effective, reason,
observed supply count and source origin). Batch CSV retains the requested and
effective policies and reason; console and TXT reports show the selection.

For an otherwise eligible independent reset with only irregular byte supply,
best-effort can project captured bytes into continuous PDX delivery whether
those bytes came from direct writes, DAC supply, or both. Native source timing,
byte order and source eligibility flags remain unchanged. Target loss
`byte_supply_schedule_not_preserved` records direct/stream byte counts, cadence
error and unsupplied PLAY tail. Strict still rejects that timing loss. This
fallback is not a claim that pauses, FIFO state or waveform timing are exact.
Single/parallel bank preflight and size profiles share its eligibility check.

## MSM6258 virtual-register interpretation

The VGM byte reader retains every B7 address/value. Interpreting that address
is a separate stage. The following compatibility behavior follows the pinned
[libvgm MSM6258 implementation](https://github.com/ValleyBell/libvgm/blob/70e1d1fad8c03df2ce4bfb13f8599c56920dcdc8/emu/cores/okim6258.c),
not a new claim about physical MSM6258 registers:

- Pan register2 uses low disable bits0/1 for audio. Upper bits remain in raw
  transfers and control data; `pan_non_audio_bits` observations retain their
  values. They do not invalidate an otherwise representable source.
- Virtual address0x17 has no reference write handler. It is retained as
  `unmapped_register_17` source evidence, without inferring a pan/clock alias
  or confusing it with the VGM stream chip identifier0x17. Best-effort target
  projection may omit it with `unmapped_register_17_not_projected`; strict
  projection rejects that explicit loss. Other unsupported addresses retain
  their existing blocking behavior.
- Direct bytes supplied while known/assumed stopped become
  `direct_supply_while_stopped` observations, just as derived stream supplies
  already do. Best-effort projection omits those supplies using the reference
  stop-to-PLAY FIFO-reset profile and reports
  `stopped_direct_supply_not_projected`. Active playback sample bytes and raw
  supply history remain distinct and unchanged. Native FIFO behavior remains
  unverified. Data supplied with an unknown play state still block projection,
  including best-effort mode.

Source observations, effective pan, target omissions and runtime uncertainty
are written separately into native CSV/JSON and target assessment CSV/JSON.
The changes do not establish waveform equivalence or solve capacity limits.

Finite bank-4 DAC stream supplies are a separate derived table with triggering
command, transfer sequence, original bank/block position and VGM time. They do
not masquerade as original B7 writes. The source scheduling profile is pinned
libvgm at 44100 Hz/32.32; original same-tick commands precede DAC supplies.
Stream STOP/exhaustion never inserts chip STOP/reset. Bit-2 codec interpretation
and stopped-to-PLAY FIFO behavior name that reference profile, not native IOCS
or silicon certification. `consumed_nibbles` remains unknown.

Conservative source cadence eligibility remains unchanged when target
best-effort collapses a fully reconstructed finite stream into continuous
PDX delivery. Keep source bytes/times, cadence error and unsupplied PLAY tail,
and report discarded delivery timing in target assessment. Known/assumed
stopped supplies and active song-loop entry remain source observations; target
omission, native buffer uncertainty and unimplemented song looping are distinct
results. Neither byte equality nor a nominal tail duration proves audible
equivalence. A target capacity failure retains completed MML/PDX and target
dumps, but must not be reported as a completed MDX/PDX pair.

PCM validation separates target note/gate intent, IOCS/DMA playback requests,
chip PLAY/STOP/decoder state and VGM stream scheduling. A stream stop is not
a chip stop; cursor restart is not by itself decoder reset. Use a versioned
MXDRV/IOCS profile and an independent playback baseline. Matching A/B after
reusing an uncertified player is internal consistency, not standard playback
proof. Unknown consumption/reset/effective-control fields remain unverified.

Keep MDX header/repeat offsets, PDX sample offsets and sample byte lengths
distinct. Standard PCM1 reads a 32-bit PDX offset and the low 16-bit length;
a PDX file or sample address above 65535 is not itself a sample-length overflow.
PCM NOTE selects a slot; standard MML does not provide a verified arbitrary
sample-byte seek. Source EOF is not an observed chip STOP. A finite track's
F1/00 and its preceding note gate are separate: in the inspected MXDRV +17
PCM1 path, an unheld q8 gate expires before processing duration expiry, while
F1/00 has no unconditional PCM1 cut. Port STOP/END stubs can confirm this call
intent but cannot certify native cessation. Do not infer mandatory trailing
rests, payload stop markers or alignment padding from an unresolved noise report.
Conform generated MDX to the selected MXDRV reference; native verification is
not a reason to leave known request handling unimplemented in a replay backend.
PDX does not adapt stopping behavior to the user's playback environment. A stub
in a separate diagnostic player is neither a cause of MMDSP playback failure
nor evidence that the generated MDX is correct at runtime.
See field_notes/2026-10-09_pcm_pdx_end_review.md for bounded reference evidence.

MDX target projection owns fidelity/eligibility and explicit approximation;
never rewrite common PCM evidence to fit target limits. Strict conversion
disallows known semantic loss. An explicitly selected best-effort policy may
emit usable MDX+PDX using a defined fallback with source-linked loss diagnostics.
Separate pass, lossy (known target loss), unverified and fail, and keep artifact
generation status separate. Unknown IOCS behavior is not a confirmed target
constraint; unexpected mismatches are not acceptable best-effort loss. Known
losses and unresolved items can coexist and must both remain visible. Lossy
artifacts do not pass strict roundtrip validation. Target projection success
does not certify runtime equivalence; unexecuted runtime comparisons stay
unverified/not_run even when all requested artifacts were generated.

For MXDRV 2.06+17 Rel.X5-S PCM1, held FC pan changes do not request an immediate
IOCS update. The defined best-effort projection retains onset pan until the
next attack, records each affected source interval, and inserts no artificial
retrigger. F7 precedes the note whose gate keyoff it suppresses; readable ties
follow that note. One typed PCM target command list drives both MDX construction
and readable rendering. Native PCM1 uses the low length word; that evidence
must not be promoted to a limit of other playback modes.

PCM packages now select the reference-tested extension route: sixteen tracks,
one initial E8 on A, P playback and inactive Q-W. The typed builder preserves
compiled A-H commands except the new mode marker, exact P commands, voices,
title and PDX reference. This target-only choice does not change source PCM IR,
the shared clock or encoded sample bytes. It requires a PCM extension in the
player; six named listening artifacts passed in the user's MMDSP environment,
not all possible drivers or inputs. Retained bank/slot/sample-size limits are
the current verified projection scope, not newly established extension limits.
Held pan is still deliberately omitted and diagnosed as projection loss;
immediate extension pan/reset behavior remains unverified. Sample-length
eligibility now follows the selected format: standard PDX uses 16-bit lengths;
EX-PDX stores 32-bit lengths, bounded by the PCM8 24-bit interface and the
1,200,000-byte total-file budget. This does not establish runtime playback
validation. See [PDX length format](pcm_pdx.md#pdx-length-format).
Inspect the actual serialized mode before reporting generation success; an old
helper must not silently emit the former standard-nine profile.

OPM and PCM share one MDX clock and common source end. Target-only
normalization cannot move one chip's boundaries independently. PCM pan
operands 1/2 have the opposite left/right meaning from MDX FM. Standard X68000
PCM uses 4-bit encoding and 10-bit output; preserving bytes alone cannot
represent a 12-bit decoder clamp. Keep unsupported source values inspectable
and diagnose them in the target.
The normalization default must not itself reject PCM input. Current projection
tries PCM-aware shared-clock correction and checks the candidate before
adoption; a candidate-specific failure falls back to the baseline when that
baseline is usable. The earlier instruction to always keep the baseline until
PCM-aware correction was verified describes the pre-2026-10-11 checkpoint, not
the current unconditional behavior. Record non-adoption separately from PCM
loss/eligibility and runtime validation.
Data Bank/DAC Stream decoding is a separate change from frontend cleanup;
unsupported stream semantics and their source evidence remain explicit.

See `docs/pcm_pdx.md` for current eligibility and tool limitations and
`docs/pcm_roundtrip_validation.md` for the independent validation design.

## Derived PCM packaging and shared clock

SegaPCM observed State/control Segments and original ROM bytes remain unchanged.
Runtime address progression, natural-stop gates and the mixed unclipped stereo
waveform are a separate source interpretation with explicitly named reset and
runtime-model assumptions; they are not newly observed register facts.
Stereo folding, clipping, resampling and MSM6258 ADPCM encoding belong to target
projection. Preserve source-linked mappings and report those assumptions and
losses separately. See [SegaPCM source/runtime artifacts](segapcm_segments.md).

The union of active runtime gates is packaged into at-most-eight-second chunks under the standard profile,
with splits at the MDX song-loop boundary and EOF. Fractional native gate bounds
round outward by less than one 44100 Hz source sample. Packaging boundaries
are not Key-On/Off gates, source byte supplies or observed decoder resets.
The derived analysis declares `normalization_omission_safe=False`; a short
packaging tail survives even if it falls below the configured whole-gate cutoff.
Unsupported source PCM cannot become eligible by omitting a short playback.

FM and PCM use one final MDX clock and common source end. Encode each original
audio interval to its final scheduled gate duration, retaining original bounds,
source event/gate identities, target ticks and target sample-count error. The
standard bridge uses F4/15625 Hz and the nearest positive even sample count
(two samples per ADPCM byte), at least two samples. Its rounding error relative
to the scheduled duration is at most one F4 sample (not one VGM source sample).
If a positive chunk collapses under the selected clock, alignment raises an
error rather than silently omitting the chunk. The current verified per-sample
size guard also remains active. This derived target re-encoding may change the
PDX payload; it does not mutate original ROM, source State/Segments or PCM IR.

A recorded loop traversal becomes fixed target audio, freezing the recorded
waveform and phase. Later source traversals may evolve differently. Report
that limitation, along with stereo folding, resampling without antialias
filtering, clipping/requantization and independent chunk-decoder assumptions;
do not claim native loop or acoustic equivalence. Runtime decoder reset and
physical playback remain unverified by artifact generation alone.

### Current implementation and historical evidence

The packaging/shared-clock policy dates from 2026-10-13. Its current code is
split between the SegaPCM adapter `py/segapcm_pcm.py`, the shared waveform bridge
`py/pcm_waveform_mdx.py`, and final-clock integration in `py/opm_conversion.py`.
`*.segapcm_pcm_mapping.csv` and `*.segapcm_pcm_bridge.json` expose source bounds,
final-clock alignment, target counts/errors and losses. Existing
`tests/scripts/test_segapcm_pcm.py` checks short tails, unchanged source bounds,
even counts, error bounds, collapsed chunks, clipping and payload deduplication.
The test definitions were inspected, not rerun, during this documentation move.

The dated experiment/test counts and listening status remain in the external
`field_notes/2026-10-13_segapcm_pdx.md` and its regression follow-ups. They do not
certify the current revision or every playback environment. The older statement
that normalization leaves PDX payload bytes unchanged applies to retained
native encoded PCM, not this derived waveform packaging route.


