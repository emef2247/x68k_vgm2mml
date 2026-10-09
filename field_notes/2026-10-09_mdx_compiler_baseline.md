# Conventional compiler baseline and native display checks

The user reported that PSG-derived MDX highlights tracks in MMDSP but does not
animate keyboards or volume meters. Passing mmlx-to-soundlog roundtrips only
checks those implementations together; it does not certify MXDRV/MMDSP behavior.
An independent compiler and native playback are needed to distinguish generated
MML, compilation, replay interpretation and display behavior. Compiler layout
and accepted source dialect must not be conflated with the MDX binary format.

The user selected MXC as the default compiler for `scripts/export_mdx.py` and
asked to avoid detailed mmlx investigation. MXC (`mxc.x` in `MDX_TOOL.lzh`) is
the conventional compiler described in the
[mdxtools instructions](https://github.com/vampirefrog/mdxtools/blob/master/README.md).
mdxtools's own `mml2mdx` is a separate implementation. No claim is made that one
compiler defines all valid MDX or accepts every later MML extension.

Before that selection, the 32 existing authored reference MML/MDX pairs were
probed without VGM conversion. CP932 source was decoded strictly to UTF-8 for
mmlx, retaining original bytes and checking encoding roundtrip. Seven references
compiled; 24 were rejected by syntax/dialect handling and one needed a missing
PDX. These failures were retained rather than removing directives or changing
the score to obtain a pass. They do not identify the MMDSP display cause.

Ignored artifacts are under `outputs/mdx_compiler_2026-10-09/`:

- `results.csv`, `references.json` and per-case source/compiler/mdxdump logs.
- `mmdsp_pairs.zip`: seven FM original/recompiled pairs plus three short newly
  authored controls. `RxxO.MDX` is the original, `RxxM.MDX` the mmlx recompile.
  `BASICX`/`BASICM`, `FINEX`/`FINEM`, `HELDX`/`HELDM` compare native MXC and
  mmlx for ordinary volume, fine volume and held notes. Earlier unsuffixed
  control files are also mmlx output.
- No GUI observation or semantic equivalence is claimed for these pairs.

The documented tool archive was fetched to ignored `outputs/research/mxc_tools/`:
SHA256 `4d4a6f00a100c728f5f4b217998e66ca8e6fa530cdfe1a5ee7c03f70715d98c4`.
The extracted `mxc.doc` and compiler banner identify **MXC v1.01**, MFS soft,
milk, 1989. The document describes it as redistributable freeware. Extracted
`mxc.x` is 9946 bytes, SHA256
`38def25dae39ae35a16668f086843ae9f0d00295e50fd034b7b4108f7c762086`.
Tool binaries are not committed or included in
listening packages. The source-built
[run68x](https://github.com/kg68k/run68x) runner is pinned to
`fc28826dd795b1f0a3241f0b03fe2353e12e7233`. GCC11 requires the build flag
`-Wno-error=format-truncation` for this checkout; this changes build warning
handling, without modifying its emulation source. Legacy LHA extraction needs
a compatible decoder because 7-Zip rejected the archive method.

Compiler selection is for FM-only MML compilation. PCM IR still produces the
existing typed MDX+PDX pair, whose FM portion uses mmlx; report that backend as
`typed_pcm_mmlx`. Do not disguise it as an MXC-compiled PCM export, silently fall
back on compiler failure, or restart the paused PCM stopping investigation.
Native compiler and runtime/display verification results must be recorded
separately from artifacts successfully generated.

## Implemented export path

`scripts/export_mdx.py` defaults to `--compiler mxc` for FM-only input. It
accepts `--mxc` and `--run68`, searches PATH, then the ignored local tool paths
above. The Rust helper remains necessary to parse the resulting MDX and replay
it with soundlog. Explicit `--compiler mmlx` keeps the previous route and needs
neither MXC nor run68. Failure never silently selects another compiler.

Native execution is isolated in a fresh short temporary directory. Copying
the tools/score to `MXC.X` and `SCORE.MML`, with an absolute short compiler path
and cwd set to that directory, avoids observed Human68k path-length/loading
failures. Input is strict CP932 with CRLF. Unrepresentable metadata is an error,
not silently replaced. MXC creates lowercase `SCORE.mdx`; exit zero, a fresh
nonempty binary, and successful helper parsing are required before publishing.
Replay failure keeps the validated MDX. Stage-specific errors and timeouts are
recorded; stale outputs and compiler inputs are invalidated before conversion.

The generated UTF-8 MML and source IR stay unchanged. The adapter makes only
these verified, lossless adjustments in the native compiler input:

- Attach `&` directly to its preceding note, including physical line wrapping.
- Split explicit rests above 256 ticks into 128-tick chunks and a remainder,
  preserving the total duration and enclosing finite loops.
- Use absolute `o8` when a known relative ascent reaches octave 8. MXC v1.01
  rejects `o7 c4 > c4` but accepts `o7 c4 o8 c4`. It does not clamp pitch;
  unknown octave state and genuine overflow remain errors. Tracks retain
  separate octave state, invalidated conservatively at loop boundaries.

Comments, headers, quoted text and voice blocks are protected from these
adjustments. The exact CP932/CRLF score is saved under `_compiler_inputs/`,
linked by `results.csv`'s `compiler_input`. `compiler` records the selected
backend initially and the effective backend for successful exports; a
conversion failure does not mean that compiler was executed. The default
relative octave direction was checked with native encoded notes; `-x` is not
used.

## Validation checkpoint

- 79 focused Python tests passed, including 18 exporter, 11 native adapter
  and 7 roundtrip-batch tests. Coverage includes explicit mmlx routing, PCM exception, missing
  dependencies, native errors/missing output/parser rejection, strict encoding,
  prepared-input isolation, stale output removal and replay failures.
- Actual MXC public OPM export: **9/9** compiled, parsed and replayed. Results:
  `outputs/mxc_export_2026-10-09/public_opm_prepared/results.csv`.
- Actual MXC public PSG export: **11/13** artifacts generated. The other two
  stop during conversion for existing noise/hardware-EG limitations; no
  compilation failures remain in this set. Results:
  `outputs/mxc_export_2026-10-09/public_psg_prepared/results.csv`.
- The public octave-boundary case was decoded independently with mdxtools
  `mdxdump`: all **434** note numbers and durations agree with the canonical
  MML, including the highest note 93. Evidence:
  `outputs/mxc_export_2026-10-09/block_boundary_fixed/note_fidelity.json`.
- A private listening representative was generated with MXC under
  `outputs/mxc_export_2026-10-09/listen_dslayer4/`; private music stays ignored.

These are generation and bounded replay checks, not a native GUI or strict
semantic roundtrip certification. The completion review found no blocking
implementation issue and required the decoded octave-boundary check above.

## Final user decision: retain roundtrip validation

The user reconsidered stopping validation and explicitly requested that
MDX-to-VGM and roundtrip validation remain available. Roundtrip comparison is
part of this project's value for assessing MML generation. The agreed change
is the FM MML compiler, from mmlx to MXC; MDX replay and Segment comparison
remain. Passing compilation, passing semantic comparison and native GUI
behavior must still be distinguished.

`verify_opm_mdx_roundtrip.py` therefore also defaults to MXC, with the same
explicit mmlx/tool-path options as export. It compiles initialization and the
converted score with the same selected backend, replays the compiled binary,
and uses the existing comparison unchanged. Results record the compiler and
prepared source. Existing internal diagnostic callers retain their mmlx
default; they are separate from the user-facing roundtrip CLI. PCM handling
and its current replay guard are unchanged.

Actual native public OPM roundtrip completed for **9/9** cases using MXC.
All nine result rows have `passed=true`, with maximum source timing error zero
samples; comparison conditions were not relaxed. Results are under
`outputs/mxc_roundtrip_2026-10-09/public_opm/`. The reviewer identified a
stale-evidence reporting issue on failed reruns; known prior per-song artifacts
are now invalidated before preflight/conversion, with a regression test. The
follow-up review found no remaining blocking issue.

Historical findings about strict GRA release-order comparison, source song
loops, track-offset capacity and soundlog wait packing remain in the PSG audit
field note. They are not prerequisites for finishing this compiler switch.
Native GUI observations are absent; no display fix is claimed. The separate
PCM stopping investigation remains paused.
