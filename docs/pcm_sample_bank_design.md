# Reusable PCM sample-bank projection

Status: a first finite-view implementation is available. The objective is
traditional MDX/PDX sample reuse, not binary
identity with a particular reference bank and not a new playback format.

## Implemented first milestone

The SegaPCM route now tries `py/segapcm_bank.py` before mixed-waveform packaging.
It supports independently startable, finite one-shot source views at stable
delta, volume, pan and ROM contents. Complete views are converted once at the
selected `standard`, `low` or `ultra_low` target rate; event duration does not
trim the stored material. The source ROM, States, control Segments, native
runtime waveform and inferred gates remain available.

```bash
python scripts/export_mdx.py INPUT_DIRECTORY --outdir outputs/listen/bank \
  --pcm-policy best-effort --no-vgm --segapcm-projection auto
```

The same option is accepted by `vgm2mml.py`:

- `auto` (default): try the complete finite bank route. On an explicitly
  unsupported capability, use the existing mixed route for the whole song.
- `bank`: require this finite bank route and report the unsupported capability
  instead of falling back. This is useful for identifying the next missing case.
- `mix`: explicitly use the previous mixed-waveform/chunk packaging.

`<stem>.segapcm_projection.json` records the requested/selected strategy and the
first fallback reason and source gate. Invalid input, missing runtime evidence
and unexpected exceptions are not caught as capability fallback. A `bank`
selection does not mean lossless conversion or native playback certification.
Known transcoding losses still require `--pcm-policy best-effort`.

### Supported identities and controls

A source-view identity includes chip/ROM generation, bank, exact 16.8 runtime
cursor, end page, delta, source frame rate, source bytes and target profile.
The fractional cursor survives an explicit disable/restart and is retained in
this identity. Volume, pan and gate duration are excluded. Equal converted
payload bytes can additionally share one target sample even when source-view
identities differ; each source view retains its own mapping row.

Each view uses a common amplitude scale of128 before MSM6258 encoding; there
is no per-asset peak normalization. Onset gains are approximated by MDX volume
commands. Left-only/right-only/silent routing is retained; unequal nonzero
left/right gains become a centered average. The numerical MDX-volume-to-driver
gain law uses an explicit inverse MXDRV/X68Sound compatibility table; resident
driver acoustic agreement remains unmeasured. True silence is omitted rather
than mapped to PCM8's nonzero minimum gain. Linear resampling lacks antialias filtering. Independent decoder
reset is an output assumption, not an observed source reset.

Natural sample exhaustion, explicit disable and source EOF remain distinct
termination values. A truncated gate retains the complete asset. Native gate
bounds round outward by less than one source tick, and native frame onset may
differ from the source write by less than one native frame. Asset lengths use
the nearest positive even target sample count (at most one target sample of
duration rounding); final clock correction schedules events without stretching
or re-encoding the immutable asset.

### Allocation and current limits

Independent playbacks use P-W through the typed MDX plan. Allocation uses the
final shared MDX clock, releases before attacks at equal ticks, reuses freed
tracks and never steals an active voice. Without `--force`, a ninth simultaneous
voice is blocked. With it, a whole new gate is omitted with provenance and a
capacity assessment; unused target samples consume no slots. Source IR remains
unchanged. One global binding is used by all PCM tracks, readable MML and PDX.

After the complete-view attempt, frame-effective finite parts handle muted
initialization, mid-sample starts, actual cursor seeks and finite held-control
trajectories. Stable parts share complete ROM/suffix views. Baked finite variants
retain absolute source gain and use full target onset volume to avoid applying
gain twice; they are not labeled recovered ROM instruments. Changing stereo pan
within a variant is centered and reported as loss. Ordinary held `@v`/`p`/`F`
commands are not used as live controls. Part boundaries do not rewrite native
source evidence. See [continuations](pcm_bank_continuations.md) for details.

