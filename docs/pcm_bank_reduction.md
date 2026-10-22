# Similar-sample reduction for reusable PCM banks

Status: implemented experimental target approximation. MSM6258, Delta-T and
SegaPCM target sample banks use `--pcm-bank-merge budget96` by default. This first performs
quality-bounded sharing, then substitutes nearby existing sounds as needed to
keep the complete target bank at no more than 96 samples and **1,200,000 bytes
including its 768-byte table**. Use
`--pcm-bank-merge similar` to limit sharing to the quality policy below. Use
`--pcm-bank-merge off` for the baseline. NumPy is required when comparing more
than one sample; neither SciPy nor an additional sound emulator is required.
PSG-to-PCM remains outside this option's scope; source-specific eligibility is
described in [shared PCM bank sources](pcm_bank_shared_sources.md).
Source PCM IR is unchanged.

## Boundary and objective

Apply reduction after source-linked reusable views / finite trajectory variants
have been constructed, but before target slot selection and P-W binding:

`Original PCM assets/events -> candidate groups -> representative mapping -> target capacity -> MML/PDX`

Keep every original source asset, view and playback event. Save a separate
many-to-one target mapping and explicit approximation diagnostics. A playback
that would otherwise be omitted may now reference a retained representative;
normal force-capacity rules handle groups that still cannot fit.

Reduce both the number of stored samples and their actual encoded bytes. Merely
keeping 96 large representatives does not guarantee native playback-buffer fit.
Existing mixed chunks can share a representative only as whole chunks, using
stricter waveform bounds. This stage does not extract phrases from a stream,
change the bank/mix route, or bypass a failure in preceding sample generation.

## Exact and approximate sharing

Stable finite ROM views already separate constant onset gain and pan from the
waveform. Equal encoded payloads can share one sample. Distinct delta/cursor
views and held-control variants still produce different assets unless their
encoded bytes happen to match.

Approximate sharing considers gain variants, then bounded pitch/rate and timbre similarity.
Compare pre-ADPCM material when available, rather than treating codec noise as
an instrument distinction. Retain the association to each source view even when
several views already share one encoded sample.

## Gain handling

For candidate source audio `x` and representative `r`, fit a positive scalar
`g` and measure the residual of `x - g*r`. Offset/phase alignment is a comparison
operation, not permission to move the song's note onset. Preserve attack timing.

An external onset gain must be composed with `g` exactly once. A trajectory
variant already contains its source gains; it does not receive that source
gain a second time. Constant loudness differences can become target onset gain.
Different envelope shapes cannot generally become a held PCM `@v` trajectory.

Use pre-ADPCM material to find candidates, then judge acceptance with decoded
representative ADPCM and the actual quantized gain/rate against the original
event's playback conditions. Pre-encoding similarity alone does not bound the
error after target gain quantization or a new encode.
Independently encoded scaled copies need not remain linearly related after
ADPCM decoding. Distinguish gain error from waveform residual, and use spectral,
transient and envelope checks alongside waveform distance. An error percentage
is not a perceived loudness difference or a listening-equivalence score.

Evaluate the actual quantized MXDRV/PCM8 gain profile, zero handling and headroom
for every mapped playback, not only a continuous least-squares gain. A quieter
representative cannot necessarily be amplified enough. Selecting a stronger
existing representative or a separately documented target rescaling may solve
that, but clipping and coarse volume steps remain part of the measured error.
Do not use per-note peak normalization to erase the original dynamics.

## Pitch/rate similarity

Use 100 cents as a provisional conservative interpretation of a permitted
one-step pitch difference. This is an approximation policy, not a chip fact or
an assertion that all percussion has an identifiable fundamental.

Known source-view rates and shared ROM content provide better evidence of
same-material rate variants than estimating one fundamental for noise drums.
For other material, compare bounded time-scaled waveforms, spectral shape,
attack/transient energy and decay envelopes. A similar dominant frequency alone
does not make two percussion instruments equivalent.

Ordinary MDX `F` has discrete rate settings; a sample-number note is not a
general arbitrary-pitch control. Do not promise exact restoration of each
member's pitch after sharing. Record the representative's actual playback rate
and residual pitch/rate error. If pitch cannot be established, record it as
unknown rather than claiming compliance with a cents bound. Source event
start/end times remain unchanged.

Rate changes also affect sample duration and decay. Check whether the
representative has sufficient audible tail for every mapped gate, and whether
it adds a tail where the original was already silent. Padding a stopped sample
with silence does not recreate missing decay. Keep those differences in the
comparison rather than scoring only a common short prefix.

