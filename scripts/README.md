# Export and diagnostic tools

Normal single-file conversion uses `python vgm2mml.py`; conversion implementations live in `py/`.

- `export_mdx.py`: single-file or recursive folder export for listening. Calls the canonical frontend and external compiler/player, writes MML/MDX/VGM per FM song or MML/MDX/PDX with an explicit PCM replay limitation, and records failures without comparing playback. See [usage](../README.md#mmlmdxvgmを生成して聴く).
- `verify_opm_mdx_roundtrip.py`, `mdx_fixture_generator/`, `generate_opm_public_fixtures.py`: OPM compiler roundtrip and authored fixture preparation.
- `decompile_mdx_references.py`: external mdxtools MDX-to-MML reference preparation, provenance and limited structural audit. See `docs/mdx_reference_mml.md`; references are separate from normal VGM conversion.
- `psg_scc_to_mdx.py`: batch projection audit with optional compiler verification and reference comparison; shares `py/psg_scc_conversion.py`.
- `audit_mdx_metadata.py`, `render_additive_mdx_notes.py`, `analyze_wav.py`: metadata, additive-model experiments and acoustic diagnostics (NumPy for WAV analysis).
- `batch_vgm_to_mgs.py`, `collect_mgs.py`, `compile_mgs.mjs`, `mml_to_vgm.mjs`, `mgs_to_vgm.mjs`: compatibility batch/compiler/replay diagnostics. Batch conversion invokes the canonical frontend with `--target mgs`.
- `check_opll_key_edges.py`, `check_reference_pitch.py`, `compare_reference_vgmticks.py`, `audit_reference_loop_windows.py`, `audit_mml_loops.py`, `verify_pitch_roundtrip.py`: compatibility evidence checks, retained because tests and source semantics depend on them.
- `batch_vgm_conv.py`: external converter comparison.
- `experiment_*.py`: retained development experiments; not normal conversion frontends.

External compiler/player tools and Node dependencies are optional; native PCM output requires the Rust helper's typed MDX assembly and PDX packing modes. Inspect the documented tool arguments and dependency errors before use. The Rust generator has its own README and locked dependencies. Build outputs are ignored.
