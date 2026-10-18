# Experimental SCC to FM voice fitting

The offline fitter compares fixed SCC waveforms against a real YM2151
emulator. It does not parse VGM, alter source Segments or claim complete SCC
reproduction. The canonical frontend can invoke the fitter automatically when its FM bank is
omitted. Production projection consumes the saved voice bank at the
Target boundary; source software envelopes must remain separate carrier-level
trajectories.

In WSL, install the external core with `bash scripts/setup_tools.sh
--with-mdxtools`, and provide GCC and NumPy. No emulator source is copied into the
repository. The authored wrapper is compiled under `.tools/scc-fm-fit/`;
`voices.json` records hashes of the external C/header files and wrapper.

```sh
python scripts/fit_scc_fm.py waveforms.json --outdir outputs/scc_fit --audio
```

Multiple positional input files may be combined into one content-deduplicated bank.
Input is a JSON array of 32 signed/unsigned bytes, a hexadecimal waveform string,
a list of either, or an existing SCC waveform CSV with `waveform_hex`. Each saved
entry is keyed by SHA-256 of the complete 32-byte waveform, rather than a local
wave ID. The bank schema is `scc-fm-fit-v1`, chip `YM2151`; operator arrays follow
register-bank order M1, M2, C1, C2. Reference gain defaults to 0.125. Carrier TLs
are fitted at source volume15; later gain/volume changes must affect carriers
only, preserving modulator TLs and FM indices. DT1/DT2, LFO and AM are zero;
AR31, D1R/D2R0 provide constant steady-state voices.

The five comparisons are four dominant representable harmonics (`additive`),
eight dominant harmonics on two channels (`additive8`), four lower and four
upper harmonics (`additive8-lowhigh`), FM plus additive, and two FM channels.
Harmonics1..15 use integer MUL values; the Nyquist harmonic16 is omitted.
The FM coarse grid has algorithms0/4/5/6, first-operator MUL1/2/3/5/7,
feedback0/3 and modulator TL24/40/56. The best three have local +/-8 TL refinement.
Two-part candidates are evaluated through actual simultaneous chip rendering,
not independent spectrum subtraction or assumed phase cancellation. Selection
is bounded and heuristic: it does not prove a global optimum, nor guarantee
that FM beats additive for a waveform. Silence on the second part is permitted.

The probe warms up for at least16 periods and measures at least32 periods, using
48kHz audio. A TL0 sine carrier calibrates the emulator output scale. The source
reference is zero-mean signed SCC table data, held for each of32 positions at
the quantized target fundamental, at the same gain and sample rate. This is a
staircase reference, not an independent SCC hardware/emulator recording.
The normalized squared difference of Hann-window FFT magnitudes includes all
bins, penalizing missing and unwanted components plus amplitude error. Phases
are not fitted. Output WAVs use a common fixed scale; they are not individually
normalized. `metrics.csv` preserves every selected model's measured error.

The same fitted parameters are additionally measured at half, reference and
double the requested fundamental, without reoptimization. Repeat
`--check-frequency 220 --check-frequency 880` to select other check pitches.
Each candidate's `pitch_checks` and metrics CSV record requested/actual quantized
frequency, KC/KF, normalized spectral error, RMS, reference gain and RMS gain
ratio. These are limited transfer measurements against the same ideal32-step
reference, not proof of accuracy throughout the musical range.

Pitch rounding is recorded by the bank's reference frequency. Other unmeasured
notes, aliasing near Nyquist, feedback stability, attacks, hardware DAC/filter
behavior, phase during waveform changes and actual listening are unverified.
The bank targets YM2151; applying these operator parameters to YM2608 is a
separate approximation and is not established by these measurements.
Caches include waveform bytes, source hashes, clock, gain, actual reference
frequency, probe settings and search version. Native source evidence is never
replaced by cache data.

Production selection, channel budgets, source software-envelope interpretation and
CLI examples are documented in [SCC target projection](scc_fm_projection.md).
