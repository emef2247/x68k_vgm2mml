# OPNA FM to X68000 and Delta-T PCM IR (2026-10-12)

User requests a quick existing-path implementation, no commit, with conversion
and listening verification performed by the user. The scope later expanded
from FM-only MDX MML to include OPNA ADPCM-B/MSM6258 PCM IR.

`conversion_config` inventories actual YM2608 writes and selects
`opna-fm-to-opm`. Existing explicit silent AY/SCC compatibility initialization
rules apply to OPNA FM sources too; additional audible chips are not omitted.
`opna_opm` consumes immutable native Segments, maps operator banks, key masks,
channels0..2/4..6, RL/FB/algorithm/PMS/AMS using vgm-conv's ISC reference
revision780a20ed505e23eb21aa9c6ce3f349029718b5a0. Committed11-bit FNUM uses
the existing nominal OPM pitch helper at4MHz, not the upstream9-bit cache.
Raw writes/latches remain source evidence. Range clamps have explicit counts.

The thin target VGM serializer retains original sample times and same-sample
event order. It marks the reader-expanded second traversal by both sample and
event ID. Existing `opm_conversion.convert(replayed_song_loop=True)` then
handles OPM analysis, MDX clock projection/normalization and MML formatting.
The six-channel output-enable bit maps to OPM RL muting without restarting
keys/envelopes. CH3 special mode, CSM, unknown effects and DAC streams reject;
SSG/rhythm/ADPCM, SSG-EG and approximate LFO/timer behavior are diagnosed.
`--dump-passes` separates native CSVs from `projected_opm/` VGM/mapping/passes.
Normal output also contains `<stem>.opna-opm.json`.

`opna_adpcm` independently retains memory blocks, register-state controls,
decoder epochs and continuation slices. Bounded external ROM and read-only
8-bit RAM image spans may transcode independently. The RAM image assumption,
nominal natural end, reset initialization and omitted prefetch/interpolation
are explicit. CPU uploads, repeat/continuation/wrap/unresolved memory effects
remain ineligible for target transcoding. Source encoded bytes are immutable.
Target PCM IR decodes nominal Yamaha ADPCM-B, resamples to existing MDX
F0..F4 rates, bakes level and independently encodes10-bit low-nibble-first
MSM6258 ADPCM. Codec/rate/volume/quantization/padding diagnostics and hashes
are retained. This does not yet bind a PCM P track, generate PDX or prove
acoustic equivalence. Native and target manifests identify current files,
including empty PCM runs.

Checks performed: syntax parsing/imports and one source inventory routing
inspection only. No conversion, playback, private fixture or broad regression
checks were run for this implementation, as requested. Focused FM/PCM tests
are supplied for the user's next verification. Earlier29-test FM MUCOMVGM
results apply to the previous milestone, not validation of this target change.

Static architect review corrected equal-sample loop placement, output-gate
key restarts and stale owned output handling. PCM review added rejection of
nondefault/shared prescaler epochs and persistent unresolved recording/RAM
mutation history, preventing stale seeded memory from becoming eligible after
register clearing. Keep AGENTS.mucom.md and local MUCOM song archives outside
this scoped registration; their untracked presence predates this change.
