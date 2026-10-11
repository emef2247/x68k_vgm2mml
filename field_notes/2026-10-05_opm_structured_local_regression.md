# Structured local OPM / MDX regression (2026-10-05)

## Scope and evidence

Working repository: `/mnt/i/wsl/repositories/emef2247/test/msx_vgm2mml`.
The user completed this command; this review inspected its existing artifacts:

```sh
python scripts/verify_opm_mdx_roundtrip.py \
  tests/fixtures/local_only/opm \
  --outdir outputs/opm/regression/structured_local_only
```

Inputs to this review were `results.json`, `results.csv`, per-case compile logs,
generated MDX MML, timing JSON, native Segment CSV and target structure-unit CSV.
Successful `returned.mdx` files were also inspected to validate a byte-cost model.
Original results and generated files were not overwritten. No fresh full regression,
audio comparison, source parser changes, Segment changes, or compression fixes
were performed. Private fixture content is not reproduced here.

Derived reports are under
`outputs/opm/regression/structured_local_only_analysis/`:

- `summary.json`: status totals and successful comparison totals.
- `capacity_failures.csv`: all 17 failures and per-FM-track byte estimates.
- `capacity_diagnostics.json`: command-cost categories and compiler error details.
- `capacity_model_validation.json`: comparison with 35 existing successful MDX files.

## Result summary

| Result | Cases | Meaning |
| --- | ---: | --- |
| success | 35 | MML compilation, MDX replay and Segment comparison passed |
| conversion_failed | 17 | MML was generated; external MDX compilation failed on track-offset capacity |
| unsupported_target | 134 | Source YM2151 clock is 3,579,580 Hz; current MDX projection requires 4 MHz |
| Total | 186 | Local inputs inspected by this run |

The supported-clock cohort has 52 cases, of which 35 passed and 17 hit capacity.
The 134 unsupported cases are not evidence of a faulty VGM-to-Segment parser or
a failed fidelity comparison; they did not enter the target roundtrip.

Successful cases: private-source-002 11, MDX 13, private-source-006 7, vgmrips.net 4.
Failed cases: MDX 5, other group 1, private publisher group 1, capture catalog 10.
All unsupported cases are under vgmrips.net. There are no `comparison_failed`
or `compile_timeout` rows in this run.

## Successful comparison measurements

| Measurement | Source | Returned | Missing | Extra |
| --- | ---: | ---: | ---: | ---: |
| Channel attacks | 15,749 | 15,749 | 0 | 0 |
| Operator KeyOn edges | 57,468 | 57,468 | 0 | 0 |
| Operator KeyOff edges | 57,200 | 57,200 | 0 | 0 |

All 35 have matching per-channel Key-edge sequences and zero known-state
mismatches. Projected event times and projected end times match exactly.
Source-to-projected timing error is at most 6 VGM samples, reflecting the
MDX tick projection; this is not exact source-time preservation.
Four private-collection-028 cases have returned end times 1–5 samples earlier than the source,
and exactly equal to the projected end times (01: -3, 03: -5, 05: -1, 14: -3).

The comparison is `hybrid_effective_state`, not byte-for-byte VGM equality.
Tone/note lowering can add initialization writes; equal-time writes on different
channels can be reordered by independent A..H tracks. Known effective state and
ordered per-channel Key edges are the comparison evidence. These measurements
do not establish waveform or physical-hardware equivalence.

## Structure effect

For the 35 successful cases only:

- Flat MML: 1,580,660 characters.
- Structured MML: 1,453,826 characters.
- Reduction: 126,834 characters (8.02%).
- Emitted loop commands: 660, across 26 cases; largest emitted depth: 3.
- Nine successful cases have no emitted loops.

This is the renderer's flat-versus-structured character measurement within the
same run, not a comparison with an earlier regression or the original MDX/MML.
There was no prior-version baseline in this review. Successful-case selection
also means 8.02% must not be generalized to all 186 inputs.

## All 17 conversion failures

Every log reports the same compiler error family:

```text
data inconsistency: MDX track N offset exceeds the maximum 0xfffe
```

