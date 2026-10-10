# Reference MML compilation and MDX metadata audit

Scope: reference/tool investigation authorized by the user; no conversion,
compiler-adapter or PCM projection implementation change. The supplied reference
data play and stop correctly in XM6 TypeG. Generated data also need correct
MMDSP keyboard/level-meter behavior; audible output alone is insufficient.

## Native MXC baseline

The two original MML files currently present in the selected private reference
tree were passed to the existing `compile_mxc` adapter. Strict CP932 decoding
and re-encoding preserved the original source bytes. Original fixtures were
not edited. Native MXC v1.01 ran via the existing run68 helper.

| Reference | Compilation | Comparison with original MDX |
| --- | --- | --- |
| FF4SIREN | pass | Entire MDX identical, including all nine tracks, tone bank and header |
| RAY2C | compiler rejected input | unverified; no compiled candidate exists |

FF4SIREN native and published MDX SHA256:
`e34545e9358f19e5a97f10a7db1b70f32e8878f0d9eb15e0983f55bccbf97391`.
No title repair was applied in this case. This establishes that the current
native tool/invocation reproduces this working reference exactly. It does not
establish correctness of every generated MML or the separate typed PCM route.

RAY2C's opening comment identifies the source as intended for `note.x v0.07.0`.
This identifies an intended tool, not proof of the original MDX's build history.
Installed MXC v1.01 reports parameter errors in voice definitions and undefined
performance commands; an appropriate note.x tool has not been verified locally.
Do not remove source directives or alter music merely to obtain a successful
compilation.

## `mdxinfo` comparison requested by the user

Built the existing vampirefrog/mdxtools checkout at revision
`9c8539fec2757fcf7c85d1986171b50ebe2ef1e5` and ran:

```text
mdxinfo -u -H <reference.mdx>
mdxinfo -u -H <compiled.mdx>
```

Capture complete stdout/stderr. This version mixes stdout and its `--output`
file for different columns, so capture stdout instead of using `--output`.
Its normal output is tab-separated despite the upstream CSV description.

Compare all 27 content columns, including title and PDX reference text/raw hex,
parse error, sizes, file/data MD5, track count, PCM marker and encoded command
counts. Keep `File`, `Date` and resolved `PDX file` paths outside literal content
equality; check PDX resolution and resolved bytes independently. The PCM marker
and command counts are static inspection results, not execution traces.

For FF4SIREN all 27 content columns matched and both parse results were Success.
The original PDX was copied unchanged beside the candidate MDX. Both paths
resolved a PDX and those PDX bytes were identical. This is reference PDX reuse,
not validation of newly generated PDX or PCM IR.

A diagnostic title-only mutation changed Title, Title hex and file MD5 while
leaving Data MD5 unchanged. The comparison detected it. Keep this diagnostic
copy and private metadata output ignored; it is not a playback candidate.

RAY2C's original MDX/PDX could be inspected/resolved, but metadata equality is
unverified because native compilation failed. Do not call this a mismatch of
two MDX files or a failure of vgm2mml's generated MML.

## Separate current PCM tool route

Inspection of `scripts/export_mdx.py` and the Rust helper confirmed that FM-only
export defaults to MXC, while typed PCM generation compiles FM with mmlx and
attaches the typed PCM plan with the existing MDX builder. The native MXC
baseline does not validate that separate route.

Passing the two unmodified UTF-8 reference MML copies to the current helper's
`--compile-only` entry point failed during mmlx parsing for both. FF4SIREN was
tested with the existing `--pcm-mode standard`; RAY2C used the default layout.
Failures were preserved without adapting either reference. This bounds the
direct reference-MML test; it does not establish a defect in the generated
canonical MML or in the typed PCM serialization. No helper MDX was produced.

The concrete first parser failures are different:

- FF4SIREN line4 is a bare voice-name annotation, without an explicit comment
  marker. Native MXC accepts the original file and reproduces its MDX exactly.
  The mmlx0.2.0 line grammar permits directives, voices, tracks, explicit
  `;`/`/* ... */` comments and blank lines, but no bare annotation line.
- RAY2C line4 is `#tps-all`. Its source also has `#detune`, `#noreturn`, `#wave`,
  `#remove`, `#beep`, `#reste` and `#coder`. The mmlx0.2.0 grammar defines only
  `#title` and `#pcmfile` as file-level directives. Parsing stopped at the first
  unsupported directive; subsequent musical syntax has not been validated by
  that trial. Native MXC's own documentation also lists only those two auxiliary
  directives; its observed failures above are not attributed solely to them.

Thus "reference notation not accepted" does not mean that a difference in basic
note spelling, timing or PCM stopping was established. It is a tool/input-dialect
compatibility result. The user's latest requirement is explicit: reference MML
notation and MDX/PDX format are the expected baseline. Evaluate generated inputs,
tools and tool usage against that baseline; do not redefine correctness around
the helper's narrower accepted grammar.

## Evidence and next allowed work

Ignored artifacts under
`outputs/pcm_stream_2026-10-09/reference_compiler_baseline/` include original
source copies, prepared compiler inputs, native/published MDX, command/tone
CSVs, compiler metadata and failure logs. `mdxinfo/` contains raw TSV/stderr,
parsed JSON, content differences and summary. Per-reference `helper_check/`
contains exact invocation and parser stdout/stderr. Diagnostic audit scripts:

- `outputs/pcm_stream_2026-10-09/audit_reference_compiler.py`
- `outputs/pcm_stream_2026-10-09/audit_reference_mdxinfo.py`

Re-run the latter against the saved compiler baseline with WSL Python:

```text
python3 outputs/pcm_stream_2026-10-09/audit_reference_mdxinfo.py
```

The user resumed reference/tool investigation after restarting the app. Further
read-only investigation of applicable reference syntax, MML/PCM IR handoff and
generated MDX/PDX is allowed. Production implementation remains paused while
the user considers the approach. BOSCON06 stopping and generated MMDSP display
failures are unresolved. No MDX-to-VGM replay or external player repair was used
in this audit. Do not treat metadata equality as proof of native display/stop
behavior, or use PCM1/PCM8 classification as a prerequisite to the user's task.