Actually traversed audible sample loops, missing complete-view ROM bytes,
song-loop-held parts and explicit capture/variant resource limits still block
the bank route. End-page FF is handled only where the runtime reaches its wrapped zero boundary without an earlier wrap.
The one-bank 96-slot and 1,200,000-byte total budget are retained. Standard
PDX limits each sample to 65,535 bytes; the default EX-PDX target uses the
PCM8 24-bit length, further bounded by the total-file budget. See
[PDX length format](pcm_pdx.md#pdx-length-format).
Song-loop seams must be independent playback boundaries; a gate held across
`L`, including an active source-EOF continuation, uses the mixed fallback.

Fallback is deliberately whole-song: one unsupported active view can prevent
all bank reuse for that song. Therefore success on authored finite patterns
does not establish that full game-derived songs use the new bank path, nor
that their PDX size or native buffer requirements improve. Inspect the strategy
JSON before comparing capacities. Internal loop bodies and a bank/mix hybrid
remain further work.

### Inspection artifacts and validation

- `.segapcm_bank.assets.csv`: source-view identities, payload binding, full
  source/target lengths, encoding error and asset-duration rounding.
- `.segapcm_bank.events.csv`: source gate/channel/events, exact native bounds,
  rounded event bounds, termination, onset gain/pan and target settings.
- `.segapcm_bank.parts.csv`: effective seek/enable boundaries, silent prefixes
  and ROM-view versus trajectory-variant classification.
- `_diagnostics/<stem>/pcm_blocks/`: all candidate listening WAVs and usage /
  retention indexes, including samples omitted by capacity selection. See
  [PCM block previews](pcm_block_previews.md).
- `.pcm_samples/`, `.pcm_samples.csv`, `.pcm_segments.csv`, `.pcm_source.json`:
  derived samples and playback IR, separate from native SegaPCM evidence.
- `.pcm_projection.csv`, `.pcm_clock.csv`, `.pcm_target_commands.csv` and
  `.pcm/target.tsv`: final P-W allocation, shared timing and typed commands.
- `.pcm_bindings.csv`, `.pcm.assessment.json` and force/omission reports:
  packed-bank references, fidelity limits and explicitly omitted events.

The authored `SEGABANK` fixture uses one sample three times with different
durations/gains/pans, including two overlapping uses. Public checks generate
readable P/Q MML and a typed MDX/PDX pair with one bank binding. Existing
`SEGAONE` uses the finite bank; `SEGAMIX` and `SEGALOOP` exercise explicit mixed
fallback. These verify structure, bytes and references, not listening.

Use `--no-vgm` for MDX/PDX regression: the current `soundlog` replay backend
does not preserve the required PCM holds/stops/reset behavior and can report
`pcm_replay_unavailable` after the pair was already generated. This is distinct
from target capacity failure and from native playback/buffer behavior.

## Deliverables and order

The converter must produce editable MDX MML and inspectable PCM IR describing
reusable samples and their playback. PDX packing is a later target operation
consuming the same binding as the MML. A packed PDX alone is not sufficient.

Proceed from original MDX/PDX structure and current-output measurements to
identified gaps, then the smallest projection change. Do not replace the whole
PCM IR or introduce Z-MUSIC/MPCM output as a prerequisite. Driver APIs and
features not expressible by the selected MDX compiler/runtime are separate.

## Existing behavior to preserve

- Native MSM6258 already separates encoded `PcmSample` from `PcmPlayback` and
  deduplicates independently reconstructable samples by codec and actual bytes.
  Reusable-bank structure is not wholly absent from the project.
- SegaPCM retains observed ROM generations, register/control Segments and a
  separate runtime model. Its current target bridge uses a mixed waveform,
  packages active spans into long chunks, folds to mono, resamples/re-encodes,
  and deduplicates only identical resulting payloads.
- The original typed MDX projection enabled PCM4/8 but played on P only, with
  Q-W inactive. The finite bank path now allocates P-W; existing single-PCM
  routes keep their P-only behavior.
- Existing source dumps, waveform fallback, force/capacity assessments and
  shared timing proofs remain available. This proposal does not redefine
  source State/Segments to make a bank convenient.

## The required distinction

A sample is reusable material. A playback is a timed use of that material.
A PDX slot is a target binding, not a source sample identity.

| Layer | Retain |
|---|---|
| Native source evidence | ROM generation/ranges, format, ordered writes, clocks, decoder state/reset knowledge |
| Sample or source view | Stable identity, bytes/data reference, range, decoding prerequisites, observed loop information |
| Playback | Source voice, sample/view identity, start/stop, offset, rate, volume/pan and ordered held controls |
| Target asset | Converted bytes, fixed encoding/rate profile, conversion identity and approximation evidence |
| Target event | P-W allocation, slot binding, scheduled gate/control times and losses |

Reuse or extend existing records where their semantics fit. Do not assume that
all these distinctions require new universal classes or a backend-specific
rewrite of native source IR.

A different note duration, pan or volume must not by itself create a new
stored sample. Gate duration controls playback; it does not set the waveform
length. Final MDX-clock alignment schedules events rather than stretching and
re-encoding an asset for each gate. Natural sample exhaustion and gate STOP
remain distinct and require the selected driver's semantics.

The same payload may sound concurrently on multiple target tracks. A single
asset can therefore be bound once and referenced by many playback events.
Asset content/conversion identity must remain independent of track allocation.

## Source-dependent feasibility

SegaPCM is the first candidate for a new bank projection because source ROM,
addresses and per-voice controls survive in VGM. Identify stable source views
before the existing mixed-waveform boundary. Keep ROM updates, start address,
fractional position, looping and runtime-model assumptions inspectable.

A native MSM6258 VGM can instead contain the already-mixed output of a software
PCM driver. Such a stream does not generally identify the original instruments,
separate voices or original PDX slots. A known MDX/PDX pair can establish a
reference bank/event baseline; it must not be silently used as missing source
evidence for an unrelated VGM conversion. Preserve the native exact-byte route
and diagnose unresolved independent starts rather than claiming general demixing.

Equal ADPCM substrings do not establish independent sample equivalence:
predictor, step state, nibble alignment and reset origin matter. Keep source
asset identity separate from target encoded-payload deduplication.

## Minimal MDX projection

1. Begin with finite, independently startable source samples at stable rates.
2. Reuse one target asset for equal source-view/conversion identities. Keep
   volume and pan in target events where supported.
3. Allocate overlapping playbacks to P-W with explicit, source-linked records.
   Retain note release/retrigger and loop-seam evidence. Do not steal an active
   voice or omit a ninth simultaneous voice without an explicit loss policy.
4. Use verified MDX rate/format commands. A source rate not representable by
   those commands may require a reusable rate-specific derived asset; this is
   distinct from baking an entire song or every note into PCM.
5. Preserve internal loops, offsets and held-rate changes in source evidence.
   Establish target support or diagnose the limitation; do not assume that a
   resident driver's full direct-call API is available through MDX.
6. Extend typed target plans and assembly/layout validation for active Q-W;
   the present single-P/inactive-Q-W contract must not be bypassed silently.

The first milestone needs neither extended PDX lengths nor multiple banks.
Keep those format/driver questions separate from proving ordinary reusable
samples and multiple PCM tracks. Retain existing constraints until independently
verified rather than changing limits to make a fixture fit.

## Inspection and acceptance

For a reference and a generated result, report bank bytes/table bytes, populated
slots, unique payloads, per-sample lengths, references per slot/track, playback
settings, track sizes and unresolved commands. A bounded first loop traversal
and finite-repeat expansion are not whole-song acoustic duration or raw attack
counts. Track usage is not itself a measured simultaneous audible-voice count.

Public authored acceptance cases should show:

- repeated uses with different gate lengths, volume and pan do not multiply
  target assets when their source view and required rate conversion are equal;
- two overlapping uses of one sample occupy separate PCM tracks but share one
  bank binding;
- rate variants are explicit and reused, with no per-gate clock stretching;
- reset/nibble-state differences prevent invalid ADPCM reuse;
- source/target event membership, timing error and allocation remain inspectable;
- the same bindings drive readable MML, PCM IR and packed PDX references;
- existing mixed-waveform output remains an explicitly identified fallback.

Report MML generation, PDX packing, compiled MDX capacity and actual native
playback separately. A smaller bank does not establish driver buffer fit,
correct release, retrigger, looping or acoustic equivalence.

For the proposed next steps on source continuations, mid-sample starts, held
controls, actual sample loops and feedback to PSG PCM, see
[Reusable PCM banks with continuations and source loops](pcm_bank_continuations.md).
Those extensions remain proposals, not additional implemented support.
