# PSG/SSG sounding-unit interpretation and limited noise projection

Japanese original: [psg_musical_noiseJ.md](psg_musical_noiseJ.md).

## Common sounding units

A temporary view in 44100 Hz source-sample units is built from immutable PSG / OPNA SSG Segments,
and `mml_envelopes.extract_notes`, also used on the MSX / mucom side, is applied.
Decreasing or equal software-volume values are combined into volume runs within a single sounding unit.
Volume increases, pitch writes, and setting/shape changes become inferred sounding-unit boundaries.
This is interpretation, not observed Keys; original State / Segments, timestamps,
and zero-length control sequences remain unchanged.

`psg_note_units.py` does not introduce MGSDRV note-value grids, MML, or envelope-bank limits.
Extracted note IDs are identified within each source channel and correspond to original rows with positive duration.
Zero-length pitch/shape writes carry forward into boundary decisions for the next positive-duration interval;
they do not create inferred Keys on their own.
Original zero-length controls belonging to no volume run / note also retain their order as projected writes.

If existing PSG analysis ends an interval at the last write, a view holds the last known state until actual VGM EOF.
No fictional mute or release tail is added, and the original Segment end is retained.
`source_interval_extensions` records the original end, interpreted end, original row, and reason.

On the OPM side, Key-Off → control update → Key-On is inferred at these boundaries.
This changes the previous PSG policy of treating continuous audibility as one sounding unit;
phase or perceptual agreement is not guaranteed.
SCC retains its existing audibility-edge interpretation. Structuring and note-value normalization
connect to the existing OPM processing.

Song loops use the existing two-iteration analysis and retained state. Neither loop boundaries themselves
nor EOF muting introduce re-attacks or muting within a loop.
Original pitch/volume and similar evidence indicating a sounding-unit boundary is a separate case.

## Initial noise support scope

With the default `--psg-model fm`, fixed-volume noise-only intervals (mode 2, no HW envelope)
are approximated for one source part only. The first source channel with such a positive-duration interval
is the owner for the entire song. A transient state of zero duration alone does not reserve ownership.
Multiple parts are neither combined nor dynamically assigned to the same resource.

- Standalone PSG / SCC: SCC A..E remain fixed. PSG F..H are reassigned, placing the owner on OPM7/H.
- OPNA: FM priority and retained-tail reservations remain. First select the SSG parts to retain within capacity,
  then reserve the actual OPM7 for the noise owner among them. Other parts use the remaining channels.
- Use only C2 with AL7/FB0, setting the other operators to TL 127. On returning to tone,
  restore AL/FB, all MUL/TL values, and NE to the original FM profile. Shared register 0x0F
  is not subjected to the usual channel-address replacement.
- At the end of a finite song, apply Key-Off, mute, and clear NE; retain state at the end of loop playback.
- Tone + noise (mode 3), HW envelopes, noise on another source channel, unavailable ch7,
  and noise with the additive model remain errors. With `--force`, unsupported intervals are omitted with reasons.

The nominal AY noise shift rate is `effective source clock / (16 * max(1, period))`,
and the OPM rate is `4 MHz / (32 * (32-N))`; choose N giving the closest logarithmic ratio.
For this conservative policy, N is restricted to 0..30. Do not treat the exclusion of N31 as a confirmed HW specification.
Large rate errors can occur at the range limits. This approximation reports errors;
it does not imply matching LFSR, phase, spectrum, gain, or hardware sound.
SSG uses each Segment's effective clock after prescaling.

The divider models reference [MAME AY](https://raw.githubusercontent.com/mamedev/mame/master/src/devices/sound/ay8910.cpp),
[YMFM OPM](https://raw.githubusercontent.com/mamedev/mame/master/3rdparty/ymfm/src/ymfm_opm.cpp), and
[register definitions](https://raw.githubusercontent.com/mamedev/mame/master/3rdparty/ymfm/src/ymfm_opm.h).

## Intermediate results and usage

No additional options are required. Use the normal `vgm2mml.py` / `scripts/export_mdx.py`,
adding `--dump-passes` to save details. Existing source/target CSVs remain available.

| Artifact | Contents |
|---|---|
| `<stem>.psg.music.csv` | Sounding units, rests, and volume runs in source-sample units; original row/event membership |
| `<stem>.ssg.psg.music.csv` | The same interpretation results for OPNA SSG |
| `.opm_target.csv` | Original row and inferred note ID/end; final/reference track; noise period, effective clock, N, rates, and error in cents |
| `.opm_target.json` | PSG reference-channel assignment, noise owner, and interval extensions to EOF |
| `.opm_performance.*` | Inferred attack/retrigger/release, original control/write membership |
| `.opna_channel_allocation.*` | Final channel assignment for mixed OPNA inputs (destinations replacing SSG reference tracks) |

Tone-frequency and pitch-error fields are blank in noise intervals; read the dedicated noise-rate fields.
Internal KC/KF values initialize the carrier and are not observed pitches.
Unsupported omissions also remain in the existing force list.

Validation covers source immutability, volume runs, zero-time handling, allocation conflicts, mode restoration,
retained loops, MML generation, and intermediate results using small, self-created data.
Regression checks on actual songs and hardware listening remain separate work.
