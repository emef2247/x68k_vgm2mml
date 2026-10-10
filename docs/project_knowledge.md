# VGM → Structured MML

## Project Knowledge & Design Principles

This document records **stable project principles and durable domain
knowledge** for `emef2247/x68k_vgm2mml`.

Keep this file small enough to read before changing conversion behavior.
Implementation history, measurements, fixture-specific results, rejected
experiments, and dated observations belong in `field_notes/` or focused
documents under `docs/`.

Not every statement is a formal specification. Distinguish:

* confirmed facts / specifications
* implementation decisions
* measurements
* hypotheses
* unresolved questions

Do not silently promote a hypothesis, test expectation, or
fixture-specific observation into a project invariant.

Export statistics must separate generated artifacts, encoded-byte identity,
projected frequency/timing checks and native load/playback/ending/display.
Raw Key-On/Off requests, operator edges and encoded MDX NOTE/hold counts are
different measurements. Do not combine them into an unsupported fidelity
percentage; explicitly label independent comparisons not yet performed.

---

# 1. Project Goal

`x68k_vgm2mml` converts VGM sound-chip data into human-readable,
editable, and structurally meaningful musical representations.

The primary orientation is **X68000 music**.

The default native source/target path is:

```text
OPM / YM2151 VGM
        ↓
Native OPM Analysis
        ↓
Musical Segments
        ↓
Structural Analysis
        ↓
MDX MML
```

OPM/YM2151 is the primary native source and MDX MML is the default output
format. The frontend selects the supported native OPM/PCM or PSG/SCC-to-OPM
route from actual VGM command usage. An unused clock declaration is not a
source-selection request. Used unsupported chips, combinations and streams
must be diagnosed rather than silently omitted. Existing inactive compatibility
initialization handling must remain explicit in the source inventory.

Canonical FM conversion generates MML, not MDX/PDX binaries. A matching stem
does not establish ownership of an adjacent MDX/PDX reference. Remove previous
PCM binaries only when their generated assessment, saved path and SHA-256 match.
Preserve other binaries, distinguish them from current artifacts, and require a
separate output directory if typed PCM generation would overwrite them.

Existing PSG/SCC/OPLL → MGSDRV MML functionality inherited from
`msx_vgm2mml` is retained as a **proven compatibility path**. It should
remain usable, but it is not the primary design center of this repository.

The project may also contain analysis or target paths for additional
chips and formats.

The goal is **not merely to produce output that sounds similar, compiles,
or passes a regression test**. The project aims to preserve observable
source-chip behavior while reconstructing useful musical structure and
keeping important transformations inspectable.

Conceptually:

```text
VGM
 ↓
Raw Register Writes
 ↓
Reconstructed Chip State / Events
 ↓
Inspectable Analysis Passes
 ↓
Musical Segments
 ↓
Structural Analysis
 ↓
Target Projection
 ↓
MDX MML / MGSDRV MML / MS2 / other targets
```

The implementation does not have to mirror this diagram one-to-one.
Do not refactor merely to make module boundaries match it.

---

# 2. Canonical Frontend

`vgm2mml.py` is the **canonical user-facing conversion entry point**.

Normal conversion functionality should be reachable through
`vgm2mml.py` using explicit source/target/output options where necessary.
`--target` selects the output format (MDX or MGSDRV), not a chip or synthesis
algorithm. Deprecated `opm`/`opm-additive` aliases preserve existing projection
defaults. Source routing, projection model, scoped fidelity policy, target
notation and diagnostics are separate concepts. The held-register PSG/SCC
compatibility projection is an internal mode; no public articulation switch
is required merely to express that distinction.

Target-specific scripts under `scripts/` may exist for:

* experiments;
* diagnostics;
* regression analysis;
* fixture preparation;
* comparison;
* one-off development tools.

They must not silently become independent production conversion
frontends.

Do not create a second normal VGM conversion entry point merely because
a new target or interpretation is being implemented.

