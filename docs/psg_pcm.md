## PSG to MDX PCM Projection

Japanese original: [psg_pcmJ.md](psg_pcmJ.md).

`--psg-output pcm` combines the audio from the three PSG channels into a single
mono PCM stream instead of assigning PSG voices to OPM channels. SCC is still
projected to OPM in the normal way. This removes the large volume of PSG control
commands from the MDX FM tracks and bakes PSG noise and hardware envelopes into
the rendered audio. The original State, Segment, and articulation-unit
structure is retained.

### Setup and Usage

Prepare Python 3, GCC, NumPy, and the standard PCM Rust helper in WSL.

To obtain the external PSG core at the required fixed revision:

```bash
bash scripts/setup_psg_pcm.sh
```

Generate output:

```bash
python scripts/export_mdx.py INPUT_DIRECTORY --outdir outputs/listen/psg_pcm \
  --psg-output pcm --pcm-policy best-effort --compiler mmlx --no-vgm
```

You can also prepare all required tools through:

```bash
bash scripts/setup_tools.sh --with-psg-pcm
```

The default value of `--psg-output` is `opm`.

Because PCM output requires recompression, `--pcm-policy best-effort` must be
specified explicitly. `strict` stops processing and records diagnostics.

To listen to PSG alone, add `--psg-only`.

`--scc-only` and `--psg-output pcm` cannot be used together.

`--pcm-profile low`, `--pcm-profile ultra_low`, and capacity-overflow omission
via `--force` follow the same common PCM projection rules.

Playback verification on real hardware or GUI players remains required.

This mode is intended for MDX PSG/SCC input. It does not implicitly redirect
OPNA internal SSG or alternate YM2149/AY variants through this path.

Current support is limited to VGM AY type 0, a single AY instance, and flags
0 through 3. These flags are recorded as output-routing hints and rendered as
a three-channel center-mono mix.

### Source Interpretation and Target Conversion

Source playback uses the external
[emu2149](https://github.com/digital-sound-antiques/emu2149) core pinned to
commit `441f3dc295a9b82db16921461f0678b483db8304`.

The core source is stored under `.tools/emu2149/`, and hashes of the generated
wrapper and shared library are recorded in the playback JSON. No external code
is copied into this repository.

Raw VGM `0xA0` commands are processed exactly once in original order and applied
at their original 44.1 kHz sample timestamps.

All three PSG channels share a single noise LFSR and hardware envelope.
Equivalent register 13 writes are treated as a single envelope restart.
Broadcasts to the three channels in trace CSV files are not reused as playback
commands.

The synthesizer is not reset at estimated note boundaries or software-volume
run boundaries.

Initialization uses the explicit core model:

- AY volume mode 2
- quality 1
- single reset at stream start

The quality-1 rate converter and high-frequency suppression are not validated
against real hardware behavior. In particular, period-zero DAC-like behavior may
be affected by the core's high-frequency suppression, and complete AY behavior
emulation is not claimed.

I/O registers 14 and 15 are preserved, but external peripherals are not
emulated.

The original positive-voltage DAC mix is preserved in the source WAV.
A separate target audio view is generated.

Before ADPCM recompression, the signal passes through:

- a first-order 20 Hz high-pass filter
- a 63-tap symmetric Hamming-windowed sinc low-pass filter

The filtered audio is then recompressed to MSM6258 ADPCM using the common PCM
packager.

The low-pass cutoff is 0.45 × the selected output sample rate.

`--psg-gain` is applied (default 1.0 in PCM mode, valid range:
0 < gain ≤ 1).

No waveform-level or segment-level peak normalization is performed.
The original audio is not replaced by the filtered result.

This process is an approximation of bandwidth, phase, and quantization.

Known limitations include:

- finite-length FIR pre-ringing
- edge zero-padding
- omission of filter tails outside the active source span

The result is not a recreation of analog output circuitry.

The common packager later uses linear interpolation and therefore does not
guarantee complete alias suppression.

### Timing and Song Loops

Initial playback and any replay performed by the existing reader continue
without resetting PSG runtime state.

In this mode, SCC-generated OPM VGM output also uses original sample timestamps.

If multiple channel writes occur within the same MDX tick, they are reordered
when necessary so that original timestamps never move backward.

EOF and selected song-loop boundaries share the same original timestamps in both
PCM and OPM output. Loop expansion is not performed again on the OPM side.

FM and PCM data are finally projected onto the shared MDX clock.

PCM chunk boundaries are included in timing-error verification between original
and final timelines, and positive-duration PCM intervals are never collapsed.

The common packager rounds to the nearest even sample, introducing at most a
one-sample duration error at the selected PCM rate.

PCM data is stored once in the generated PDX and reused on each loop.
When playback repeats after an `L` command, the waveform remains fixed.

Infinite PSG evolution, including later LFSR states and oscillator phase
continuation, is not recomputed on every loop iteration.

The assumption of independent ADPCM predictor resets per chunk is also recorded
in diagnostics.

### Data Size and Reuse

This is not note-by-note drum-style sampling.

Even when pitch and volume are identical, different noise, oscillator, or
envelope start states produce different audio.

The initial implementation reuses only chunks whose actual ADPCM bytes are
identical.

Future work may investigate reuse via forced phase resets at note boundaries as
a separate approximation strategy.

Although MML command volume may decrease, PDX size can increase in proportion
to sounding duration.

The existing packaging limits remain in effect:

- 96 sample slots
- Current mixed-waveform chunks are bounded to 65,535 encoded bytes each,
  independently of the selected PDX format. EX-PDX does not automatically
  enlarge these implementation-defined chunks.
- 1,200,000 bytes per PDX including the table. See
  [PDX length format](pcm_pdx.md#pdx-length-format).

The same PCM profile and capacity diagnostics are used.

No guarantee is provided that output fits within MMDSP ADPCM buffers or SCC-side
track-capacity limits.

### Intermediate Outputs

- `.psg.ordered_writes.csv`
  - Original addresses, event IDs, repeat indices, and timestamps for every
    applied write.

- `.psg.playback_gates.csv`
  - Conservative union of active spans where volume or envelope selection is
    nonzero.
  - Includes DAC states with all mixer inputs disabled.
  - Distinct from perceptual silence detection.

- `.psg.native.wav`
- `.psg.playback.json`
  - Pre-filter core output together with core, initialization, and configuration
    provenance.

- `.psg_pcm_mapping.csv`
- `.psg_pcm_bridge.json`
  - Original spans, output chunks, sample IDs, profiles, and documented losses
    or errors introduced by filtering, mono mixing, ADPCM encoding, and shared
    clock projection.

- `.pcm_*` and `.pcm/`
  - Standard and shared PCM IR, bindings, typed MDX instructions, and capacity
    diagnostics.

- `projected_opm/*.source_map.csv`
- `provenance.json`
  - Mapping between sample-level serialized OPM output and final MDX timing.
  - Reported separately from existing `.opm_performance.*` rounded-tick
    diagnostics.

Analysis artifacts and intermediate results are preserved in this mode.
Listening exports retain them under `_diagnostics/`.

Successful audio generation does not constitute proof of real-hardware playback
behavior or bit-exact agreement with the original source.