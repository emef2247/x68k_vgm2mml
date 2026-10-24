# Export package layout

The default `scripts/export_mdx.py` command creates one package for each
original input directory. Relative parent directories below INDIR are retained.
For example, INDIR/vgmrips.net/NEMESIS/SONG01.vgm becomes:

```text
OUTDIR/vgmrips.net/NEMESIS/
  tracks/
    SONG01.mml
    SONG01.mdx
    SONG01.pdx
  _diagnostics/
    SONG01/
  _source_inputs/
    SONG01.vgm
  listening_manifest.json
  results.csv
```

PDX is present only when required. Final files live directly in `tracks/`;
there is no per-song listening directory. Compiler inputs, reports, replay VGM,
source/Segment/target dumps and other evidence remain under
`_diagnostics/<safe_stem>/`. Internal diagnostic trees may contain further
working directories; those are not listening publications.

`--outdir OUTDIR` selects a separate output tree. If omitted, each package
is created beside its original VGM files. Recursive discovery skips managed
`tracks`, `_source_inputs` and `_diagnostics` directories on every run.
Explicit overlapping input/output trees are rejected.

Existing portable 8-character stems are preserved. Other names receive the
existing deterministic short stem before conversion, so MML, MDX and PDX
references agree without binary patching. Original source bytes and titles
are retained; `_source_inputs/` contains a byte-identical staged copy.

Each package has a version-1 `listening_manifest.json` with source hashes,
staging ownership and the path/hash of every published final artifact.
Package `results.csv` paths are relative to that package and retain other
songs during a partial rerun. `OUTDIR/_diagnostics/results.csv` is the latest
batch aggregate with paths relative to OUTDIR, as are programmatic return rows.

The entire batch is checked for final-name collisions before conversion.
Modified or unowned final files, modified staged sources and conflicting
source owners are rejected. A song publication is prepared as a complete
bundle and replacement errors restore its old files. A failed rerun preserves
its previous listening set; `latest_attempt_status` and current results report
the failure, while publication status and source hash retain their last
published provenance. Stale files are never advertised as this attempt's
successful binaries.

Old `tracks/<stem>/` ownership manifests are not destructively migrated.
Use a fresh output tree when an incompatible legacy ownership entry is reported.
The low-level `run_batch(..., listening_layout=False)` diagnostic/compiler
interface keeps its existing working layout.