If target-specific logic becomes part of normal conversion, integrate
that capability into the canonical `vgm2mml.py` pipeline while keeping
target-specific implementation details in appropriate modules.

---

# 3. Primary Rule: Intermediate Results Are First-Class Artifacts

Generating inspectable intermediate results is a primary project
requirement, not merely a debugging aid.

A human should be able to determine, where relevant:

* which source register event caused a musical event;
* what chip state existed at that point;
* where Key-On/Key-Off or trigger edges occurred;
* which source pitch/volume/instrument/waveform values were present;
* when an event became an interpreted Segment;
* when musical structure was inferred from Segments;
* which information was changed or discarded by target projection.

CSV or equivalent pass output should favor human traceability over
compactness. Redundancy is acceptable when it makes an analyzed event
self-contained.

> Redundancy that improves traceability is acceptable.
> Loss of source information for structural elegance is not.

Do not remove, merge, split, normalize, or reshape an intermediate
representation merely because doing so makes final output cleaner or
makes a regression test pass.

**Tests are evidence, not the objective.** If a test conflicts with the
information-preservation model, first determine whether the
implementation, the test expectation, the structural interpretation, or
the target projection is wrong.

When an intermediate schema must change, explain the semantic reason and
what information is added, removed, or reinterpreted.

---

# 4. Transformation Boundaries

Keep these responsibilities conceptually separate.

## 4.1 Raw Register Writes

Preserve what was written to the source chip, when it was written, and
ordering between writes.

Avoid musical interpretation here.

## 4.2 Chip-Specific State / Events

Reconstruct the meaning of register writes using the native semantics of
the source chip.

Examples:

* OPM: KC/KF, operator parameters, partial Key state and shared controls
* OPLL: FNUM, BLOCK, instrument, volume, Key state
* PSG/SSG: tone period, mixer, noise, fixed/hardware envelope state
* SCC: frequency, volume, waveform state
* rhythm modes: trigger and per-instrument state

Do not force different chips into a lowest-common-denominator state
schema.

## 4.3 Inspectable Analysis Passes

Analysis may progressively derive higher-level information. Later passes
may repeat earlier fields when this improves human inspection.

A pass is not disposable debug text.

## 4.4 Musical Segments

Segments represent interpreted musical objects or sounding intervals.

This is where concepts such as:

* start/end;
* duration;
* retrigger;
* continuity;
* note identity;
* waveform identity;
* rhythm identity;

may be derived.

A Segment is not a raw register event.

Do not invent information at the event/state stage that can only be
inferred during Segment construction.

Do not split or merge Segments solely to accommodate target notation,
compression, buffer limits, or a regression oracle. Such operations
belong to a later representation unless they reflect a justified change
in musical interpretation.

## 4.5 Structural Analysis

Structural analysis operates **after source semantics and musical
Segments have been reconstructed**.

Its purpose is to discover useful musical organization such as:

* note continuity;
* repeated phrases;
* source loops;
* candidate musical loops;
* repeated control patterns;
* reusable macros;
* sustained musical gestures;
* higher-level relationships between adjacent Segments.

Structural analysis must not rewrite source history.

A Segment boundary is evidence about interpreted source behavior. It is
not automatically a required MML note boundary.

Likewise, several Segments may contribute to one higher-level musical
gesture when continuity is justified.

Structural analysis should preserve mappings back to the Segments and
source events from which the structure was inferred.

## 4.6 Target Projection

The target stage decides how interpreted musical information and
structure can be represented in MDX MML, MGSDRV MML, MS2/MAmidiMemo, or
future formats.

Target limitations and conveniences must not rewrite source history.

Information loss should occur as late as practical and should remain
inspectable.

---

# 5. VGM Is a Register Event Stream, Not a Score

A VGM contains register writes and timing information, not conventional
musical notation.

Potentially meaningful information includes:

