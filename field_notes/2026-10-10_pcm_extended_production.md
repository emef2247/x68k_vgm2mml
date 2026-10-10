# Verified finite endings and production PCM mode

The user confirmed that all six current root MDX files in
`outputs/listen/finite_end_tail/` play correctly and stop correctly in MMDSP.
This supersedes the failed standard-nine generation, not its archived evidence.
The screenshot shows MADRV. No additional environment assumption or inquiry
was made. Workspace hashes were checked; hashes of the user's copied files
were not independently measured. Display was not separately reported for all
six in this confirmation. No PCM roundtrip success is claimed.

| Case | Current MDX SHA-256 | Playback / natural cessation |
| --- | --- | --- |
| RATES | b4bd0b64e163b4ba7c97e38f5bfffaea0d8b72a05e360abf9f14ced0ee2f4f44 | pass / pass |
| RATESF | 2f50c3924c245673546b53f022167acdba4d4ea2aa5f89e9710a6094f810220a | pass / pass |
| RATESP | a4411707c69f95660413ff218b9c57429bfe0ab64b518cbe6dd0bf36ba83cc91 | pass / pass |
| FS432 | d80c442c1f4a8c46296d3a161691da000d0d4e9e1e60e875df68ea14a0ef722a | pass / pass |
| FS432F | e863fca1fb4308665af0b69ecc99866aed85b6bfb11299d714d9131da61ba9c0 | pass / pass |
| FS432P | a375aa735b53e2174539b1f5a47c232fd0086261cb5032748df62f224fe12e3e | pass / pass |

`listening_results.json`, `listening_observations.csv` and both validation JSONs
in that package now record the new results. The public RATES variants also have
`tests/fixtures/public/mdx_reference/listening_extended_results.json`; the
previous standard-nine `listening_results.json` retains its failure. Private
phrase/sample bytes remain ignored. HOLDEND's earlier successful standard-nine
ending remains separate evidence; no universal standard-nine defect is inferred.

## Applied production change

The verified delta is initial E8 on A and sixteen track offsets, with Q-W
containing only finite endings. Notes/control order, durations, holds, tones,
title, PDX name and payloads were preserved in the listening experiment.
Trailing rests alone had failed; no new tail silence or payload markers were
added to the production converter.

`--compile-pcm` now uses the existing soundlog typed builder for this same mode
selection. Existing FM compilation stays mmlx, followed by typed PCM assembly;
the listening baseline had used native MXC followed by the typed mode change.
Only this mode delta is adopted. Rust compares A minus exactly its initial E8,
B-H, P, voices/title/PDX name and checks exactly one E8 and inactive Q-W after
serialization. Python independently checks the actual emitted layout before
recording generation, rejecting a stale standard-nine helper. FM-only export
still defaults to MXC. Rebuild the helper after updating code.

PCM source IR, sample bytes, source decoder evidence and the shared MDX clock
are unchanged. Single P, bank0/96 slots and the verified sample-size scope stay
bounded. Extended-mode support above65535 sample bytes is unknown, so that
case is blocked as `unverified`/implementation scope, rather than attributing
the old PCM1 low-word limitation to the new mode. Held pan remains a deliberate
projection omission with known loss. Other extended-mode controls/reset are
not certified by six natural-ending checks. Strict/best-effort distinctions
and runtime `unverified`/`not_run` remain visible for newly generated inputs.

`export_mdx.py --no-vgm` generates MML/MDX/optional PDX without invoking the
uncertified PCM replay. It requires the complete typed pair rather than
recompiling readable PCM as fallback. Default replay and roundtrip tooling
remain available; PCM replay still reports its existing limitation.

## Public-only verification

- Rust helper: 12 tests passed and offline release build completed.
- Ten selected public/authored test modules: 138 tests passed, including
  all F0-F4/onset pan, long holds, finite streams, PCM-only/OPM+PCM, shared-clock
  fallback, source bytes, capacity diagnostics, mode preservation and exporter.
- Actual folder export: all11 inputs succeeded with `--no-vgm --pcm-policy
  best-effort`; ten PCM pairs and one supply-only MML/MDX without PDX.
- Independent structure audit: all ten pairs have16 tracks, one E8, complete
  finite commands and no invalid PDX slots or PCM bindings. Command/binding/
  control CSVs are under `outputs/listen/public_opm_oki6258_extended/structure/`.
- `mdxinfo.tsv` retains title/PDX resolution and Success for all11. In the ten
  no-tone packages, soundlog emits tone offset0; mdxtools' current `mdx.c`
  includes zero in its minimum-offset calculation and reports Tracks=-1/PCM8=0.
  Those fields are unavailable in that tool output, not a16-track verification.
  Independent header/command audits supply the mode check. A valid tone pointer
  may precede or follow tracks; no-tone offset0 and padding after finite endings
  are now handled by the diagnostic reader, with authored regression checks.

No local_only conversion or playback was run for this implementation. The user
will run those cases. Further ordering research remains paused.

## Reproduction (WSL, repository root)

```sh
cargo build --release --locked --manifest-path scripts/mdx_fixture_generator/Cargo.toml
python scripts/export_mdx.py tests/fixtures/public/opm_oki6258 \
  --outdir outputs/listen/opm_oki6258 --no-vgm --pcm-policy best-effort
python scripts/export_mdx.py tests/fixtures/local_only/opm_oki6258/vgmrips.net/BOSCON \
  --outdir outputs/listen/BOSCON --no-vgm --pcm-policy best-effort
```

The second input is for the user's local run. `best-effort` explicitly permits
diagnosed losses; omit it to retain strict rejection of such losses. Outputs
are `tracks/<relative input with .vgm/.vgz suffix>/<stem>.mdx.mml`, `.mdx`,
and `.pdx` when PCM samples exist, plus assessments/target artifacts and results.
MDX and its named PDX must be copied together for playback.

VGM input fixtures formerly in `tests/fixtures/public/pcm/` are now grouped by
the actual native chips at `tests/fixtures/public/opm_oki6258/`. The generator
and current documentation references were updated; VGM and expectation bytes
were preserved during the move. Their README identifies PCM-only, OPM+PCM,
direct-register and DAC-stream cases, distinct from other chips' PCM formats.