## Group formation and representative choice

Do not form groups by transitive pairwise matches: A close to B and B close to C
does not establish A close to C. Every member must satisfy the representative's
pitch, waveform/spectral and envelope bounds. Bound group-wide pitch spread too,
so a chain of small differences cannot exceed the intended tolerance.

Prefer an existing sample representative to raw waveform averaging. Misaligned
averages can weaken attacks and cancel components. Rank valid representatives
using usage, recovered previously omitted playbacks, audible error, gain/rate
feasibility and actual stored bytes. A rare distinct instrument must not disappear
merely because frequent instruments dominate an average error score.

Use an initial high-confidence pass for scalar/same-material variants, followed
by an explicitly more approximate pass for spectral/envelope similarity.
Do not claim that a chosen numerical similarity threshold establishes perceptual
equivalence; user cluster listening remains separate evidence.

## Inspectable output and evaluation

Reduction CSV fields include original sample/view ID, representative ID,
group ID, gain ratio, effective quantized gain/error, rate ratio/cents, comparison
alignment, waveform/spectral/envelope errors, original/representative durations,
usage and selection reason. Event rows retain their original gate and source IDs.

Report candidate count -> representative count -> retained count; encoded bytes
at each step; target playbacks recovered from capacity omission; worst and
usage-weighted errors; groups rejected by gain, tail, pitch or timbre constraints.
Distinguish potentially recovered events from events actually passing the final
slot, byte and eight-voice allocation checks.
Provide representative/member A/B WAV sequences and their mapping before private
full-song regression. Export original and projected versions separately.

Authored evaluation should cover scaled copies, small rate variants, misleading
same-spectrum/different-envelope drums, insufficient tails, quiet/silent material,
gain saturation/quantization, non-transitive matches and timing preservation.
No fixture-specific reduction count is a universal guarantee of 96-slot fit.

## Default slot and PDX byte budgets

The default `budget96` prioritizes a playable-size sample inventory over exact
instrument reproduction. It operates independently of `--force`; explicit
`similar` and `off` modes preserve their previous quality/capacity behavior.
The existing `--pcm-policy strict` contract still rejects reported lossy
projection. Use `--pcm-policy best-effort` to accept defined approximations.

All candidate assets and source-linked events are constructed before selection;
they are not all packed into a PDX first. This is a stored-bank capacity policy,
not a streaming-memory or conversion-time bound.

If the quality-bounded result exceeds 96 samples **or 1,200,000 packed bytes**,
a deterministic selection considers usage and timbre coverage. Each additional
representative must fit the remaining payload budget (1,199,232 bytes). Repeated
playbacks of an already retained asset cost no additional PDX storage.
Remaining events reference
nearby selected representatives with quantized onset-volume compensation.
The final target sample set and all event references are assembled together;
unreferenced source assets and normalized omissions cannot add extra slots.
Original source PCM IR and candidate WAVs remain unchanged.

Forced replacements may exceed the ordinary pitch, envelope, tail or gain
quality bounds. They are explicitly labeled in mapping CSVs, loss evidence
and statistics. Every affected original event is compared directly against its
final representative at its original playback rate and checked target gate;
previous approximation gains/errors are not compounded through a chain.
Representative payloads are existing immutable, independently encoded assets.
This stage does not resynthesize, crop or average samples to force eligibility.

The JSON/console/results CSV distinguish the count after quality sharing from
the final budget, and report forced samples/playbacks. Merge JSON includes
`budget_byte_limit`, `budget_input_pdx_bytes`, `budget_output_pdx_bytes` and
`byte_budget_satisfied`. Console output and `pcm_bank_pdx_*` result columns show
the actual packed bytes and the 1,200,000-byte cap separately from estimates.
Actual size remains unmeasured until a current binary is verified.

Normal projection rejects an oversized final bank. With `similar` / `off`,
`--force` may retain first-use whole samples within the byte cap and omit new
ones with `pdx_byte_capacity` diagnostics; later reuse of retained samples
continues. It does not silently activate stronger approximation. All PCM routes,
including PSG PCM, are checked at final packing; oversized output is rejected
and removed. Slot/byte compliance does not guarantee eight-voice allocation,
compiler limits or runtime playback. These retain their existing diagnostics.
The option covers native MSM6258 and OPNA Delta-T target assets as well as
SegaPCM, following source-specific eligibility validation. Diagnostic WAV interruption
recovery is also separate from this change.

