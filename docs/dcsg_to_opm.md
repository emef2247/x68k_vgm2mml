# DCSG to OPM / MDX

The canonical MDX frontend accepts single and dual SN76489-family command
streams (`0x50` / `0x30`, with optional stereo masks `0x4f` / `0x3f`). Unused
clock declarations do not select the route. Active combinations with other
source engines and T6W28 cross-chip semantics are outside this projection.
The MGSDRV compatibility frontend has not gained DCSG support.

```sh
python scripts/export_mdx.py input.vgm --outdir outputs/dcsg \
  --force
```

## Evidence and musical interpretation

`dcsg.py` shares the MUCOM converter's native analysis. Source latch selection,
known register bits, attenuation, periods, noise resets, stereo masks and chip
instance remain separate from target controls. Unknown source state is not
replaced with a presumed hardware reset. Native CSV files are retained even
when ordinary pass dumping was not requested.

A source-only interpretation view passes exact SN periods and monotonic level
indices to the shared MSX `extract_notes` / volume-run rules. This reuses note
continuity and volume-rise attack inference without converting SN registers
into AY registers. Such attacks are musical inferences: DCSG has no Key-On
register, and inferred OPM attacks do not preserve source oscillator phase.

The target writes retain original 44100 Hz sample timestamps and native Segment
IDs. `projected_opm/*.source_map.csv` links serialized commands to those writes;
`provenance.json` labels the stream as projected OPM derived from DCSG.
The ordinary OPM converter then performs the established held-note, inner-loop
and phrase-loop processing. No new source-level envelope classifier is implied.

For a declared song loop, the original body is played once, then decoded again
from the ending latch/register/noise state. The repeating MDX `L` starts at the
end of that first traversal. Replayed native writes retain original event IDs
and iteration indices. `--no-song-loop` produces one finite traversal instead;
`--no-loops` independently disables finite repeat compaction.

## Target allocation and losses

- Each chip's three tones use A–C or D–F. G is unallocated. H supplies the single
  OPM noise lane. Square tones use the existing four-carrier additive model,
  projected KC/KF pitch and nominal two-dB attenuation steps.
- Fixed-rate white noise uses the nearest supported OPM noise rate. LFSR,
  spectrum, phase and reset behavior differ; approximation rows report source
  rate, target rate and cents error. This is allowed with diagnostics in either
  mode, following the existing PSG noise approximation policy.
- Two chips may share H in nonoverlapping intervals. During overlap, instance 0
  has priority. Strict conversion stops; `--force` omits only the competing
  interval and resumes it when H becomes free. Tone2 is retained independently.
- Periodic noise and tone2-linked noise currently require strict rejection or
  explicit force omission. T6W28 audible intervals likewise cannot be mapped
  through an ordinary dual-chip interpretation.
- Uninterpreted source writes are rejected in strict mode. Force reports each
  omitted write and affected unknown-state interval; native evidence remains.
- `--opm-pitch-policy clamp|error` retains the existing target-range policy.
  Clamping is diagnosed separately from deliberate noise omission.

`--fm-state-ms` defaults to 24 ms (1058 source samples) in this x68k frontend.
It applies only to eligible internal pitch/uniform carrier-level states after
OPM projection. The independent `--normalization-ms` default remains 8 ms for
whole-gate omission and target boundary movement. `--no-normalize-lengths`
disables both output approximations. Native DCSG state and software-envelope
curves are not pruned by either option. Larger thresholds and successful
compilation do not establish listening fidelity.

## Inspectable artifacts

- `*.dcsg.writes.csv`, `*.dcsg.states.csv`, `*.dcsg.segments.csv`,
  `*.dcsg.analysis.json`: native source evidence.
- `*.dcsg.loop.json`: first/replayed loop timing.
- `*.opm_performance*.csv/json`: inferred note membership, volume runs, target
  controls and their reconstructed OPM states.
- `*.dcsg_opm.json`, `*.dcsg_opm.forced_omissions.csv`,
  `*.dcsg_opm.approximations.csv`: allocation and explicit losses.
- `projected_opm/`: serialized OPM VGM, source map, normalization and structured
  MDX passes. `*.fm.short_states.csv/json` is also copied beside the final MML.

The export default timeout is 1200 seconds per input per stage. It can be
changed with `--timeout`; increasing it permits longer work without certifying
that a resource-limited conversion will succeed.
