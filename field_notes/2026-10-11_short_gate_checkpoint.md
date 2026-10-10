# Original-time short gate output policy checkpoint

The user authorized omission of complete sounding gates <=8 ms, classified
before normalization from original Key-On to Key-Off. Source analysis is kept.
352 samples is the largest integer duration <=8 ms at 44100 Hz; 353 is retained.
PSG/SCC original source-map times are passed into gate classification rather
than deciding from the intermediate rounded OPM VGM. PCM checks source
eligibility before omitting any short playback; PDX sample bytes are retained.

Structured normalization tries the musical clock, then bounded fallback
multiplier 65 down to 1 (16.640 ms preferred, finer when needed). Boundary
movement must not exceed 352 samples. Positive surviving gates, long rests,
side-effect pulses and valid loop spans are protected. Short Off-to-On gaps
may coalesce, retaining both ordered commands. Their lost rest duration is
reported separately from omitted gates. No native GUI improvement is claimed.
Use --no-normalize-lengths to disable the new output policy.

## Checkpoint before verification

The user requested a repository checkpoint before further testing, then
minimal public-only validation. No local_only conversions are permitted here.
Earlier checks (160 Python tests before this policy, 14 Rust tests before the
last integration edits) do not validate the final checkpoint. A first
experimental from_fm package exported 16/16; it predates short-rest coalescing
and must be regenerated. The Rust release helper must also be rebuilt.

## Rebuild and export in WSL

Run from /mnt/i/wsl/repositories/emef2247/test/x68k_vgm2mml:

```sh
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python scripts/export_mdx.py tests/fixtures/public/opm/from_fm \
  --outdir outputs/listen/opm/from_fm_8ms
python scripts/export_mdx.py tests/fixtures/public/opm_oki6258 \
  --outdir outputs/listen/opm_oki6258_8ms --no-vgm --pcm-policy best-effort
```

MML/MDX/PDX are published under tracks/<short_name>/; diagnostics remain
available separately, including human-readable TXT statistics. Tiny PCM
fixtures can intentionally become silent when their whole playback is <=8 ms.
Export success alone does not establish native playback/display validity.

Next: minimal synthetic boundary tests (352/353, original mapped phase,
short-rest command order), one representative public FM export and one PCM
export. Record actual results here after the checkpoint. User can then perform
XM6TypeG/MMDSP listening. Clock-control pattern repair stays canceled.