* Key-On / Key-Off timing
* KC/KF, F-number, BLOCK or tone-period changes
* instrument and volume changes
* operator parameter changes
* mixer, noise and envelope state
* SCC waveform changes
* retrigger behavior
* pitch changes and portamento-like behavior
* register-write ordering
* repeated writes that appear musically redundant

Do not aggressively merge or normalize events merely because they
eventually produce the same note.

A sparse-looking event stream may be correct. Preserve event sparsity
unless there is evidence that it is an artifact.

Conversely, do not assume every register-state change represents a new
musical note.

The transformation from register events to musical structure is an
explicit interpretation stage.

---

# 6. Preserve Evidence and Derived Meaning Separately

Whenever practical, preserve both:

1. the source-chip representation; and
2. the physical or musical quantity derived from it.

For example, Yamaha FM pitch analysis may retain:

```text
KC / KF
```

or, for chips using that representation:

```text
FNUM
BLOCK
```

alongside:

```text
frequency_hz
musical_note
```

For PSG, retain source tone period when deriving frequency.

For SCC, retain waveform data or a stable waveform identity.

Derived values must not silently replace source evidence.

Unknown or unwritten source state must remain unknown unless an explicit,
documented reset assumption applies.

Do not fill absent fields with invented values.

---

# 7. Timing Is Source Evidence

VGM waits are source timing evidence.

Preserve native timing before target quantization.

The shared VGM source clock accumulates wait samples as integer samples
at 44100 Hz. Chips share the same stream origin; do not rebase each chip
at its first write.

Same-sample writes remain ordered.

A physical sub-tick interval must not disappear merely because a later
musical or target projection rounds it to zero.

A source timestamp, target tick, musical duration, and playback-driver
frame are different concepts.

Do not silently substitute one for another.

Tempo, quantization, grid inference, and target duration encoding are
interpretations. They are not source facts.

See `docs/vgm_timing.md` for implementation details and measured
limitations.

---

# 8. Key Edges, Retrigger, Continuity, and Zero-Length Events

Retrigger and continuation are distinct.

Retain enough evidence to determine whether:

* a note was newly triggered;
* an existing sounding state continued;
* pitch/state changed while the key remained active;
* an operator mask changed;
* a new Segment is justified;
* a higher-level musical gesture may continue across a Segment boundary.

Do not equate zero target duration with an irrelevant source event.

Same-tick or zero-length events may contain real Key or rhythm edges.

For OPLL, distinguish an inferred musical `onset` from a real source
`key_on_edge`. Volume recovery or another inferred onset is not
permission to restart a hardware envelope.

For OPM, preserve partial Key transitions and do not invent a complete
Key-On merely because target notation is easier that way.

Do not merge a real same-pitch Key-Off/Key-On sequence merely because the
resulting pitch is unchanged.

How a target represents an unrepresentable sub-tick event is a
target-stage decision. The source evidence must remain available.

---

# 9. Chip-Specific Durable Semantics

## 9.1 OPM / YM2151

OPM/YM2151 is the primary native FM source for this repository.

Native OPM analysis must preserve OPM semantics rather than invent
OPLL-like FNUM/BLOCK or preset voices.

Preserve where relevant:

* all four operator identities;
* KC/KF;
* Key-On/Key-Off state;
* partial operator Key masks;
* algorithm and feedback;
* operator parameters;
* pan;
* PMS/AMS;
* LFO and shared controls;
* noise state;
* same-time transitions;
* register ordering;
* unknown/unwritten state.

Parameter changes must not create artificial Key-Ons.

A held OPM note may contain multiple source-state changes without
representing multiple musical attacks.

Segment boundaries created by parameter changes must therefore not be
translated mechanically into separate MDX notes joined by ties.

MDX rendering should consume interpreted musical continuity and target
projection, not merely serialize each Segment independently.

Detailed OPM state/target behavior belongs in `docs/opm_segments.md` and
`docs/opm_mdx.md`.

