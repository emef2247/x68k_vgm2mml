## SCC Timbre Projection to OPM

Japanese original: [scc_fm_projectionJ.md](scc_fm_projectionJ.md).

The current target is the X68000 MDX path. Several projection models are
available, including the default FM-plus-additive (`fm-additive`) mode, with
optional allocation of up to two OPM channels per SCC channel.

Observed SCC State, Segment data, and 32-byte waveforms are preserved without
modification.

### Ready-to-Use Two-Channel Additive Synthesis

```bash
python vgm2mml.py input.vgm --outdir outputs/scc_additive8 \
  --scc-model additive8 --dump-passes

python scripts/export_mdx.py input.vgm --outdir outputs/listen/scc_additive8 \
  --scc-model additive8 --compiler mmlx --no-vgm
```

`additive` selects the four strongest harmonic components from DFT harmonics
1 through 15.

`additive8` assigns the next four strongest components to an auxiliary channel.
Both models use OPM algorithm AL7.

No per-waveform loudness normalization is applied. Output level is determined
by the common `--scc-gain` value (default: `0.125`) multiplied by the SCC
volume level.

DC offset, the 16th harmonic, and arbitrary phase relationships are not
reproduced.

Reported retained DFT energy is diagnostic information only. It must not be
interpreted as a perceptual quality score or evidence of hardware waveform
equivalence.

### Articulation, Software Envelopes, and Structural Representation

`py/scc_note_units.py` uses the shared MSX-side
`mml_envelopes.extract_notes(..., 'scc')` interpretation at original sample
timestamps.

Constant or decreasing software volume across a continuous region with
unchanged settings is represented as a single run within one articulation unit.

The following events begin a new articulation unit:

- volume increases
- pitch writes
- waveform-ID changes
- enable/disable changes
- other SCC configuration changes

Zero-duration pitch writes are retained and applied at the boundary of the next
positive-duration interval.

This should not be interpreted as SCC possessing native OPM Key-On events.

The final observed state is extended only when no subsequent state exists, and
only until the explicit VGM end position.

Pre-extension and post-extension timing information is recorded in
`opm_target.json` under `scc_source_interval_extensions`.

Original Segment lengths, volumes, and waveform contents are never rewritten.

Both OPM channels reference the same articulation units and volume runs.

For FM-based projections, software volume changes affect **carrier TL only**.
Modulator TL values and modulation depth remain unchanged.

Oscillator phase at Key boundaries and waveform transitions does not match SCC
phase behavior.

MGSDRV-specific `@e` notation and envelope-bank limitations are not carried
into MDX output.

This projection does not eliminate OPM TL-range limitations (`0..127`) nor
saturation caused by summing multiple channels.

Articulation-unit repetition structure is stored in audit CSV output through the
shared `source_plan` / `SourceLoopPlan` mechanism.

Final MML is generated through:

```text
Explicit OPM performance plan
  -> Generated OPM VGM
  -> Normal OPM musical/structural pipeline
```

This path uses the shared MSX loop-analysis implementation.

MSX MML text is not reused directly, nor are note/tie structures generated
per Segment.

Audit-time articulation structure and final target-side structure should be
considered distinct concepts.

Existing `--normalization-ms` handling and VGM song-loop processing also apply
to this projection.

Note-length omission and timing correction occur only on the target side.
Original articulation units and Segments are preserved.

### Channel Budget

OPM provides eight channels.

The following channels are reserved first:

- SCC primary channels A through E
- PSG fixed assignments F through H
  (reordered within that range when noise allocation is active)

Reservations cover the entire input span, including loop re-analysis.

Channels are not borrowed temporarily during silent sections.

Non-oscillating SCC channels that emit initialization commands still consume
reserved channels.

Auxiliary-channel priority is determined by:

```text
improvement × source_duration × (source_volume / 15)^2
```

For `additive8`, improvement is measured as additional retained DFT energy.

For FM-based models, improvement is measured as reduction in pitch-reference
measurement error.

All five SCC channels cannot necessarily be expanded uniformly to two OPM
channels each.

If no channel budget remains, the affected SCC channel falls back to the
existing one-channel additive model.

Primary SCC channels and PSG channels are never removed to improve quality.

### Using an FM Voice Bank

If `--scc-voice-bank` is omitted for FM models, suitable FM voices are
automatically searched from analyzed articulation waveforms.

Generated files:

- `<stem>.scc.waveforms.csv`
- `<stem>.scc.voice_bank.json`

are saved alongside the MML output.

Search results are cached under:

```text
.tools/scc-fm-fit/cache/
```

Cached fits are reused when waveform, clock, gain, core, and search-version
parameters match.

Pitch-transfer measurements are also recorded.

The initial fitting process requires:

- GCC
- NumPy
- an external YM2151 core

If dependencies are missing, setup instructions are displayed and processing
stops.

The traditional explicit-bank workflow remains available:

