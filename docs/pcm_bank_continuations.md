# Reusable PCM banks with continuations and source loops

Status: finite sounding parts and onset-volume correction are implemented.
Actual internal sample-loop bodies, localized bank/mix combinations and PSG
bank extraction remain proposals. See [PCM sample banks](pcm_sample_bank_design.md)
for the current route selection. Native source State and Segments are unchanged.

`py/segapcm_bank_parts.py` observes the existing native renderer at effective
frames. It omits leading zero-gain material while the source cursor advances,
groups low/high address writes into effective seeks, and keeps held gain/rate
changes inside one part. Stable parts use complete ROM/suffix views; finite
control trajectories use separately labeled, content-addressed variants. Seek
boundaries share one rounded source tick. No live held PCM control is assumed.
Per-voice capture is bounded at 16 million frames and unique variant payload at
2 million bytes; exceeding either limit explicitly falls back for the whole
source in `auto` mode. Those are tool resource limits, not chip specifications.

Onset gain now uses the inspected inverse tables below. Preview WAVs before and
after ADPCM encoding include all candidate assets, including capacity omissions;
see [PCM block previews](pcm_block_previews.md).

## First correct the target control model

The former linear source-gain-to-MDX-volume mapping was not a valid general
PCM8 amplitude mapping. In the inspected MXDRV2.06+17 Rel.X5-S,
raw direct-volume bytes become attenuation indices. Indices 43 and above clear
pan, rather than providing more quiet linear amplitude levels. MXDRV then uses
its PCMVolumeTable to select a PCM8 level. The referenced X68Sound implementation
has a nonlinear 16-entry gain table, whose lowest entry is nonzero.

The implemented onset profile follows these rules:

- Map source onset gain through an explicit target compatibility profile and
  inverse gain/attenuation tables. Keep desired/effective gain and error in CSV.
- Represent true silence separately and restore the next attack's routing.
- Keep a common asset scale, rather than normalizing each note separately.
- Distinguish code-profile agreement from measured native-driver amplitude.

Ordinary PCM volume, pan and frequency commands in that MXDRV reference update
track state, but do not provide general live changes to an already-held PCM
note. Do not assume that adding `@v`/`p`/`F` between held note chunks reproduces
the source trajectory. Extended direct-driver operations need a separate ABI,
compiler and runtime proof; they are not an implicit first-version solution.

## Derive sounding parts without inventing attacks

An enable-to-stop runtime gate may contain muted initialization, several address
reprogramming sequences, rate changes and changes of gain. Derive source-linked
parts with effective cursor/fraction, ROM generation/bank, rate, gain, loop state
and termination. Label each boundary as continuation, explicit reposition/start,
or unresolved. A split is not automatically a new PDX note.

Apply writes in source order at their effective native frames. In particular,
low-address/high-address/control writes completed before one native frame must
not create artificial intervening sound. Preserve the intermediate observations.
During muted intervals continue advancing cursor, loop and decoder/oscillator
state; omit only target audio proved silent throughout the omitted interval.

Judge loop eligibility from the path actually traversed. A loop-enabled setting
does not require loop material when playback stops before reaching its loop
boundary. Keep the setting as evidence without rejecting an otherwise finite
audible path.

## Finite samples and mid-sample starts

Reuse finite unsigned-ROM views at their required rate, keeping gain/routing and
gate duration separate where target capability allows. A mid-sample entry keeps
the exact effective address/fraction. It can use an independently encoded suffix
view, cached by actual source view and conversion identity, rather than a fresh
whole-song chunk for every use.

Future improvement: select each asset's target rate within the chosen quality profile, with explicit
resampling and duration/pitch error accounting. Merely changing MDX `F` changes
playback speed and is not rate conversion. Avoid unnecessary upsampling of low
source-rate material, but do not infer an acceptable bandwidth loss or a final
bank size from source address ranges alone.

Do not splice into the middle of existing ADPCM bytes and assume the initial
predictor/step/nibble state is correct. SegaPCM unsigned8 source material permits
independent transcoding of a suffix; native MSM6258 source needs its own retained
decoder evidence. A loop-start address is not automatically proof of an original
instrument's canonical start.

