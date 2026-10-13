# SegaPCM native source checkpoint

The shared VGM reader captures C0 writes and type80 ROM blocks on the same
44100 Hz sample clock as OPM. Loop replay carries state and retains original
command IDs, occurrence IDs, command addresses and iteration/timing provenance.
No MDX clock normalization is applied to native evidence.

The collector emits immutable raw records, channel State snapshots and
write-observed control/configuration Segments for sixteen channels per instance.
Repeated writes and zero-duration observations remain inspectable. Enabled
configuration is not proof of an audible gate. Programmed address bytes remain
unknown until written; runtime address advancement and natural sample completion
are not emulated. EOF closes observations without a synthetic disable.

## Retained artifacts

- `<stem>_trace.segapcm_regs.csv`: original C0 operands, RAM aliases, role and provenance.
- `<stem>_trace.segapcm.csv`: state after each modeled write or ROM update.
- `<stem>.segapcm.segments.csv`: channel configuration intervals and endpoint IDs.
- `<stem>.segapcm.rom_blocks.csv`: ordered ROM size/start/header facts and payload paths.
- `<stem>.segapcm.rom_blocks/blockNNNN.bin`: verbatim sparse payload per block.
- `<stem>.segapcm.analysis.json`: current artifact list, counts, declarations, issues and limits.
- OPM State/Segment, shared timing and loop CSVs accompany this source route.

Only manifest `current_files` belong to the current analysis. Older unlisted
payloads in a reused output directory are not part of the current ROM history.
ROM blocks preserve overlaps, repeated loads and changing sizes chronologically;
each update changes the ROM generation in affected channel intervals. There is
no allocation proportional to a declared ROM size. A short ROM header is kept
opaque and diagnosed; physically truncated VGM framing is rejected.

Register interpretation follows the sixteen-channel VGMPlay SegaPCM model:
low-page channel offsets2/3 set volume,4/5 loop address,6 end page,7 delta;
high-page84/85 program address and86 control. Bit0 disables; bit1 disables loop.
Untouched bytes are nullable. Unmodeled RAM writes remain in the raw CSV.
Nominal byte advance rate, when declarations permit it, is clock * delta /32768;
it is not measured playback frequency. Bank parameters retain raw interface
values; a zero mask's compatibility default is explicitly labeled. Undeclared
or unmodeled second-instance/clock details do not manufacture a known rate.

## Target boundary

Without `--fm-only`, mixed OPM/SegaPCM returns `source_analyzed` and no MML.
`--fm-only` explicitly authorizes an OPM-only diagnostic target. Full source
validation still runs first. Shared waits and loops remain unchanged, SegaPCM
evidence is always saved, and its control slices do not constrain FM target
normalization. Existing native OPM pitch, musical structure, loop and clock
projection generate the MML; the usual exporter compiles it to MDX. No SegaPCM
PDX, transcoding, PCM channel binding or acoustic equivalence is claimed.

The exporter stops before compilation for an analysis-only result. An explicit
FM-only export reports the SegaPCM omission in conversion JSON and TXT.
MGS and other unsupported source combinations remain rejected.

## References

Hardware/VGM facts were checked against the
[VGM specification](https://github.com/vgmrips/vgmplay-legacy/blob/master/VGMPlay/vgmspec171.txt),
[VGMPlay command dispatch](https://github.com/vgmrips/vgmplay-legacy/blob/master/VGMPlay/VGMPlay.c)
and [SegaPCM model](https://github.com/vgmrips/vgmplay-legacy/blob/master/VGMPlay/chips/segapcm.c).
This source checkpoint reconstructs write-observed configuration independently;
it does not embed that emulator or implement its runtime audio behavior.
