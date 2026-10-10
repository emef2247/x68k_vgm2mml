# Adjustable output timing and native listening observations

User observations in XM6TypeG/MMDSP:
- from_fm_8ms plays as before; frozen controls resolved and counters advance.
  Volume bars still do not animate.
- BOSCON now animates but remains somewhat sluggish. User export generated
  9/12: 01/02/03/04/06/07/08/09/12 succeed; 05/10/11 remain PCM blocked.
  These are user observations, not automated native validation. No new
  local_only conversions were performed by the agent.

## Why the reported block_boundary clock was still 256 us

The saved outputs/listen/opm/from_fm_8ms block_boundary normalization JSON
predates short-rest coalescing: its reason says surviving gates/rests preserved.
It rejected even multipliers 2..5 because original Off-to-On rests of 12..15
samples would collapse. That selected multiplier1 / @t255 / 256 us.
Current code coalesces such short rests while retaining ordered key commands.
An updated public block_boundary export selects multiplier41 / @t215 /
10496 us, with 34 coalesced rests (447 original samples of lost rest duration).

In MML, @tN emits the MDX Timer B setting. For the 4 MHz target used here,
period_us = 256 * (256 - N). The converter selects N using projected source
timing, surviving key/gate spans, side-effect pulses, valid loops and PCM
representability. It is not determined by pitch, octave or volume token order.
Editing only @t in an existing score changes playback speed: all durations
must be reprojected on the new clock.

## Parameter

Both entry points support --normalization-ms (default8). It changes BOTH:
1. Whole original Key-On/Key-Off gate omission threshold, before normalization.
2. Maximum absolute target boundary movement and short-rest coalescing budget.

Integer source samples are floor(44.1 * milliseconds). 4/8/16 ms correspond
to176/352/705 samples. Original State/Segment/PCM IR and PDX bytes are retained.
--no-normalize-lengths disables the policy. Values must be finite, positive
and at least one source sample. PCM eligibility still precedes any omission.
The preferred fallback multiplier scales from65 according to the integer
sample budget, capped255; musical fitting is still tried first. Larger values
therefore do not guarantee a slower clock for every song.

```sh
python scripts/export_mdx.py tests/fixtures/public/opm/from_fm \
  --outdir outputs/listen/opm/from_fm_16ms --no-vgm --normalization-ms 16
python scripts/export_mdx.py tests/fixtures/local_only/opm_oki6258/vgmrips.net/BOSCON \
  --outdir outputs/listen/BOSCON_16ms --no-vgm --pcm-policy best-effort \
  --normalization-ms 16
```

TXT reports have plain section labels, blank paragraphs, indented subfields
and wrapped prose. Requested ms/sample budget, MML @t, selected period,
omissions, coalesced rests, correction size and sampled rejected-clock reasons
are visible. Generated files and native validation remain separate claims.

## Minimal public verification

- 12 focused gate/PCM/PSG-SCC tests pass, including original threshold boundaries
  at4/8/16 ms, original mapped phase, source preservation, OFF equality,
  invalid/subsample parameters and very large finite input.
- 9 TXT tests and1 export argument forwarding test pass.
- Public block_boundary exports at8/16 ms both select10496 us (musical fit),
  max error226 samples. Public opm_pcm_rates at16 ms selects32512 us,
  max error689 samples. All3 exports succeed.
- Independent MDX parser confirms complete9/9/16-track structures and encoded
  Timer B periods matching the reports. PCM128-byte sample packing is exact.
- Outputs: outputs/listen/clock_option/ms8/, ms16/, pcm16/.
- No full regression or native listening performed; no animation fix claimed.