For held controls unavailable in ordinary target commands, consider reusable
gain/envelope/rate variants with explicit content identities and size accounting.
Do not create one unique full-duration waveform per control slice. A control
change does not authorize an artificial audible retrigger. Unresolved cases keep
their source evidence and an explicit localized-render or blocked decision.

## Actual internal sample loops

Keep source-song `L` and a source sample's internal loop separate. The current
PDX binding stores byte position/length, not native loop-start/end metadata.

For a genuinely traversed internal loop, evaluate:

1. an initial prefix up to the first source loop seam;
2. reusable body assets containing multiple complete source loop traversals;
3. a source-phase-specific prefix/suffix for partial entry or exit.

Multiple-cycle bodies avoid scheduling very short source periods as individual
MDX notes. Derive each asset from fixed source/rate/profile conditions; final
event-clock alignment must not stretch the waveform separately for each use.
Do not tie an exhausted sample and assume it restarts. An MDX repeat of notes
restarts the target decoder and is an approximation to a continuously looping
source, even when its bytes and duration appear periodic.

Evaluate seam/reset discontinuity, pitch/rate error, accumulated phase drift
over repeated bodies and final stop position. One boundary's timing tolerance
does not establish a long loop's accuracy. If those criteria cannot be met,
render only the affected source part or keep an explicit limitation.

## Common target and bounded fallback

Reuse existing P-W allocation, immutable bindings, capacity selection, typed
commands, MML rendering and PDX packing for every source-specific adapter.
Do not build a second source-independent parser or replace proven native MSM
sample extraction. Adopt the smallest common sample/view/playback extensions
supported by concrete source cases.

A localized render must have explicit source-channel/time membership disjoint
from banked material. Never add a whole-source mix on top of banked voices.
The combined banked and rendered parts share the eight-voice budget. Measure
stored bytes and actual saved assets; a fallback label alone is not progress.

## Feedback to PSG PCM

PSG can use the same target bank/event machinery, but it has no source ROM from
which to extract an instrument. First establish channel-resolved continuous
audio while preserving common noise, hardware-envelope, oscillator phase and
filter state. Reading a core's final channel output after an internally averaged
quality-mode call does not necessarily reconstruct that call's channel audio.

Then bank repeatable finite tone/phrase material when initial state and evolution
are equivalent. Preserve existing musical units and volume trajectories as
evidence. Do not reset a PSG core at inferred note boundaries or promise exact
reuse of evolving noise/EG. Software-volume changes need the same held-control
capability handling as other sources, not assumed live `@v` behavior.

## Public acceptance before private regression

- Onset gain mapping includes silence, quiet and full levels without accidental
  target mute; gain/pan are restored after silent spans.
- Muted initialization advances state and does not reject a later finite sound.
- Native-frame low/high/control ordering, explicit reposition and uninterrupted
  continuation remain distinct and inspectable.
- Finite full/suffix views share assets across different gate durations; known
  decoder-state differences prevent invalid ADPCM substring reuse.
- Loop-enabled-but-unreached samples remain finite; traversed loops preserve
  prefix/body/tail relationships and report multi-repeat drift/reset errors.
- Combined bank/render ownership neither duplicates nor drops source audio,
  respects P-W allocation and keeps one binding for MML and PDX.
- PSG phase, noise/EG and quality-mode channel extraction have independent
  authored expectations before PSG bank reuse is enabled.

Report source-model checks, immutable asset bytes, compiled MDX constraints and
user native listening separately. No fixed PDX-size threshold guarantees that
all playback environments will load a bank.

## Implementation references

- [MXDRV2.06+17 Rel.X5-S source](https://github.com/vampirefrog/x68kd11s/blob/master/sound/mxdrv/2.06%2B17_Rel.X5-S/mxdrv17.s),
  `L000c66`, `SetPCMVolume`, `PCMVolumeTable`, volume/pan/frequency commands.
- [X68Sound PCM8 mode](https://github.com/rururutan/X68Sound/blob/master/X68Sound/pcm8.h)
  and [PCM8 gain table](https://github.com/rururutan/X68Sound/blob/master/X68Sound/global.h).
- [PSG PCM source/runtime boundary](psg_pcm.md) and
  [native PCM evidence](pcm_source_and_target.md).