All 17 have generated MML and native/target inspection artifacts, but no
`returned.mdx`. The failure is in external MML-to-MDX compilation/finalization,
before playback and returned-Segment comparison. Fidelity for these cases is
therefore unmeasured. Longer timeouts cannot resolve this error.

In the current mmlx/soundlog build, track start offsets are unsigned 16-bit
values; `0xffff` means absent, so the largest usable track start is `0xfffe`.
Offsets are cumulative. The reported track index is the first overflowing
start address, not necessarily the track that produced most of the data.
Index 8 is the compiler's ninth PCM/dummy track, not an OPM ninth channel;
FM-only output still has this two-byte EndOfTrack marker in the nine-track layout.
This differs from MGSDRV track-buffer allocation: `#alloc` cannot repair it.

The byte estimates below count physically emitted track commands, retaining
loops without unrolling them. Header, tone bank and padding are excluded;
the dummy track's two bytes are included. They are **estimates** for failures,
not measured sizes of compiled MDX files. The model matches all A..H track spans
in the 35 successful compiled files; their dummy end markers also match.
Including the current compiler's initial tone reservation predicts the first
overflowing track index for all 17 failed cases.

| Input | Error index | Estimated track bytes | Flat → structured characters | Emitted loops / max depth |
| --- | ---: | ---: | ---: | ---: |
| `<private-reference>/private-case-142.vgm` | 8 | 118,408 | 319,672 → 296,266 | 111 / 1 |
| `<private-reference>/private-case-146.vgm` | 8 | 88,078 | 238,098 → 235,474 | 59 / 1 |
| `<private-reference>/private-case-149.vgm` | 8 | 67,508 | 186,845 → 166,872 | 84 / 2 |
| `<private-reference>/private-case-155.vgm` | 8 | 131,189 | 342,568 → 319,890 | 173 / 3 |
| `<private-reference>/private-case-157.vgm` | 8 | 113,215 | 303,886 → 283,873 | 150 / 2 |
| `<private-reference>/private-case-194.vgm` | 6 | 106,376 | 280,858 → 250,154 | 514 / 2 |
| `<private-reference>/private-case-055.vgm` | 4 | 152,541 | 442,778 → 439,345 | 7 / 1 |
| `<private-reference>/private-case-195.vgm` | 6 | 143,453 | 389,374 → 389,125 | 5 / 1 |
| `<private-reference>/private-case-196.vgm` | 5 | 147,281 | 409,404 → 409,404 | 0 / 0 |
| `<private-reference>/private-case-197.vgm` | 4 | 180,605 | 493,956 → 493,956 | 0 / 0 |
| `<private-reference>/private-case-198.vgm` | 6 | 83,339 | 220,899 → 220,899 | 0 / 0 |
| `<private-reference>/private-case-199.vgm` | 5 | 156,180 | 427,176 → 427,176 | 0 / 0 |
| `<private-reference>/private-case-200.vgm` | 4 | 264,659 | 720,281 → 720,281 | 0 / 0 |
| `<private-reference>/private-case-201.vgm` | 5 | 190,733 | 501,273 → 501,193 | 1 / 1 |
| `<private-reference>/private-case-202.vgm` | 3 | 231,555 | 624,225 → 624,225 | 0 / 0 |
| `<private-reference>/private-case-203.vgm` | 3 | 564,208 | 1,542,531 → 1,542,531 | 0 / 0 |
| `<private-reference>/private-case-204.vgm` | 6 | 179,235 | 489,989 → 489,989 | 0 / 0 |

## Why track data becomes large

Confirmed from the emitted MML and the locally installed external compiler code:

- Each raw OPM register-write command occupies three MDX bytes.
- A rest occupies one byte per at most 128 MDX ticks. Writing a long `r%N`
  is short text, but the compiler expands the duration into many rest commands.
- A note occupies two bytes per at most 256 ticks. Sustained-note splitting also
  requires tie/key-off control. At the current `@t255` (256 microseconds per tick),
  these limits are about 32.8 ms per rest and 65.5 ms per note.
