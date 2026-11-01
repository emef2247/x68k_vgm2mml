# Shared PSG/SCC source-curve interpretation

The requested native routes now reuse the MSX performance and fixed-tone
continuation engine before structural planning. Adapters explicitly use 44,100 Hz
sample coordinates; the inherited MGSDRV compatibility route is unchanged.

Supported continuation combines inactive HW-reset partitions, unchanged-period
PSG release continuations, and compatible fixed-pitch rising/decaying volume
curves. Ordered zero-time pitch/mixer/HW/noise changes, silence, unknown source
time and SCC waveform changes remain protected. Native Segments are retained.

This does not import MGSDRV envelope IDs, its 32-slot bank, 60 Hz envelope holds or
MGS-specific tie compensation. Existing target pitch, channel and PCM policies
still apply. Inferred complete sounding units are not recovered source score
Key-On/Key-Off or release commands.

Original performance and projected continuation CSV/JSON use an explicit
44,100 Hz clock. Existing note/source membership and target dumps remain.

Active routes: PSG/SCC -> OPM, including the existing SSG-to-PSG adapter; PSG -> PCM packaging.

PSG PCM keeps continuous emulator rendering/filtering. Interpreted groups
nominate complete-group packaging cuts before the existing chunk limit only
when no channel group straddles the cut. Hard loop/span endings remain fixed;
without a safe candidate, existing chunking is retained. Optional input defaults
leave other waveform backends unchanged. The bridge records preferred_groups
and packaging_boundaries. This is not a new reusable per-drum PCM bank or a
promise of smaller PDX/runtime-buffer fit. Derived last-state extensions remain
separate from original vgmticks_end and are reported in projection settings.
