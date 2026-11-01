# MSM6295 source and PCM8 sample-bank projection

Single-chip MSM6295, alone or with OPM, uses native source analysis and the
existing MDX/EX-PDX bank target. This is initial support for fixed clock/pin 7
and basic ROM mapping. Dual chips, NMK112/bank switching, dynamic rate changes
and changed ROM while a voice is active remain explicitly unsupported.

## Usage

```sh
python scripts/export_mdx.py INPUT_DIRECTORY --outdir outputs/msm6295 --no-song-loop
```

No source-selection option is needed. Actual MSM6295 commands select the route;
a clock declaration or empty ROM-size block alone does not require PCM output.
Auto PCM policy selects best-effort for the exact MSM6295-derived origin and
records msm6295_bank_transcoding. Explicit strict rejects known target losses.
Existing mmlx, 24 ms FM state, 8 ms normalization, 1200-second timeout, budget96
and EX-PDX defaults apply. --force retains its existing target-capacity scope;
it does not manufacture missing ROM or bypass source limitations.

Use a finite pass first. A voice held across the chosen song-loop boundary can
still be blocked by the shared PCM continuation guard. Source traversal retains
latch/voice state, with no invented restart. Playback memory and MXDRV track
buffers remain separate from compilation and packed-size checks.

## Native evidence and runtime profile

py/msm6295.py preserves ordered writes, original source IDs/traversal occurrences,
raw clock/flags, sparse ROM blocks, observed State and command Segments. A command
interval is not automatically an audible gate. Used ROM coverage is distinct
from unprovided bytes. Reset state is labeled as a reference assumption.

The pinned reference is libvgm bad50c571db45b872304bdcd0603dd2214f0663e:

- MSM6295 core SHA256: 00778ea2bb630abf549ea25671e9d19df50d4ce4889be9e1fcfa6739b5ae6194
- OKI ADPCM SHA256: 95ad62ea67fb3f239873abf79200ce11d3d548c40022ec02da0dd4a3abaf5af1

Four native voices have independent busy/cursor state. Pending commands,
accepted and ignored requests, explicit stop, natural completion and EOF are
separate observations/inferences. Preserve equal-timestamp order. An observed
invalid sample interval follows the reference's ignored-request behavior;
missing required table/data bytes block projection.

The source profile uses the reference integer grid clock // divisor while
retaining nominal clock/divisor separately. Header bit 31 pin 7 behavior is a
libvgm VGM convention. Native scheduling and target rounding are recorded
approximations, not a claim of analog/hardware timing equivalence.
Target ends are bounded by source EOF and the next accepted start on the same
channel. Native frame endpoints and target clipping reasons/amounts remain
separate in the event CSV.

## Reusable assets and target projection

py/msm6295_bank.py first infers source assets/playbacks without per-playback
waveform capture. Each unique source asset is decoded once, resampled and
re-encoded independently as MSM6258 ADPCM. Source asset identity includes byte
content, nominal length, native rate and decoder reset profile. Gain, sample
number aliases and early stop duration do not duplicate the waveform.

Onset attenuation maps through the existing PCM8 gain table with error evidence.
Silent source voices still occupy busy state. A stopped source playback keeps
the reusable full asset. Unavailable optional unplayed tails are represented as
incomplete prefixes; missing bytes actually consumed remain hard failures.

The fixed-map MVP conservatively rejects changed ROM while any voice is active,
even when the changed range might be unrelated. Restored unsupported extension
state can remain blocked for that run. These are implementation limits, not
chip restrictions. Raw source evidence is retained before target rejection.

The shared reducer, PCM8 allocation, typed target commands and external packer
consume a separate target view. Limits remain eight simultaneous PCM voices,
96 slots, 1,200,000 total PDX bytes including table, and format-specific sample
length limits. Conversion to linear PCM, resampling without antialias filtering,
MSM6258 requantization, gain/timing approximation and independent PDX reset are
reported separately from playback validation.

Resource bounds: 64 MiB ROM, 16 million unique native decoded samples and
16 million target samples. Repeated playback does not multiply the decoded
sample storage/work budget. There is no automatic whole-song mix fallback.

## Inspectable stages and validation

- .msm6295.writes/states/segments.csv and .source.json
- .msm6295.rom.NNNN.bin with block identity/hashes
- .msm6295.samples/playbacks/requests/voice_states.csv and source sample payloads
- .msm6295_bank.assets/events/parts.csv and .msm6295_projection.json
- Shared source/target manifests, bindings, reductions, omissions and assessments

Native asset/playback dumps can be emitted before target conversion, including
when a subsequent target-resource check fails. Target IDs remain linked to
native playbacks, sample aliases, ROM generations and source commands.

Original public arithmetic fixtures are in tests/fixtures/public/opm_msm6295;
regenerate with python tests/scripts/generate_msm6295_public_fixtures.py.

```sh
python scripts/msm6295_reference.py --setup --self-test
python -m unittest discover -s tests/scripts -p 'test_msm6295*.py' -v
```

The optional setup retains pinned unchanged source, wrapper and library hashes
under ignored .tools/msm6295-reference. Authored comparisons cover decoder
samples/state, native scheduler and voice availability. They are separate from
MDX/PDX compilation, user listening and physical playback-buffer fit.

Primary sources: [VGM specification](https://vgmrips.theclassicgamer.net/VGM_Specification),
[pinned MSM6295 core](https://github.com/ValleyBell/libvgm/blob/bad50c571db45b872304bdcd0603dd2214f0663e/emu/cores/okim6295.c),
[pinned OKI decoder](https://github.com/ValleyBell/libvgm/blob/bad50c571db45b872304bdcd0603dd2214f0663e/emu/cores/okiadpcm.c).