- The current note renderer emits voice, volume, pan, gate and detune setters
  per note. Their runtime byte cost matters even where source state is unchanged.
- Fixed isolated note units are lowered to notes/@voices. Noise-enabled notes,
  partial operator keys and many held-note state changes remain raw controls.
  This conservative choice preserves evidence but can be expensive.

Examples from the current physical-command model:

- `private-case-149`: 67,508 track bytes; H alone is 43,969. Raw writes account for
  43,566 bytes across the output. This is a useful near-limit optimization case.
- `private-case-155`: H alone is 84,895 bytes. Channel-7/noise/tone controls dominate
  its native raw-unit stream; extending conservative note lowering is relevant.
- `private-case-194`: repeated setters consume 36,907 bytes of 106,376 track bytes.
  F/G are large; this is a useful state-aware setter-reuse case.
- `private-case-203`: 564,208 track bytes, of which raw writes account for 440,895.
  E alone is 292,984 bytes. KC/KF/channel controls, operator TL/voice changes
  need more compact target expression; shortening rest text alone is insufficient.
- Seven of the ten failed private-collection-028 inputs have no emitted exact source loops.
  The source-derived exact plans do not make frequent held controls disappear.

These are target capacity observations. They do not justify dropping operator
updates, suppressing attacks, normalizing source timing or changing native
Segments just to fit MDX.

## Countermeasures to evaluate next (not implemented)

1. **Report the failure stage explicitly.** Keep current original results as
   evidence; in future runs distinguish MDX capacity/compile errors from Python
   conversion errors and replay/Segment mismatches. Include the overflowing track
   index, cumulative offset and dominant command categories. Increasing the
   timeout would address a different problem.
2. **Reduce target-state setter repetition.** Start with private-case-194 and a small
   synthetic case. Reuse voice/volume/pan/gate/detune state only when safe;
   intervening raw writes can invalidate cached state. Preserve expanded target
   meaning, native membership and inspectable decisions.
3. **Make target duration encoding compact.** Repeated silence and held-note
   duration chunks may permit finite loops. Loop boundaries must not create
   KeyOn/KeyOff edges: compiler tie/lookahead semantics need dedicated checks,
   followed by native-state/Key comparison. A shorter MML length spelling by
   itself does not change the compiler's duration splitting.
4. **Extend conservative held-note/noise lowering.** Use private-case-149/H first, then
   private-case-155, private-case-055 and private-collection-028. Keep native partial-key, KC/KF, per-operator TL,
   patch and noise behavior; represent controls inside a held note where MDX can
   express them. Do not replace arbitrary operator-TL trajectories with a single
   inferred channel volume. MDX noise commands are not interchangeable with all
   raw noise writes: the local replay implementation preserves the enable bit
   while changing frequency. Enable transitions need separate handling.
5. **Measure binary benefit separately from source text.** Current exact loops
   reduce physical commands, but macro/text shortening is not sufficient evidence
   of a compiled-size reduction. Verify expansion and compiled output, then use
   the integrated source Segment CSV and target-unit mapping for roundtrip checks.

The 134 unsupported 3.57958-MHz inputs need a separate clock-aware pitch target
projection. Do not relabel the source clock as 4 MHz or modify source KC/KF facts.
That work is independent of the capacity failures above.

## Local implementation references

- `scripts/verify_opm_mdx_roundtrip.py`: preflight, external compilation and
  hybrid effective-state comparison; current broad `conversion_failed` status.
- `py/opm_mdx_structure.py`: conservative note eligibility, raw fallback,
  duration splitting and repeated note setters.
- `scripts/mdx_fixture_generator/Cargo.toml`: mmlx 0.2.0 / soundlog 0.15.0 build.
- Local mmlx `src/mdx/compile.rs`: register/rest/note/control lowering and
  nine-track output construction.
- Local soundlog `src/mdx/document.rs` and `command.rs`: layout offsets and
  encoded command lengths; `convert.rs`: noise replay semantics.

External code was inspected only for diagnosis; it was not copied into project
implementation or modified. All proposed fixes remain at target projection or
diagnostic reporting, leaving source parsing and the integrated native CSV intact.