## 9.2 OPLL / YM2413

Pitch uses FNUM and BLOCK; preserve both when available.

OPLL volume direction is inverted relative to conventional loudness:

```text
VOL = 0   -> loudest
VOL = 15  -> quietest / near silence
```

Register writes need not arrive in convenient note-oriented order.
Reconstruct effective state without assuming all parameters precede
Key-On.

User-defined patch registers are meaningful source data. Do not silently
replace them with perceptually similar presets.

OPLL rhythm trigger edges and channel 6--8 pitch state should be
preserved before target projection.

The final MGSDRV layout may differ between melodic mode and rhythm mode,
but layout selection is a target concern and must not delete source
Segments.

## 9.3 PSG / SSG

PSG state is not "OPLL with different parameters."

Preserve tone period, tone/noise enable state, noise period, mixer state,
fixed volume, and hardware envelope state as required for interpretation.

Noise and hardware envelope behavior are musical source data.

If the target needs IDs, macros, reconstructed commands, or conversion
to another chip family, retain decoded source state in an earlier pass.

## 9.4 SCC

Programmable waveform data is first-class source information.

Preserve waveform bytes or a stable identity, timing of waveform changes,
channel use, pitch, and volume where relevant.

Exact equality may be used for stable deduplication; stronger
normalization requires explicit justification.

---

# 10. Rhythm Semantic Layer

Where a common musical rhythm vocabulary is useful, use:

```text
BD
SD
TOM
HH
CYM
RIM
```

This vocabulary describes musical meaning, not source implementation.

Source-specific terminology may still be retained in diagnostic/source
fields.

Rhythm event/state representations should preserve source trigger state,
timestamp, volume, source pitch fields and pan where applicable.

Segment construction may derive sounding intervals later.

Do not infer duration earlier than the available evidence justifies.

---

# 11. Source Structure, Patterns, Envelopes, and Compression

Pattern detection and compression must operate without destroying the
information-preservation pipeline.

A repeated candidate is evidence of structural similarity, not automatic
permission to rewrite source Segments.

Prefer reversible structural plans and retain mappings from patterns,
occurrences, envelopes, loops, or macros back to the original
Segments/events.

Target loops/macros may be selected only when their expansion preserves
the required target command semantics.

Do not introduce new note boundaries, attacks, state resets, or
quantization merely to improve compression.

For software-envelope extraction, do not invent unobserved tails.

Source volume trajectories and attack/restart semantics remain
authoritative.

Target output size and driver/compiler limits are real constraints, but
solving them belongs at or near target projection.

Shorter MML is not evidence of a better conversion.

See `docs/melody_patterns.md` and focused field notes for current
algorithms and experimental results where those documents are retained.

---

# 12. Source Loops and Target Loops

Declared VGM loops are source structure and must be preserved without
inventing a Key-On at the loop boundary.

Structural loop candidates should remain reversible until target
selection.

Overlapping or nested alternatives may be useful to later macro or loop
selection.

Compiler acceptance, MML character count, compiled size, and
musical/source equivalence are separate validation dimensions.

Success in one does not prove the others.

See `docs/vgm_loop.md` for VGM loop details.

---

# 13. Source Interpretation vs Musical Restructuring

`vgm2mml.py` preserves source timing and event semantics through native
analysis and Segment construction.

Musical quantization, normalization, continuity reconstruction, pattern
detection, and restructuring belong to explicit later analysis or
target-projection stages.

Keep this distinction explicit:

```text
source-faithful interpretation != intentional musical restructuring
```

A cleaner or more conventional MML representation does not justify
changing native source evidence.

Likewise, source Segment boundaries do not automatically define the
structure or token boundaries of the final MML.

Do not create a parallel conversion frontend solely to implement a
different structural interpretation of the same VGM input.

New structural approaches should operate as explicit stages within the
canonical conversion architecture.

---

# 14. MDX MML Is a Musical Target, Not a Segment Dump

