# Native MXC title boundary

## Observation

The locally selected MXC v1.01 silently emits an empty MDX title when the
`#title` payload exceeds 64 CP932 bytes. Authored ASCII and Japanese cases
independently reproduce the boundary: 64 bytes survives; 65 bytes becomes
empty, with exit status zero. This is a byte boundary, not a character boundary.

The adapter invokes `run68 <temporary>/MXC.X SCORE.MML` without native compiler
options. The prepared score retains `#title` and uses CP932 with CRLF. Repeating
the authored cases through this exact invocation reproduced the loss. Thus the
observed title loss occurs inside this compiler/runner combination; it does not
result from the adapter stripping the MML header or selecting a different title
argument. This evidence does not independently establish behavior on real
Human68k hardware or another MXC release.

The bundled MXC documentation describes `-c` for status suppression and `-x`
for octave direction, with no title-length option. Successful `-x` runs had the
same title boundary. The local binary rejected `-c`/`-C`; the adapter uses
neither flag, so that separate documentation/binary discrepancy does not affect
its invocation.

## Narrow adapter remedy

For a generated title exceeding 64 CP932 bytes, restore it only when the native
MDX title is empty. An unexpected short-title or nonempty mismatch fails instead
of being rewritten. Preserve the entire suffix beginning at CR/LF/0x1A byte for
byte, including the PDX name, data-relative offsets, track commands and voices.
Validate the resulting package with the existing MDX parser before publication.

Keep the unmodified native package beside the prepared score and write metadata
with title lengths, hashes, invocation arguments and parser validation status.
This is compiler adaptation after MML generation, not a music transformation.
It does not address MMDSP keyboard/level display behavior.

## Checks and evidence

- `python3 -m unittest discover -s tests/scripts -p test_mdx_compiler.py -v`:
  16 adapter tests pass, including CP932 64/65 boundaries, unexpected mismatches,
  comments, PDX/suffix preservation, failure publication and native evidence.
- Four fresh authored scores passed through the actual native adapter and MDX
  parser, with correct final titles and byte-identical native suffixes.
- Local authored artifacts and probe script:
  `outputs/mxc_title_2026-10-09/recheck/` and
  `outputs/mxc_title_2026-10-09/recheck.py` (ignored outputs).
- Previous authored title/header probes remain under
  `outputs/mxc_title_2026-10-09/`.

Native-runtime display verification remains a separate manual check.
