# Performed OPM structure and MSX processing reuse

The MDX renderer groups source-derived OPM key gates before spelling notes.
It uses the established MSX source-loop planner for inner held-note repeats
and outer note/phrase repeats. Source State, Segments, ordered writes and
PCM IR are preserved; target structure is a separate view.

## Reused and target-specific processing

| Processing | MDX route |
| --- | --- |
| Continuous-note grouping and key/retrigger boundaries | Native OPM key/operator evidence; no artificial attacks at ordinary state changes |
| Exact structural loop solver | Shared `source_loop_plan` and `loop_structure` implementation |
| Child repeats inside a held note | OPM performed runs feed the same planner |
| Adjacent identical positive states | Coalesced before child and outer repeat keys, independently of harmless source partitioning |
| Setter and duration compaction | MDX-specific voice/volume/pan/gate/detune reuse and safe finite duration loops |
| PSG/SCC software envelope recognition | Shared in the MGSDRV route; OPM/MDX controls use their supported target representation |
| MGSDRV macros and gate syntax | Compiler/driver-specific; not copied into MDX as unsupported syntax |
| Short-state selection | Shared MSX-derived selector; target-specific protection and rendering |

## Configurable short-state projection

With normalization enabled, `--fm-state-ms` controls eligible intra-note pitch
and uniform carrier-level state omission. It defaults to **24 ms** (1058 original
44.1 kHz samples, rounded down). Smaller or larger values remain selectable for listening comparisons.
`--normalization-ms` independently keeps its 8 ms default for whole-gate omission
and target boundary movement. Changing one option does not change the other.
`--no-normalize-lengths` disables both output approximations.

```sh
python scripts/export_mdx.py input.vgm --outdir outputs/fm-state-4ms \
  --fm-state-ms 4 --no-vgm
```

The shared `fm_state_runs` selector serves MSX OPLL normalization, x68k
OPM-to-OPM, OPNA-to-OPM and projected DCSG-to-OPM, and MUCOM native OPNA / OPM-to-OPNA adapters.
MSX keeps its existing opt-in normalization and 44-sample default. Chip-specific
protection remains in each adapter. These are deliberate output approximations,
not chip specifications or claims that all sub-frame controls are inaudible.

For OPM, complete key-gate endpoints stay fixed. A surviving first state fills
an omitted prefix; a preceding retained state fills an omitted middle interval.
Tone changes, nonuniform operator levels, pan/modulation, partial/repeated key
operations, ordered global effects and zero-source-time controls are protected.
Candidate states also pass target pitch, noise and voice-capacity checks.
Source State, Segments, PCM IR and original writes remain unchanged.

### Release state and structural equality

The last positive source state is protected for the released envelope. If it
has positive target duration, it remains an ordinary held run. If its target
duration is zero, earlier short-state selection is kept: original writes at
that release target tick are emitted in their original relative order at the
existing renderer's terminal position. Missing KC/KF/TL values inherited from
an omitted earlier state are then restored explicitly. These supplemental
writes are labeled as target restorations, separately from source writes.
A plan with no surviving positive target run still falls back conservatively;
it does not invent a duration for the tail. No extra target tick is added.

The actual terminal write sequence and final state are part of repeat equality.
Different release states can therefore prevent two otherwise matching notes
from sharing a loop. Removing them might save commands or permit extra repeats,
but key-off does not make an FM release silent: the last frequency and level
can affect the released tail and persist until overwritten. Omitting a 1 ms
pre-key-off state could change a much longer release, not only that 1 ms.
Such a policy would require a separately diagnosed listening decision; it is
not enabled by raising `--fm-state-ms`. Register-state replay checks do not
establish acoustic equivalence or native driver playback.

## Score units and internal control trajectories

An internal chip-state boundary is not an additional musical note. A musical
attack owns its pitch/level trajectory; native State and Segments retain that
trajectory independently of output notation. OPM target rendering can still
spell a held trajectory as tied timed slices when no higher-level target
representation has been inferred. Those slices reproduce explicit VGM KC/KF/TL
controls, not a simulation of the chip's internal waveform or envelope phase.
They are a rendering fallback, not the intended musical segmentation.

Further work should distinguish score events from expressive controls and
instrument behavior, then project supported modulation/envelope patterns with
appropriate target commands. A duration threshold alone does not establish
that a change is nonmusical or equivalent to an instrument definition.

## Canonical positive held-note runs

`opm_performed_runs` supplies the target-only grouping used by
`opm_mdx_music`. Within one ordinary complete attack, contiguous runs with
identical **complete projected OPM state** can share a duration when the later
run has no new emitted operation. The comparison includes pitch, operator
parameters, key mask, pan and shared controls, not just a note name or volume.

This handles, for example, an intermediate KC/KF update and restoration that
already occupy one target tick after normalization: it must not create a new
timed slice or block phrase recognition when the positive state is unchanged.
Original writes and their native timing remain in the source/unit trajectory.
Uniform carrier-volume setup is reused only while known; raw writes invalidate
that knowledge so a necessary volume restoration remains explicit.

Raw register writes are barriers with retained order. Coalescing does not
cross a retrigger, partial key operation, release, song-loop marker or gap.
With short-state selection disabled or protected, different positive states
survive even if very short. Exact coalescing itself removes no differing state. Long durations
still pass through the existing <=256-tick note splitter and held-note ties.
No arbitrary raw-write deletion, state-curve flattening or PCM changes occur.

## Repeat equality and exit state

A musical note's `performed_key` records its entry state and emitted entry
operations, canonical positive runs, ordered terminal/release operations and
final state. Different zero-time source partitions no longer make identical
performed notes unequal. A different terminal operation/state still prevents
incorrect reuse even when all sounding intervals match.

Inner and outer repeat planning use these canonical positive runs. The shared
source-loop renderer additionally verifies exact expansion of the proposed
rendered loop body. Source identities and the full original trajectory remain
in the unit independently of the performed key. Raw fallback/control units
keep their conservative original equality and ordered controls.

## Inspection

Use the canonical converter with `--dump-passes`:

```sh
python vgm2mml.py input.vgm --outdir outputs/input --dump-passes
```

- `<stem>.mdx.structure.performed_runs.csv`: input positive runs, source-event
  membership, retained/merged action and target-run index/bounds. Full state
  and ordered actions permit inspection before loop planning.
- `<stem>.mdx.structure.units.csv`: original trajectory/membership plus the
  separate performed key. Source rows are not replaced by normalized rows.
- Existing inner/outer loop CSVs and plain/uncompacted/final MML remain.
- `<stem>.fm.short_states.csv` and `.json` are saved by structured conversion
  even without `--dump-passes`; they report configured thresholds and each short
  state omission/protection or rejected plan. With pass dumps the same decisions
  appear in `.mdx.structure.short_states.csv`.
- Structure summaries report input performed-run count, merged-run count and
  short-state omission count.

Compiled bytes, not MML character count, determine whether the MDX fits.
Exact grouping may expose additional loops or reduce tied fragments, but it
does not guarantee that every long/dense song fits its MDX track offsets.
Successful compilation/state comparison is distinct from native listening.
