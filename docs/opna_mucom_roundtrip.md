# Diagnostic OPNA FM roundtrip

The validation path is `VGM -> native State/Segments -> diagnostic MUCOMVGM
register-MML -> VGM -> native State/Segments`. It is a development check,
separate from the X68000 converter's MDX output. It establishes preservation
of modeled FM controls, not acoustic equivalence or musical note/voice MML.

```bash
python scripts/verify_opna_mucom_roundtrip.py tests/fixtures/public/opna \
  --outdir outputs/opna/mucom_roundtrip
python -m unittest discover -s tests/scripts -p 'test_opna*.py' -v
```

The runner uses WING's `mucomvgm.exe` v0.0.5 under
`.tools/mucomvgm-0.0.5/mucomvgm/`; `--mucomvgm PATH` selects its location.
Windows Python and WSL interop are supported. The tool is a local dependency,
not bundled source or an executable redistributed by this repository. See
[source setup](opna_segments.md#mucomvgm-source-check) and
[license notice](../THIRD_PARTY_NOTICES.md#mucomvgm-005).

The current target accepts one YM2608 instance at 7987200 Hz. Different clocks,
dual instances and CSM are rejected. DAC streams and unknown/uninterpreted
register effects are also rejected: they might affect FM and must not be
silently classified as non-FM. Known SSG/rhythm/ADPCM registers and memory
blocks remain excluded evidence. `--loop-count N` checks a finite expansion
of declared VGM loops while preserving held state; it does not validate an
infinite playback loop or an audio loop seam.

## Target boundary

`py/opna_mucom.py` consumes the immutable integrated native Segment collection.
It derives operator parameters, committed FNUM/BLOCK pairs, key masks and
shared FM controls from typed State fields. Original register identifiers select
the field and retain event order/provenance; original data bytes are not simply
replayed. Shared snapshots are deduplicated by source event/instance. Target
write rows list contributing Segment IDs in `target_writes.csv`.

One MML control track carries both ports with MUCOMVGM's 0..511 `y` addresses.
It uses explicit key controls and rests rather than note events, avoiding
driver-generated voice, key and pitch changes. This is register-MML, not a
compact editable musical score. Its virtual clock `C192 T55125` maps `r%1`
to exactly one 44100 Hz VGM sample: four internal ticks at 1/4 sample per tick.
It is an accepted MUCOMVGM diagnostic extension, not an ordinary MUCOM88 tempo
or a claimed score compatible with the original PC-8801 driver.

The compiler buffers frequency-high writes per register, while native OPNA
uses shared latches. The projection emits a canonical high/low pair for every
committed pitch boundary. Standalone source high-latch writes remain in source
IR; the target need not reproduce the writer's latch bookkeeping. Reserved
operator bits are canonicalized without modifying original evidence. Prescaler
selectors use alternating unused data bytes so compiler deduplication cannot
erase a repeated address strobe.

## Comparison and artifacts

The runner independently compiles a one-sample rest to establish the compiler's
zero-time initialization prefix. It saves the initializer's VGM, passes, log
and executable SHA256 under `_compiler_profile`. The returned prefix must match
exactly, and its state remains present in subsequent comparisons. Known source
controls cannot be excused as initialization. No final key-off or wait is stripped.

For each input, `tracks/<relative input>/` contains:

- `source/`: Raw, State, integrated Segments, unmodeled/auxiliary evidence and
  native analysis manifest, plus shared timing CSV.
- `target_writes.csv`, `generated.muc`, `generated.compile.log`: projection and
  exact external compiler input/output diagnostics.
- `returned.vgm`, `returned/`: external VGM and its reconstructed native passes.
- `comparison.json`: clock, sample boundaries/end, compiler-normalized control
  sequence, per-boundary known semantic State and ordered operator key edges.

`results.csv` / `results.json` summarize each input. `passed` requires all FM
checks to agree. `no_active_fm` marks sources without an observed FM attack and
is not evidence of a playable FM conversion. Non-FM domains and auxiliary
commands are reported separately. SSG, rhythm, ADPCM, timer expiry, acoustic
release and LFO/envelope phase are not compared. Unknown source fields remain
unknown expectations. Latch/raw-history fields and unused register bits are
excluded from semantic equality; committed pitches, known operator/control
values, edge order and the final held state remain checked.

## Repository boundaries and next branches

The shared source modules `vgm_io`, `vgm_timing`, `vgm_loop`, `vgm_reader` and
`opna` provide the native evidence boundary. `opna_mucom`,
`opna_mucom_roundtrip` and the diagnostic runner form the MUCOM-specific target
boundary. They can move into a future `mucom88_vgm2mml` without importing MDX
target conveniences into source State/Segments. A standalone repository will
need a small source-only reader adapter; do not duplicate the interpreter or
route it through OPM to accomplish that split.

The next MUCOM milestone includes SSG, whose musical behavior is equivalent to
PSG, alongside FM. Preserve SSG source evidence, construct inspectable Segments,
and include the13 currently `no_active_fm` patterns in SSG MML roundtrip coverage.
The current milestone intentionally validates FM only, as accepted by the user.

The X68000 branch will project native OPNA Segments to OPM at 4 MHz using the
vgm-conv mapping and to MSM6258 PCM IR. Source evidence, target projection and
loss/eligibility diagnostics remain separate. Normal chip usage detection will
select that route and output MDX MML; MUCOM MML is not a normal output format.
The mapping is not implemented by this validation change. On adoption, record
the vgm-conv method, provenance and notice in README and developer documentation.