## Quality-bounded acceptance policy (`similar` phase) and limits

`py/pcm_bank_reduce.py` records the complete numerical policy in each JSON
report. The current implementation chooses existing, generally stronger assets
first, then usage count, byte size and ID. It compares each candidate directly
to the representative; it does not optimize a global minimum bank.

The discovery fit tests up to two sample positions of alignment (also bounded
by `--normalization-ms`) and a ±100-cent rate search. Neither comparison shift
nor rate warp is applied to output. Known identical ROM-range rate evidence
is preferred; otherwise a stable spectral peak can supply an estimated pitch.
Complex/noise pitch is explicitly unknown. Multirate assets remain distinct.

Final checks use decoded assets, actual PCM8 onset gain and every distinct
projected gate/gain condition. The gate is calculated using the selected MDX
clock and boundary tick mapping, rather than source duration alone. Source
start/end times and playback rates are preserved. Explicit normalization
omissions are excluded only within the configured short-duration allowance.

Current bounds include relative gain error 0.20, envelope error 0.20, attack
error 0.22 and missing/extra tail energy 0.035. Ordinary spectral error is
bounded at 0.24. A waveform error above 0.38 requires spectral error ≤0.16,
envelope error ≤0.13 and aligned discovery waveform error ≤0.18. For sounds
no longer than one second, an explicitly approximate `spectral_envelope`
method may instead accept independent phases with spectral error ≤0.12,
envelope error ≤0.10, attack error ≤0.15 and temporal spectral error ≤0.18.
It uses an energy-ratio gain and still checks actual unshifted target audio.
It does **not** claim waveform equivalence. Existing longer chunks require
actual decoded waveform error ≤0.08 in addition to gain, envelope, attack and
tail checks. All values are experimental target policy, not chip properties.

The retained representative is never re-encoded, averaged or normalized.
In the `similar` phase, a failed gain/headroom, tail, pitch or timbre check leaves the original asset
separate; `budget96` may then make a separately reported forced replacement. The ordinary slot, byte and eight-voice limits apply afterward.
Candidate search is approximately quadratic after feature screening; full-song
conversion time and playback buffer fit are not guaranteed by public tests.

## Files and reading the results

The original `.pcm_samples.csv`, `.pcm_segments.csv`, sample payloads and
`pcm_blocks` WAVs continue to describe the original candidates. The separate
following files describe the target reduction:

- `<stem>.pcm_bank_merge.samples.csv`: original-to-representative mapping,
  comparison method, fit, pitch evidence and worst accepted errors.
- `<stem>.pcm_bank_merge.playbacks.csv`: original/target sample and volume,
  effective gains, unchanged source gate/rate and checked target gate frames.
- `<stem>.pcm_bank_merge.json`: policy, candidate/representative counts and
  bytes, rejection counts, worst and usage-weighted errors, final selection.
- `_diagnostics/<stem>/pcm_merge/`: mapping CSV, ownership manifest and up to
  24 member/representative A/B WAVs, ordered by worst accepted waveform error.

Each A/B WAV plays original decoded audio, 0.2 seconds of silence, then the
representative with its actual quantized onset gain. Each half uses the checked
MDX gate, capped at 16 seconds with an explicit flag. Header-rate rounding is
reported. These mono diagnostics do not emulate driver interpolation, pan or
a final mix. Modified/unowned diagnostic files are protected from replacement.

The console and `results.csv` show candidate → representative count/bytes,
merged playbacks, newly recovered capacity playbacks, newly omitted playbacks
and retained-playback delta. Recovery compares actual final allocation against
an original-bank projection under the same clock and options. Recovery can be
unknown when that baseline cannot be projected; a recovered count alone is
not a net gain. Inspect final bindings and projection rows for retained slots
and P–W allocation. Original WAV metadata labels an asset whose events use a
representative as `represented` rather than incorrectly calling it unbound.

## Analysis references

The current numerical investigation can use
[cross-correlation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlate.html)
for alignment and
[polyphase resampling](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html)
for bounded rate comparisons. Neither function supplies a perceptual acceptance
threshold. The distinction between single-link and complete-link grouping is
documented in [SciPy linkage](https://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.linkage.html).

See [sample-bank projection](pcm_sample_bank_design.md),
[continuation constraints](pcm_bank_continuations.md) and
[listening previews](pcm_block_previews.md).
