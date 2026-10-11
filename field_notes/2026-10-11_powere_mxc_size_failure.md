# POWERE: size-dependent native MXC failure

## Observed failure

The user's existing POWERE export completed native OPM-to-MML conversion,
then failed compilation with `Compiler exited with -11`. The generated report
selected 7424 us/tick (`@t227`), with a 4 MHz source and target and no PCM
projection. This is not an alternate-clock pitch rejection.

Only existing generated private MML was compiled for diagnosis; source VGM was
not reconverted. No private score contents are included here.

Running MXC v1.01 through the installed run68 with host stdout unbuffered
revealed `ChHのループが閉じていません` at end of input, followed by SIGSEGV.
The prepared score has 97,430 bytes and maximum physical line length 112 bytes.
Every track has balanced repeat brackets (maximum depth 3); track H alone
compiles successfully, as do tracks A through G together. Reordering H before
G or adding a final blank line does not resolve the full-score failure.

## Independent public reproduction

A synthetic score with only raw register writes and a final rest reproduces
the crash without any repeat brackets:

```python
score = '#title "Public size probe"\r\n'
score += ('A ' + 'y32,0 ' * 20 + '\r\n') * (count // 20)
score += 'A r%1\r\n'
```

- `count=14500`: native compilation succeeds, MDX size 43,560 bytes.
- `count=15000`: false unclosed-loop diagnostic on A, SIGSEGV, empty MDX.
- A 102,037-byte score using 10,000 writes and extra whitespace succeeds with
  a 30,062-byte MDX.
- A shorter 78,037-byte input using 15,000 `y8,0` writes fails identically.

This distinguishes encoded-data-size dependence from input text size or real
unclosed repeats. The observed failure lies between roughly 43.5 and 45 kB
for this synthetic case. This is not a documented MDX format limit, and the
exact internal MXC/run68 memory defect has not been identified.
Buffered stdout on the crash explains why the ordinary export log retained
only the exit code.

## Existing compiler workaround

The same generated POWERE MML compiled with the existing helper's
`--compile-only` mmlx path, producing a 54,667-byte MDX. The helper's
`--inspect-commands` parsed it successfully. These are compilation and
structural inspection results, not native playback/ending/display validation.
The diagnostic artifact is in ignored
`outputs/powere_compiler_check_2026-10-11/POWERE.mdx`.

The user can regenerate a separate listening package with the documented
`scripts/export_mdx.py --compiler mmlx --no-vgm` path. No implicit compiler
fallback was added, and no song-loop implementation was started.

## WBIIIA02: additional target-offset capacity failure

The user's WBIIIAC batch has successes for 01 and 03; 02 failed with the same
native process exit -11. Existing prepared MML is 190,332 bytes, maximum line
112 bytes, with balanced repeat brackets and maximum depth 2. Its clock is
10240 us/tick (`@t216`), source and target are both 4 MHz, and no PCM projection
is present. Unbuffered native stdout falsely reports an unclosed repeat on F.

Unlike POWERE, compiling the existing full MML with mmlx also fails, explicitly:
`data inconsistency: MDX track 6 offset exceeds the maximum 0xfffe`.
Compiling existing channel F separately succeeds with a 50,327-byte MDX;
C alone produces 14,384 bytes, with A/B/D/E contributing additional data.
The full MML has 16,182 raw register commands. These channel-isolation builds
are capacity diagnostics, not playable replacements for the whole song.

This case crosses the target's track-start offset capacity as well as exhibiting
the native compiler crash. A compiler switch alone is therefore insufficient.
Do not describe the capacity failure as pitch-range rejection, a timer-period
problem, or an actual unclosed repeat. No source VGM reconversion or behavioral
fix was made. The user has deferred work on data-size-dependent failures.
