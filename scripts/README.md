# Export and diagnostic tools

Normal single-file conversion uses `python vgm2mml.py`; conversion implementations live in `py/`.

- `setup_tools.sh`: repeatable WSL setup for hash-checked MXC, pinned run68x and the locked Rust helper, outside `outputs/`. Add `--with-mdxtools` for independent metadata/decompiler tools. See `docs/mdx_compiler_setup.md`.

- `export_mdx.py`: single-file or recursive folder export for listening. FM defaults to mmlx, with native MXC via run68 available through `--compiler mxc`. Calls the canonical frontend, parses the compiled MDX and replays it with soundlog. Writes MML/MDX/VGM per FM song, exact MXC input under `_compiler_inputs/`, or the existing typed MML/MDX/PDX pair with an explicit PCM replay limitation. Records compiler/failures without comparing playback. See [usage](../README.md#mmlmdxvgmを生成して聴く).
- `mdx_compiler.py`: isolated MXC invocation, strict CP932 encoding and lossless compiler-dialect preparation; canonical generated MML stays unchanged.
- `compare_opm_vgm.py`: explicit channel-mapped OPM state/Segment, Key-event, nominal-pitch and command-size diagnostics. Saves both inputs' raw/state/Segment CSVs; does not certify waveform, loop seams or native display behavior.
- `verify_opm_mdx_roundtrip.py`: OPM state/Segment roundtrip; CLI defaults to mmlx, soundlog replays the compiled MDX, and the existing comparator remains unchanged. Explicit MXC via run68 is available. Prepared scores and selected compiler are recorded.
- `verify_opna_mucom_roundtrip.py`: development-only OPNA FM control-state roundtrip through WING's MUCOMVGM. Keeps source/target/re-read passes and checks known state, operator edge order and exact sample boundaries. Its register-MML is a validation artifact, separate from the X68000 MDX output. See `docs/opna_mucom_roundtrip.md`.
- `mdx_fixture_generator/`, `generate_opm_public_fixtures.py`: external MDX replay and authored fixture preparation; the helper's own MML compilation modes use mmlx.
- `decompile_mdx_references.py`: external mdxtools MDX-to-MML reference preparation, provenance and limited structural audit. See `docs/mdx_reference_mml.md`; references are separate from normal VGM conversion.
- `psg_scc_to_mdx.py`: batch projection audit with optional compiler verification and reference comparison; shares `py/psg_scc_conversion.py`.
- `audit_mdx_metadata.py`, `render_additive_mdx_notes.py`, `analyze_wav.py`: metadata, additive-model experiments and acoustic diagnostics (NumPy for WAV analysis).
- `batch_vgm_to_mgs.py`, `collect_mgs.py`, `compile_mgs.mjs`, `mml_to_vgm.mjs`, `mgs_to_vgm.mjs`: compatibility batch/compiler/replay diagnostics. Batch conversion invokes the canonical frontend with `--target mgs`.
- `check_opll_key_edges.py`, `check_reference_pitch.py`, `compare_reference_vgmticks.py`, `audit_reference_loop_windows.py`, `audit_mml_loops.py`, `verify_pitch_roundtrip.py`: compatibility evidence checks, retained because tests and source semantics depend on them.
- `setup_psg_pcm.sh`, `psg_pcm_probe.c`: pinned external emu2149 source runtime for opt-in PSG-to-PCM projection. See [scope and diagnostics](../docs/psg_pcm.md).
- `fit_scc_fm.py`, `scc_opm_probe.c`: optional static SCC voice fitting against the external YM2151 core; writes a content-addressed bank, measured scores and optional audio. See [fitting](../docs/scc_fm_fit.md) and [MML use](../docs/scc_fm_projection.md).
- `batch_vgm_conv.py`: external converter comparison.
- `experiment_*.py`: retained development experiments; not normal conversion frontends.

External compiler/player tools and Node dependencies are optional; native PCM output requires the Rust helper's typed MDX assembly and PDX packing modes. Inspect the documented tool arguments and dependency errors before use. The Rust generator has its own README and locked dependencies. Build outputs are ignored.
