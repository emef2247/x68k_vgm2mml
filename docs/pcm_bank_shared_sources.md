# Shared PCM8 sample-bank projection

MSM6258, OPNA Delta-T and SegaPCM share the target sample reducer, 96-slot
binding, typed MDX commands and external PDX packer. Source interpretation
remains chip-specific. The default is `--pcm-bank-merge budget96`; explicit
`similar` and `off` retain their documented meanings. Known approximation
losses require `--pcm-policy best-effort`. PSG PCM is not changed by this work.

## Native MSM6258

The existing source analyzer already separates encoded samples from playbacks
and deduplicates equal independently reconstructable byte sequences. The new
common bank view adds target-only similar/96-slot replacement and onset-volume
compensation; it does not recover instruments from a software-mixed stream.

`pcm_bank_target.prepare` first runs the ordinary source/reset/supply/rate and
control validation. Capacity omissions are allowed internally during this
validation so a source with more than96 samples can reach the reducer. The
final user-selected policy and allocation run afterward. Source controls,
transfer ranges, reset knowledge, timings and encoded candidates are retained;
they must not be interpreted as supplies of the replacement representative.

`.pcm_bank.source_validation.json` records this preflight separately from the
final assessment. It is not final playback certification. Native IR remains
available alongside the reducer's target mapping. If no existing asset is
within the selected format's sample-byte limit, ordinary capacity handling remains;
no cropped or invented asset is substituted merely to pass validation.

## Finite Delta-T samples

`opna_pcm_bank` handles finite independently restartable ADPCM-B source segments
at a stable rate/level/pan. It nominally decodes the complete source sample and
converts it once per byte-content, rate and profile identity. Every accepted
segment starts with the same defined nominal Yamaha decoder state; memory
changes and continuation state are not inferred away.

Gate duration, onset level and pan do not create new stored waveforms. PCM8
onset gain approximates source level/256 once, with explicit quantization loss.
The complete asset may outlast a shorter gate; natural exhaustion may precede
a longer gate. Source gate timing and reset evidence remain unchanged. Target
independent MSM6258 decoder reset is an output assumption, not observed source
hardware behavior. Linear resampling, requantization and padding are inspectable
approximations; native DAC/prefetch behavior is not emulated.

Held-control continuations, repeat, zero rate, unresolved source state and
explicit resource bounds retain the existing continuous-waveform or legacy
adapter paths. Those derived assets can still use the common96-slot reducer.
Unexpected exceptions and source/sample hash corruption are errors, not fallback.
The ordinary shared-clock alignment remains in the existing waveform route;
new immutable finite assets are not stretched to match each gate.

Inspect `.opna_pcm_bank.assets.csv`, `.opna_pcm_bank.events.csv`,
`.opna_pcm_bridge.json` and `finite_sample_bank` in `.opna-opm.json` for the
chosen route and native playback/segment/sample links. The native ADPCM-B
State/Segment/sample files remain separate.

## Shared target artifacts and limits

`.pcm_bank_merge.*` records original-to-final asset/volume mappings, budget
replacements and error evidence. `.pcm_bindings.csv`, `.pcm_projection.csv`
and the typed target manifest drive the same MML/MDX/PDX sample references.
The CLI and results CSV report the selected PCM route and reduction statistics.

The verified target is one96-slot PDX bank with a 1,200,000-byte file budget,
including its table. Eight simultaneous PCM voices,
format-dependent per-sample limits, MDX compiler limits and actual player
memory remain separate constraints. Standard PDX permits 65,535 bytes per
sample; EX-PDX uses a 32-bit stored length, bounded here by the PCM8 24-bit
length and the total-file budget. See [PDX length format](pcm_pdx.md#pdx-length-format). A software mix cannot be demixed by this
bank layer. Private conversion/listening regression remains user validation.

See [reduction policy](pcm_bank_reduction.md),
[source and target evidence](pcm_source_and_target.md) and
[PCM interoperability](pcm_interoperability.md).
