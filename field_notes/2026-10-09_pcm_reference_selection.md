# User-provided PCM reference selection after local cleanup

The user reduced `tests/fixtures/local_only/opm_oki6258/mdx_pdx/` to eight PDX
files with associated MDX material. The separate FM/reference tree moved under
`tests/fixtures/local_only/opm/mdx/`; that tree is outside this PCM trial.
Do not move or modify private fixtures, stage them, or alter conversion to
recover structure from original MML/MDX.

## Current collection

| Group | MDX files | Original MML found | Static layout |
|---|---:|---|---|
| `FinalFantasy/FF4/MACHAN/FF4SIREN` | 1 | Yes | 9 tracks, standard PCM1 candidate |
| `Namco/System_FA/SFA02`, `SFA02_`, `SFA11` | 3 | None beside the MDX | 16 tracks, PCM8 enabled |
| `Taito/RayForce/RAY2C` | 1 | Yes | 16 tracks, PCM8 enabled |
| `Taito/RayForce/RAYFOR0`, `RAYFOR1` | 2 | None beside the MDX | 16 tracks, shared `RAYFOR.PDX` |
| `Taito/RayForce/RF2` | 1 | None beside the MDX | 16 tracks, PCM8 enabled |
| `Taito/RayForce/CHAMA/RAY01C` through `RAY07C` | 7 | No original MML; PDL present | 16 tracks, shared `RAY01C.PDX` |

All 15 original MDX headers resolve their declared PDX filename locally,
including case differences and shared-bank filenames. The user's description
of complete MML sets is broader than the original MML files currently present:
only FF4SIREN and RAY2C have same-stem `.MML` files in this selected tree.
PDL is sample-container construction material, not music-track MML.

Use FF4SIREN first for standard PCM1 static C0 evidence. The other 14 are useful
extension references, but do not certify standard PCM1 semantics. PCM8 and
multi-bank references need their own execution profile; a bank-0-only sample
audit must not call a note invalid merely because its slot is in another bank.

## Static evidence obtained

The original FF4SIREN MDX is 1835 bytes and declares a 2221-byte PDX. Bank 0 has
one populated slot, number 1, with 1453 encoded bytes. Its P track is 45 bytes
and contains 23 encoded commands, including F4 and 15 encoded sample-note
commands with durations 6, 12 or 24 MDX ticks. Each static sample reference
resolves. These are encoded facts, not expanded repeat counts or measured
PCM consumption. Original MML also uses the P track and F4.

A read-only C inspector linked to pinned `vampirefrog/mdxtools` revision
`9c8539fec2757fcf7c85d1986171b50ebe2ef1e5` preserved track boundaries, original
file offsets, opcodes and operands. It explicitly consumes F1/00 as two bytes,
matching that upstream driver's finite termination branch. All 15 selected
files produced command-boundary dumps. This is independent of the converter's
source analyzer and soundlog player, but does not execute MDX commands or
establish native IOCS/DMA semantics.

The normal mdx2mml/mdxdump preparation tools exited zero for all 15 files, but
their resulting MML failed strict UTF-8 decoding in the title area, so all
remain `needs_review` under the existing reference-preparation audit. Preserve
the original stdout and failure reasons. Do not turn this into a successful
decompilation or rewrite source titles to hide the problem. Static binary
inspection does not depend on the malformed converted title text.

Ignored evidence:

- `outputs/pcm_stream_2026-10-09/reference_selected/`: original-tool stdout,
  stderr, hashes, decompiled text and per-track encoded-command CSVs.
- `outputs/pcm_stream_2026-10-09/selected_audit.json`: sizes, layout, PDX
  resolution, hashes and original-MML availability.
- `outputs/pcm_stream_2026-10-09/selected_commands.json`: encoded PCM sample
  references and F values, with explicit static-only scope.
- `outputs/pcm_stream_2026-10-09/reference/encoded_commands.c`: local read-only
  inspector; upstream source is outside tracked production code.

The earlier `reference_mdx_audit.json` and `reference_mdx_bosconian/` inventory
predate the user's cleanup and are historical only. The former Bosconian set
was not proven to match the X68000 BOSCON VGM performance; one matching sample
alone was insufficient pairing evidence. Do not reuse it as a current oracle.

## How this helps the current implementation

The samples confirm a small standard PCM1 reference can provide direct C0
command/sample-binding evidence without requiring PCM MML compilation. They
also expose the need to classify standard versus PCM8 sources before selecting
an independent reference. Do not use PCM8 references to infer standard PCM1
hold, pan, reset or rate behavior.

No selected MDX has yet been certified as the original performance behind
BOSCON01. Its generated MDX capacity issue therefore remains separate; matching
the size/structure of a different reference is not a conversion criterion.
Full C/A/B playback comparison and native runtime validation remain unimplemented.
The later BOSCON06 end-noise report resumed static reference/stop-path research;
see field_notes/2026-10-09_pcm_pdx_end_review.md. MMDSP display work remains paused,
and no native cessation or runtime equivalence is certified.
