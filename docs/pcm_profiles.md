# PCM output capacity and sound-quality profiles

Japanese original: [pcm_profilesJ.md](pcm_profilesJ.md).

`vgm2mml.py` and `scripts/export_mdx.py` accept `--pcm-profile standard|low|ultra_low`.
The default, `standard`, retains the previous encoded bytes and rate selection. low/ultra_low reduce rates
and re-encode only on the output side; they do not overwrite the original State, Segments, or PCM IR.

```sh
python scripts/export_mdx.py INPUT --outdir outputs/pcm_ultra_low \
  --no-vgm --compiler mmlx --pcm-policy best-effort --pcm-profile ultra_low
```

These profiles can be combined with existing options such as `--force` and `--no-song-loop`.
Known sound-quality losses from low/ultra_low are also subject to `best-effort`;
these options do not unconditionally permit capacity violations or unsupported controls.

| Source route | standard | low | ultra_low |
|---|---|---|---|
| Derived waveforms from SegaPCM / continuous Delta-T | 15625 Hz (F4), packaged in chunks of up to 8 seconds | 7812.5 Hz (F2), packaged in chunks of up to 16 seconds | 3906.25 Hz (F0), packaged in chunks of up to 32 seconds |
| Independent Delta-T | Re-encode to F0..F4 close to the original rate | Re-encode to a rate close to the original within F0..F2 | Re-encode to F0 |
| Native MSM6258 | Preserve encoded bytes as before | Re-encode within F0..F2; preserve bytes if already at a standard rate at or below the limit | Re-encode to F0; preserve bytes if already at F0 |

F0..F2 correspond to 3906.25, 15625/3, and 7812.5 Hz. The encoded sample count and MDX F command
are changed to match the target rate, preserving the original pitch and duration rather than playing the data more slowly.
F0 is 4 MHz / 1024; F2 is 8 MHz / 1024. The actual clock and divider stored in the profile
are also reflected in the derived PCM IR / bridge, keeping the rate and F command consistent.
Rounding to an even sample count (minimum 2), boundary correction to the shared MDX clock,
and encoding errors are reported in diagnostics.
Final clock alignment of derived waveforms also re-encodes at the selected profile's rate.
As before, exact agreement between the natural end of an independent sample and its gate time is a separate issue.

## Effects and limitations

Converting from 15.6 kHz to 7.8 kHz approximately halves the audio data for the same duration.
ultra_low at 3.9 kHz reduces it to approximately one quarter of standard.
Long derived waveforms can be packaged into fewer samples, which can also help with the 96-slot limit.
However, silence, original sounding intervals, and song-loop boundaries are preserved,
so the slot count is not halved for every input. Byte-identical deduplication, rounding,
and omissions under force also affect the result. MSM or Delta-T already at low rates may see no reduction.

The maximum audio payload of low's 16-second chunks and ultra_low's 32-second chunks is comparable
to standard's 8-second chunks (approximately 62500 bytes).
The goal is to reduce total bank capacity usage / sample count, not the maximum buffer requirement of an individual sample.
Independent Delta-T / native MSM use a separate route from this chunking process;
even after rate reduction, samples exceeding the validated sample-capacity range remain subject to rejection / force omission.
There is no guarantee that the result fits a player's PCM buffer limit or memory layout.
The PDX limits of 96 slots and the currently validated range of 65535 bytes/sample are unchanged.

High-frequency content in the original PCM is lost. Existing linear interpolation has no dedicated
anti-aliasing filter, so aliasing is also possible. ADPCM re-encoding errors, 10-bit output,
and the assumption of an independent predictor at each packaging boundary remain.
Compare sound quality and listening results using actual data.

Source guards for MSM6258 resets, supply cadence, unsupported modes, and similar conditions remain in place.
low/ultra_low do not resolve unknown decoder state or damaged input. When already at a low rate and unchanged,
no re-encoding loss is invented; losses with source timestamps are recorded only for playbacks actually converted.

## Intermediate results

- Native MSM `.pcm_*` outputs and original SegaPCM / Delta-T IR are retained.
- Derived native MSM data is separated into `.pcm_low.pcm_*` / `.pcm_ultra_low.pcm_*`.
  `.pcm_profile.json` / `.pcm_profile.mapping.csv` save original/output rates, byte counts, IDs, timestamps, errors, and re-encoding counts.
- Derived waveform `.*_pcm_bridge.json` / mappings save the profile, exact fractional rate, F number,
  maximum chunk duration in seconds, and output byte count. For independent Delta-T, also see `.opna_pcm_bridge.json`.
- `pcm_profile` / `pcm_payload_bytes` in `.pcm.timing.json` record the final adopted result.
  PDX header size and audio payload size are distinguished. TXT output also displays the selected profile.
- `pcm_options` in the normal CLI's `.conversion.json` records the requested profile and its applicability.

Profiles with the same names are also implemented for MSM6258 / SegaPCM on the mucom88 side,
but their target is a YM2608 ADPCM-B bank. The actual rate is calculated from integer Delta-N and reflected in MUC,
with 32-slot, 256 KiB payload, and alignment constraints applied. Do not confuse these with PDX constraints.
mucom88's native OPNA ADPCM-B follows a separate route preserving original bytes/rates and is outside this change's scope.

## Batch conversion waiting time

The default timeout in `scripts/export_mdx.py` is 600 seconds per input, per stage.
An explicit `--timeout` takes precedence. This value does not specify a playback-duration or PCM-capacity limit.
Rate reduction does not reduce the amount of native waveform analysis itself,
so processing time is not guaranteed to fall to one quarter.