```bash
python vgm2mml.py input.vgm --outdir outputs/scc_source --dump-passes

python scripts/fit_scc_fm.py \
  outputs/scc_source/input.scc.waveforms.csv \
  --outdir outputs/scc_fit --audio

python vgm2mml.py input.vgm --outdir outputs/scc_fm \
  --scc-model fm-additive \
  --scc-voice-bank outputs/scc_fit/voices.json \
  --dump-passes

python scripts/export_mdx.py input.vgm --outdir outputs/listen/scc_fm \
  --scc-model fm-additive \
  --scc-voice-bank outputs/scc_fit/voices.json \
  --compiler mmlx --no-vgm
```

`fm-additive` chooses FM + additive candidates.

`fm-fm` chooses FM + FM candidates.

Multiple waveform CSV files can be supplied to the fitting process. Duplicate
waveform content is removed and combined into a single voice bank.

Processing stops when required waveform/model combinations are missing from the
specified bank.

For details regarding the fitting system, external YM2151 core, GCC, NumPy,
search space, and measurement procedures, see
[scc_fm_fit.md](scc_fm_fit.md).

These requirements do not apply to ordinary `additive8` output.

A candidate is accepted only when it yields lower measured error than additive
synthesis alone at the reference pitch.

Otherwise the projection falls back to one-channel additive synthesis.

Candidates whose auxiliary part is silent consume no additional channel budget.

Candidates requiring two audible parts revert to one-channel additive synthesis
if an auxiliary channel cannot be allocated.

Partial use of only one audible component is not performed.

Voice banks are matched using SHA-256 hashes of the full 32-byte waveform.

Validation includes:

- YM2151 / 4 MHz assumption
- reference gain and pitch
- fitting version
- core and wrapper hashes
- measurement sample rate
- measurement frame count
- carrier calibration values
- voice-parameter schema

Because local execution does not require the same installed synthesis core,
voice banks generated on another system can be reused.

Recorded provenance does not prove timbre correctness or authenticity of
external files.

Acceptance decisions are based on measurements at the reference pitch only.

`pitch_checks` records limited transfer evaluations at the documented pitches.
It does not guarantee quality across the full pitch range, during software
volume modulation, or during waveform switching.

No general assumption is made that FM is superior to additive synthesis.

Real-hardware listening evaluation remains necessary.

### Intermediate Outputs and Selection Rationale

FM and auxiliary-channel models store:

```text
<stem>.scc.voice_projection.json
```

as part of normal output.

The report includes:

- primary and reserved channels
- auxiliary-channel allocation
- waveform-specific acceptance reasons
- reference errors
- voice-bank hashes

`quality_fallback_one_lane` indicates fallback to a single channel due to
channel-budget limitations.

With `--dump-passes`, the following additional files are produced:

- `.scc.music.csv`
  - articulation units at original timestamps, waveforms, source Segment rows,
    software-volume runs, and inference provenance.

- `.scc.music.chN.structure.csv`
  - shared structure analysis of articulation units and corresponding source
    rows.

- `.opm_target.csv`
- `.opm_writes.csv`
  - physical target tracks, target lanes, voices, TL values, and source rows.

- `.opm_voices.csv`
  - additive voices or FM algorithm, feedback, MUL, TL, and carrier data.

- `.opm_performance.*`
  - inferred Key events, control writes, and linkage to source articulation
    units for each physical channel.

- `projected_opm/`
  - generated VGM and all intermediate articulation, control, structural, and
    normalization artifacts consumed by the ordinary OPM pipeline.

During listening exports, detailed JSON and CSV diagnostics are written under
the output directory's `_diagnostics/` tree.

The minimal output layout for the explicit one-channel additive model and the
legacy `opm-additive` compatibility alias remains unchanged.

Detailed configuration is also recorded in `.opm_target.json` when
`--dump-passes` is enabled.

### Application to the MUCOM Path

Implementation and validation so far target the X68000 path.

The SCC articulation-unit interpretation, software-volume-run analysis, and
voice-fitting infrastructure are reusable.

However, the MUCOM path requires:

- budgeting against OPNA's six FM channels
- timbre measurement using YM2608

Voice banks validated for YM2151 are not treated as validated YM2608 voices.

### Source-Chip Comparison Output

`--psg-only` (`--psg_only`) and `--scc-only` (`--scc_only`) are mutually
exclusive.

Raw VGM data, State and Segment information for both chips, articulation units,
and software-volume runs at original timestamps are always analyzed.

Only the chips forwarded to the target projection stage are selected.

Selected and excluded source chips are recorded in the conversion JSON.

PSG noise or hardware-envelope activity in excluded PSG data does not cause
SCC-only output to fail.

Because SCC-only mode does not reserve PSG channels, additional auxiliary SCC
channels may become available within existing allocation rules.

These options are intended exclusively for MDX PSG/SCC input workflows.

They do not apply to MGSDRV-compatible output or native OPM input paths.