MDX MML generation must not be implemented as a mechanical one-to-one
serialization of Segment rows.

In particular:

```text
Segment -> MML fragment -> tie -> next Segment
```

is not a general model of musical reconstruction.

Segments exist primarily to preserve interpreted source state and
boundaries. MDX MML should instead represent the reconstructed musical
performance as naturally and structurally as the available evidence
allows.

The MDX path should distinguish at least:

```text
source/state change
musical attack
musical continuation
pitch change
target control change
note termination
structural repetition
```

A source parameter change during a held note does not automatically
require a new note token.

A Segment boundary does not automatically require a tie.

A tie is an MDX/MML representation choice, not a generic relationship
between adjacent Segments.

When ordinary MDX notation cannot faithfully express a meaningful source
behavior, explicit target controls may be used where justified. Such
controls must remain traceable to source evidence.

Musical structure should be reconstructed before textual compaction.

Do not optimize an incorrect flat representation merely because it can
be made shorter with loops, ties, or macros.

---

# 15. Target Formats Are Not Canonical Internal Representations

MDX MML, MGSDRV MML, MS2/MAmidiMemo, and future targets have different
constraints.

Target-specific choices may include:

* duration quantization/encoding
* instrument commands
* operator/register controls
* noise/envelope commands
* waveform definitions
* rhythm commands
* ties, rests and gates
* loops/macros
* channel/buffer allocation
* target-specific timing

Do not shape source/state/Segment data solely around one target's syntax.

A target may intentionally approximate or discard information it cannot
represent.

When it does:

1. preserve the source information in an earlier inspectable stage;
2. document or report the approximation where useful;
3. perform the loss in target projection;
4. do not alter earlier representations to pretend the source lacked it.

Existing MGSDRV compatibility remains supported.

MGSDRV syntax references:

* `https://p.gigamix.jp/mgsdrv/MGSDR320.TXT`
* `https://z80.msx.click/index.php?title=MGSDRV_MML_11_JP`

MDX-specific syntax, compiler behavior, and target constraints should be
documented in focused MDX documentation rather than assumed from MGSDRV
behavior.

Current MDX scope excludes macroization because source macro preprocessing is
compiler-specific. Reuse proven MGSDRV/shared structural processing where it
preserves native semantics; finite repeats and song loops remain in scope.
Existing MGSDRV macro functionality remains supported. Decompiled MDX MML may
serve as independent structure evidence, but cannot recover source macro names
or act as an exact-text oracle for VGM conversion. See `docs/mdx_reference_mml.md`.

Exact duration spelling and optional target timing correction are separate
operations. Native MDX correction must retain source times and report its actual
timer error; an estimator fit alone does not establish representability. See
`docs/opm_note_lengths.md` for the current default-on structured MDX implementation
and fallback. Non-adoption keeps the same structured renderer and baseline
clock/projection; it does not select legacy/registers notation. Explicit
`--no-normalize-lengths` disables correction. MGSDRV correction remains opt-in.
Projected PSG/SCC output must check cumulative timing against original source
boundaries as well as intermediate OPM boundaries before adopting correction.
PCM-only and OPM+PCM output use that same target normalization stage: logical
playback starts contribute anchors, while playback/control boundaries constrain
one shared timer. Raw supply cadence and encoded bytes remain source IR.
Candidate-only projection/score failure falls back for both FM and PCM; source
eligibility errors are not hidden. The estimator's 735-sample bound is a timing
error limit, not a minimum interrupt period; its 12/6 grids are musical score
subdivisions rather than a short-source-interval deletion rule.

---

# 16. Validation: Correctness Has Multiple Meanings

Keep these objectives separate:

**Register correctness**
Reconstruct source-chip state and behavior accurately.

**Musical correctness**
Represent the intended performance usefully.

**Structural correctness**
Infer continuity, repetition, loops, and other musical organization
without contradicting source evidence.

