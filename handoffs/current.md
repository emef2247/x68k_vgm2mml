# PSG/SSG musical units and scoped noise checkpoint (2026-10-16)

User requested steps2/3 after confirming initial OPM->OPNA on real GFII inputs.
Changes saved in x68k working tree only; no stage/commit/push/branch changes.
Public mucom files are left untouched for user's pending commit/PR.

py/psg_note_units adapts immutable PSG/SSG Segments to original-sample MSX
extract_notes. Decay/steady volume stays within runs; rises, pitch writes and
settings/shape changes infer note boundaries. opm_performance consumes note IDs
and actual allocated track. SCC stays on audibility edges. Zero-length controls
remain ordered, not false gates. Last observed PSG state carries to actual VGM
EOF only in explicit interpretation view (source_interval_extensions and
interpreted_vgmticks_end); original Segment bounds remain intact. This changes
old PSG audibility-only onset policy; phase is not preserved. No MGSDRV target
syntax/grid/envelope-bank rules were copied.

Scoped FM-model noise-only support uses one fixed positive-duration source part
on actual OPM7/C2, AL7, other operators muted. Canonical PSG F..H permutation;
OPNA FM-first reservations unchanged, selected SSG noise owner gets7. reg0F is
not channel-remapped. Tone mode restores AL/FB and all MUL/TL; finite EOF has
NE0, song-loop EOF does not. HW-EG, mode3, additional owners, missing actual7,
additive noise remain reject/force omissions. N0..30 closest nominal shift rate,
source/effective clock/rate/error auditable. N31 exclusion conservative, not a
settled hardware claim. Blank noise tone-Hz/cents: KC/KF is internal placeholder.

Verification:15 focused authored checks passed (8 new,5 performance,1 allocation,
1 force). Authored PSG/SSG CLI with --dump-passes generated MML and inspected
source music, mapping, target Key/NE, rates and bounded EOF. Both finite examples
have5 notes/rests and final Key-Off110250; MML722/571 bytes. Held-noise2pass test
retains L, no artificial boundary Key or terminal NE disable. Outputs:
outputs/diagnostics/psg_ssg_noise_20261016. No private conversions/listening.
An earlier direct TestCase import accidentally collected9 existing authored SSG
checks including one MDX/PDX helper case; helper ran successfully, and obsolete
noise rejection expectation was updated. Collection is now restricted.
Architect read-only review found no remaining blocker after zero-time owner and
placeholder-Hz fixes and accepted bounded EOF carry as source-state interpretation.

Docs: docs/psg_musical_noise.md and short README link; existing PSG/SSG/force docs
updated. Details in external field_notes/2026-10-16_psg_ssg_units_scoped_noise.md.
Next: user's real regression/listening. Do not broaden noise scope or weaken
checks for compiler capacity without evidence. Eventual source/helper sync back
to mucom/MSX is separate from applying MUCOM target syntax here.
