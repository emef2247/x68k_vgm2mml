# PCM block listening previews

SegaPCM conversion saves candidate PCM IR assets under
`<song-output>/_diagnostics/<stem>/pcm_blocks/`. These diagnostic WAV files do
not change MML, PCM bindings or PDX contents. They include candidates omitted
by `--force`, so missing instruments can be inspected independently of target
bank capacity.

To decode already-saved PCM IR without converting its VGM again:

```bash
python scripts/export_pcm_blocks.py PATH_TO_SONG_OUTPUT --stem SONG_STEM
```

The folder must contain `<stem>.pcm_samples.csv`, referenced `.adpcm` files and
`<stem>.pcm_segments.csv`. This diagnostic command produces `decoded_adpcm`
previews. Pre-ADPCM waveforms are available during a new normal conversion;
they cannot be recovered exactly from previously encoded bytes. Retained status
from saved output is used only when the current PDX ownership hash is verified.
Saved-IR exports go into `pcm_blocks/saved_ir/`, so they preserve the normal
conversion's pre-ADPCM comparisons. For a listening batch, use the diagnostic
folder containing `.pcm_samples.csv`, not the short-name publication folder
that contains only MML/MDX/PDX/TXT. The printed WAV path and TXT report identify
the normal preview directory.

## Two waveform stages

- `pre_adpcm`: finite source-derived material after target-rate resampling,
  immediately before MSM6258 encoding. Available for the reusable-bank route.
- `decoded_adpcm`: the encoded PCM IR sample decoded using the independent
  MSM6258 reset model. This represents the candidate PDX payload, including any
  padding nibble. It is not a capture from a resident PCM driver.

When the selected route is `mix`, these previews are mixed chunks rather than
recovered individual source samples. The asset-kind column makes that distinction
explicit; WAV export does not itself improve source separation.

Both stages use mono signed 16-bit WAV without per-file normalization. The
original SegaPCM stereo mix and native State/runtime evidence remain separate.
Held-control variants already include their source gain trajectory; stable ROM
views keep onset gain in playback events. Preview audio does not apply that
onset gain again. Consequently a full-level ROM-view WAV and a quiet baked
variant are not amplitude-normalized equivalents.

A sample WAV contains the entire reusable asset. A song playback can stop it
earlier, use it more than once, or play it at a different rate. Do not interpret
the WAV length as a note's scheduled gate duration. The metadata retains exact
rational rates; WAV headers require integer rates, and header rounding is
reported rather than modifying encoded sample bytes.

## Comparing candidates

The generated index associates WAVs with sample/view IDs, asset kinds, source
playbacks, encoded hashes, rates and target selection. Use the playback data to
distinguish sample reuse, onset volume, source-channel membership and omissions.
`retained` means selected for the target plan; it does not establish successful
native loading or audible playback. Before a target plan is available, selection
is unmeasured rather than inferred from an old PDX file.

Near-identical sounds may be candidates for later perceptual clustering, but
this exporter does not average, merge or replace them. Such a transformation
would require separate alignment, gain/phase, pitch, envelope and error criteria.
Exact encoded-byte deduplication remains the existing bank identity rule.

Generated preview files have an ownership manifest. Reruns replace or remove only
unchanged generated files; modified or unowned files are preserved by rejecting
the conflicting output. Use a fresh output directory when keeping edited WAVs.

PSG block selection and PSG-to-PCM reuse are separate follow-up work. This
diagnostic format can be reused there after musical sounding units, shared
noise/envelope state and oscillator continuity have been checked.

## Approximate bank sharing

Original candidate WAVs remain unchanged by similar-sample reduction. Their
manifest and playback CSV distinguish `retained`, `represented` and omitted
assets, and link original IDs to target sample IDs/volumes. Bounded comparison
WAVs are written separately to `_diagnostics/<stem>/pcm_merge/`; see
[similar-sample bank reduction](pcm_bank_reduction.md) for sequence, gain, gate
and rate assumptions.
