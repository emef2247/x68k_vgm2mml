# Clock listening baseline failure and controlled replacement

The user reports CLOCK.mdx cannot load in XM6 TypeG / MMDSP (no song data;
file read error in the selector). All four older CLK references load but are
inaudible and show no animation. These results cannot establish a timer cause.
The old canonical MDX and four references remain unchanged; copies and host
hashes are retained under `outputs/listen/clock_failed_20261010/`, and a public
listening record is beside CLOCK.vgm. Emulator-copy hashes were not measured.

Independent `mdxinfo -H` reports Success, 9 tracks and PCM8=0 for CLOCK,
CLK8192 and previously audible/animated FMSTATE. CLK8192's voice 0 is exactly
the same 27 bytes as FMSTATE's. Native MXC and the same brace voice syntax are
used for both; there is no evidence supporting a voice-syntax adapter fix.
CLOCK's normalized carrier TL0 is different from the reference carrier TL24.
Its finite command and tone boundaries are parseable, but native load still fails.

The earlier clock experiment had additional differences from the known-good
baseline: empty PDX filename, only timed A, one voice and explicit raw Key-Off.
FMSTATE has two voices, PUBPCM.PDX reference and timed A/P. None of these
differences has been established as the cause. In particular, PDX is unused by
FMSTATE's resting P track; including it in a diagnostic is not a new requirement
that all FM-only MDX must refer to a PDX.

Replacement generator: `tests/scripts/generate_fmstate_clock_controls.py`.
Its separate `outputs/listen/clock_controls/` preserves an exact FMSTATE MML/MDX
and PUBPCM.PDX copy first. FMONLY removes only the PDX directive, checking the
compiled data area against the exact baseline. FM0256, FM2048, FM4096, FM8192
and FM16384 retain the baseline voices and FM control phrase, repeat it eight
times and scale note/rest ticks for equal physical requested timing (~6.291s).
A/P are timed to the same finite boundary. The independent comparison includes
voice bytes, note pitch, attack/release, hold, volume, pan and track termination.
These are diagnostic reference scores, not vgm2mml output or a production fix.
Latest user listening: every clock_control case is inaudible, counters advance,
and MMDSP remains responsive during playback. Animation/cessation are not
separately certified. The user ended this experiment; do not repair or
regenerate these authored patterns. Responsiveness is the positive observation,
not proof that the clock determines animation or audible playback.

Separate FM render probe: locally built vampirefrog/mdxtools `mdx2pcm` produces
nonzero 16-bit samples (peak107) for old CLOCK, CLK8192 and FMSTATE alike. Build:
`make mdx2pcm LIBS='-lsndfile -lm'`. This checks that another MDX interpreter and
YM2151 emulator can generate a signal. It does not certify MMDSP load or sound.
The renderer writes BUFFER_SIZE shorts from a BUFFER_SIZE*2 interleaved block,
discarding half of each block; its WAV length and waveform continuity are not
a clock/audio-quality oracle. Do not use these diagnostic WAVs for roundtrip
acceptance and do not repair the external renderer as part of this investigation.

No source IR, production clock, note ordering, driver or compiler was changed.
No local_only conversion was rerun. Further clock-pattern debugging is canceled.