**Target correctness**
Produce valid target data within target constraints.

Also distinguish:

* audible similarity;
* source behavioral equivalence;
* target command equivalence;
* musical equivalence;
* textual optimization;
* compiled-size optimization.

A final MML file, successful compilation, matching event count, or
passing test suite is not sufficient by itself to prove conversion
correctness.

For non-trivial behavior changes, inspect the relevant intermediate
results before and after the change and validate more than one
representative piece where practical.

Real/reference playback, emulator behavior, compiler roundtrips,
hardware observations, code inspection, and subjective listening are
different kinds of evidence.

Record which kind supports a conclusion.

Do not overfit a general rule to one song or fixture.

---

# 17. Tests and Fixtures

Fixtures should make specific behaviors reproducible and, where
practical, cover the relevant layers:

```text
source VGM
raw/state trace
analysis pass
Segments
structural interpretation
target projection
target output
```

Do not blindly update expected artifacts when a regression test fails.

First determine whether:

1. the implementation violated source semantics;
2. the interpretation/Segment logic is wrong;
3. the structural interpretation is wrong;
4. the target projection is wrong;
5. the test expectation encodes obsolete or incorrect behavior.

**Never change an intermediate representation solely to satisfy an
expected artifact.**

A fixture is an oracle only for the behavior it was designed and
justified to test.

Private copyrighted source material must not be copied into tracked
documentation or fixtures unless explicitly safe to commit.

---

# 18. Human-Readable Intermediate Output

Intermediate output should favor diagnosis over compactness.

Use explicit names with stable semantics.

Prefer `frequency_hz` for a physical frequency while retaining native
source representations such as:

```text
KC
KF
FNUM
BLOCK
tone_period
```

where applicable.

Do not fill non-applicable fields with misleading values.

Use empty/null values or chip-specific schemas.

Preserve enough timestamps, channel/source indices, Segment IDs,
pattern/occurrence IDs, structural mappings, and other identifiers to
trace target behavior back toward source evidence.

PASS files generated by `--dump-passes` are part of the project's
diagnostic contract, not arbitrary temporary dumps.

---

# 19. Development Workflow

For a non-trivial conversion change:

```text
1. Inspect the existing implementation.
2. Identify the conceptual stage that owns the problem.
3. Inspect representative source/intermediate evidence.
4. Explain current behavior.
5. Form a hypothesis.
6. Design the smallest useful experiment or test.
7. Implement the smallest justified change.
8. Run regression tests.
9. Inspect intermediate results again.
10. Validate structural interpretation where applicable.
11. Validate target output.
12. Record durable knowledge in the appropriate place.
```

Do not jump from a failing final artifact directly to reshaping Segments
or earlier passes.

Before changing established behavior, identify why it exists.

When adding a new target or major target behavior:

1. do not create a new production frontend by default;
2. reuse the canonical VGM reader and native analysis stages;
3. preserve existing intermediate evidence;
4. add target-specific projection only after source interpretation;
5. integrate normal user-facing operation through `vgm2mml.py`.

---

# 20. Documentation Placement

Keep documentation layered so the highest-priority rules remain visible.

## `AGENTS.md`

Only short, always-on operating rules and repository navigation.

## `docs/project_knowledge.md`

Only stable architectural principles and durable chip/domain knowledge
that should guide future work.

## Focused `docs/*.md`

Current design and usage of substantial subsystems, for example:

* timing;
* loops;
* patterns;
* OPM Segments;
* MDX MML;
* OPLL rhythm;
* compatibility targets.

## `field_notes/*.md`

Dated experiments, measurements, fixture-specific findings, regressions,
benchmarks, rejected approaches, and provisional conclusions.

A finding may move from a field note into this file only after it becomes
a stable project principle or durable domain rule.

Do not append implementation history to this document merely because it
may be useful later.

## `handoffs/current.md`

Keep only information needed to continue the **current active work**.

