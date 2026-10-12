# OPNA export and listening checkpoint (2026-10-12)

## Scope and evidence

Read existing top-level batch `results.csv` files, conversion diagnostics and
PCM assessments. No songs were rebuilt and no conversion behavior was changed.
All local-only source files, collection names, paths and hashes are omitted.
The user's report contains 44 distinct inputs in nine collections; one pasted
batch is repeated and is counted once. Two additional inputs have saved results
in a tenth collection. Nested diagnostic copies of batch CSVs are not counted.

## Results

| Outcome | User-reported inputs | All existing top-level results |
|---|---:|---:|
| `success` | 18 | 18 |
| `conversion_failed` | 17 | 18 |
| `pcm_projection_blocked` | 8 | 9 |
| `compilation_failed` | 1 | 1 |
| Total | 44 | 46 |

The two additional inputs account for one CH3-mode rejection and one PCM block.
These counts are file-generation outcomes, not fidelity or playback scores.
Only the first reported blocking condition is categorized; later stages may
expose additional unsupported behavior after that condition is addressed.

## Observed blockers

- **FM target projection:** 13 of the 18 conversion failures reject OPNA CH3
  special operator frequencies. The current ordinary OPNA-to-OPM mapping does
  not represent independently tuned CH3 operators. This is an explicit target
  limitation, not evidence of a VGM read failure.
- **SSG target projection:** the other five conversion failures report
  `noise/hardware EG not implemented` through the reused PSG projection.
  The message does not distinguish noise from hardware envelope, or establish
  which one is solely responsible in each song. Tone-only SSG projection remains
  the accepted scope; allocated unsupported parts stop conversion.
- **PCM eligibility:** nine inputs cannot begin an independent PDX note.
  Assessments report `controls_during_decoder_epoch`,
  `continuous_or_unresolved_source_not_transcoded` and
  `opna_decoder_epoch_not_independent`, alongside the recorded RAM1 seeded-image
  assumption. The current independent-sample path cannot safely transcode those
  continuing/control-changing decoder spans as fresh notes. `best-effort` allows
  known target losses; it does not resolve missing source/decoder evidence.
  These results do not indicate that the source VGM contains no PCM data.
- **Compiler stage:** one input reaches compilation and reports
  `Compiler exited with -11`. On the reported WSL execution, this is a process
  signal termination consistent with SIGSEGV. The precise failing component
  and cause are unisolated; neither malformed MML nor a track-buffer limit has
  been established as its cause.

## Native playback observations (user reported)

Successful exports generally play well and no animation freezes were observed.
Several songs exceed the playback track buffer. The affected inputs, byte limits
and runtime allocation were not supplied, so no per-song count or proven cause
is recorded. Large command streams are a possible future investigation, not a
measured explanation or authorization to change timing/controls/compression.
Compilation success and runtime buffer capacity remain separate checks.

## Milestone boundary

The OPNA-to-X68000 route is handed back at the current FM + tone-only SSG +
ADPCM-B/MSM6258 MDX/PDX checkpoint. The user handles commit, push and PR.
Unsupported CH3/SSG behavior, continuing PCM epochs, the compiler crash and
runtime buffer limits remain open; this review implements no fixes for them.
MUCOMVGM prepares test VGMs. vgm-conv supplies referenced mapping methods;
normal Python conversion does not execute the external vgm-conv command.
