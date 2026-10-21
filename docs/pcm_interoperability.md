# PCM interoperability and continuous DELTA playback

The primary outputs remain MML and inspectable PCM IR. Native chip evidence,
derived playback waveforms, target codec samples and packed banks are separate.

## Shared improvements from mucom88

`musical_structure.source_plan` provides the existing MDX source phrase planner
through a shared module. `ordered_timing.allocate_tick_domains` supplies the
integer-domain allocator behind the MDX timing wrapper; MDX clock arithmetic
and acceptance bounds remain MDX-specific. `opna_adpcm_playback` groups native
ADPCM-B control slices into decoder epochs and retains exact nominal nibble
positions. These modules do not import MUCOM clock, notation or bank limits.

## DELTA to MDX

The existing independent-playback route remains. Supported continuous epochs
now use `opna_adpcm_waveform` to decode once and retain position across level,
pan and Delta-N changes. Zero Delta-N pauses position without a decoder reset;
natural sample exhaustion prevents later controls from restarting that epoch.
The fixed 44.1kHz derived stereo waveform applies native pan and level once.

This is a nominal decoder/interpolation model, not YM2608 DAC, prefetch or
hardware-phase emulation. Repeat, address/memory changes and unresolved source
configurations remain rejected. Positive ordinary clocks and the supported
prescaler are required. Resource bounds remain explicit.

`pcm_waveform_mdx` reuses the SegaPCM target packaging and final-clock alignment
engine. `segapcm_pcm` remains its source-specific adapter. Source-specific loss
labels and reset assumptions are kept separate. Target mono folding, resampling,
ADPCM requantization and independent target chunk resets are reported losses.
PDX slot/byte limits and player buffers are not removed by this work.

```bash
python scripts/export_mdx.py INPUT_DIRECTORY --outdir outputs/listen/delta \
  --no-vgm --pcm-policy best-effort --no-song-loop
```

Inspect `.opna_adpcm.playback.json/.csv`, `.opna_adpcm.waveform.json`, the
waveform gate CSV, and the generated waveform-to-MSM6258 mapping/bridge files.
Native source Segments remain intact. MML/MDX/PDX generation is not proof of
native playback or acoustic equivalence. User regression/listening is separate.

## Shared reusable sample banks

Eligible MSM6258, finite Delta-T and SegaPCM assets now share the target96-slot
projection. See [shared PCM bank sources](pcm_bank_shared_sources.md) for native
reset/supply validation, finite Delta-T identities and fallback boundaries.