Do not use the handoff as an accumulating project history.

When the active development direction changes, rewrite or prune the
handoff so obsolete work does not compete with the current objective.

---

# 21. Compatibility Paths Must Not Control the Architecture

Inherited PSG/SCC/OPLL → MGSDRV functionality is proven functionality
and should remain operational unless an intentional compatibility change
is made.

Preserving compatibility does **not** mean that the architecture of new
OPM/MDX work must follow historical MGSDRV implementation choices.

Likewise, do not refactor proven compatibility paths merely to make them
look like the new OPM/MDX path unless there is a concrete architectural
benefit and regression evidence supports the change.

The preferred relationship is:

```text
                    ┌─ OPM analysis ── structural analysis ── MDX MML
VGM ─ shared read ──┤
                    ├─ OPLL analysis ──────────────────────── MGSDRV MML
                    ├─ PSG analysis ───────────────────────── MGSDRV MML
                    └─ SCC analysis ───────────────────────── MGSDRV MML
```

Shared infrastructure should be genuinely shared.

Chip semantics and target behavior should remain specialized where their
meaning differs.

---

## 22. PCM source evidence and target projection

PCM source evidence is target-independent. Preserve exact encoded bytes,
source timing, playback/control events, decoder state evidence, and
observed-versus-assumed distinctions without rewriting them to satisfy
MDX/PDX constraints.

Raw → State → Segment/PCM IR → Target boundaries must remain explicit.
Sample identity is based on codec and exact encoded bytes; playback state
and timing are separate. Unknown decoder consumption and effective runtime
behavior must not be inferred from byte equality or nominal duration.

MDX/PDX placement, capacity limits, command encoding, and approximations
belong exclusively to target projection. OPM and PCM share one MDX clock.
Strict conversion rejects known semantic loss; explicit best-effort may
emit lossy artifacts with source-linked diagnostics. Artifact generation
and runtime validation are separate results.

Reference playback evidence must be distinguished from assumptions and
tool-specific behavior. Successful MDX/PDX generation does not establish
native playback equivalence.

Details:
- `docs/pcm_source_and_target.md`
- `docs/pcm_pdx.md`
- `docs/pcm_roundtrip_validation.md`

---

# 23. Final Rule

When uncertain whether to simplify, merge, split, normalize, quantize,
discard, restructure, or reinterpret data:

1. preserve the source evidence;
2. expose it in an inspectable intermediate result;
3. make the interpretation explicit;
4. distinguish source interpretation from musical restructuring;
5. defer irreversible loss until the target stage;
6. ask whether a human can still trace the final result back toward the
   VGM.

If the answer to step 6 becomes "no", the change requires strong
justification.

The central design question is not:

> "How can we make this conversion simpler or make this test pass?"

Nor is it:

> "How can every Segment be represented directly in MML?"

It is:

> "What musical behavior can be reconstructed from the source evidence,
> what information is being changed or lost at each transformation stage,
> and is that interpretation or loss intentional?"

A final target file is not sufficient evidence that the conversion is
correct.

The path from source register stream through interpreted musical
structure to the target must remain inspectable.
# Original-time short output gates (2026-10-11)

Structured MDX normalization may omit complete Key-On to Key-Off gates of at
most 352 original 44100 Hz samples before quantization. Do not classify a
short Segment control slice as a whole short note, or use an already rounded
PSG/SCC intermediate timestamp for the threshold. Preserve original State,
Segment, PCM IR, sample bytes and elapsed song time. Partial/repeated/unclosed
key operations are conservative survivors. Ordinary controls and short rests
may coalesce within the 352-sample boundary budget, retaining ordered Key-Off
and Key-On operations and explicitly reporting lost rest duration. Preferred
fallback multiplier 65 is an output policy, not a chip specification or a
guarantee of minimum interrupt period. Unsupported PCM remains unsupported
even when its playback is short. Native MMDSP behavior requires listening.

