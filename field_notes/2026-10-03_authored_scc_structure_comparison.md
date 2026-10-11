# PSG/SCC full-pipeline comparison on authored-MML exports

## Question and scope

The previous private-case-166 comparison was incomplete because expensive searches
were interrupted, not because its source bytes were unparseable. Its VGM is
about1.25MB, but the relevant cost is the expanded note/command sequence and
repeat/macro candidate search, not file size alone. An unused legacy Segment
repeat search was removed from source-plan rendering in the preceding change.
The remaining full enhanced-macro paired comparison on private-case-166 has not been
completed. Its successful legacy-macro diagnostic must not be substituted for
that missing measurement.

For a bounded follow-up, use only <private-reference>/private-collection-017 inputs: private-case-100,
private-case-103 and the six available private-case-099_with_sync_mark VGMs. According to the
user, these were exported from authored MGSDRV MML reconstructed by an SCC
analysis program. Do not pool these with <private-reference>/private-collection-022 game captures.
This is eight paired inputs, not a regression of all17 original private-collection-016 songs.
The long unsplit private-case-099 is not converted in this comparison.

Both variants use enhanced macros, ordinary60Hz target ticks, default sync
policy and automatic allocations. --normalize-lengths is absent. The only
changed policy is the PSG/SCC shared envelope bank: earlier envelope-first
versus structural source-loop-first. OPLL policy is held fixed. This isolates
the effect of PSG/SCC ordering; it is not a combined legacy-loops/legacy-macros
versus all-new-defaults comparison.

All event/PASS/Segment, source-loop, envelope, target and macro dumps are kept.
Inputs and reference MMLs are read-only. The production converter was not
changed in this follow-up.

## Final enhanced-macro MML sizes

Decoded final MML characters include comments, blank lines and definitions;
line endings are read as LF. All generated files here are ASCII, so character
and byte counts coincide. Both variants compile in every row with MGSC1.11
via mgsc-js2.0.0, without Track buffer full or allocation overrides.

| Input | Envelope-first | Loop-first | Saved |
| --- | ---: | ---: | ---: |
| private-case-100 | 4117 | 4117 | 0.00% |
| private-case-103 | 8749 | 8313 | 4.98% |
| private-case-099 split VGM01 | 4189 | 4187 | 0.05% |
| private-case-099 split VGM02 | 6345 | 6315 | 0.47% |
| private-case-099 split VGM03 | 7220 | 7261 | -0.57% |
| private-case-099 split VGM04 | 8443 | 8297 | 1.73% |
| private-case-099 split VGM05 | 13789 | 13789 | 0.00% |
| private-case-099 split VGM06 | 9149 | 9053 | 1.05% |
| Total | 62001 | 61332 | 1.08% |

The six split VGMs alone total49135->48902 characters, a0.47% reduction.
Five inputs shrink, two are unchanged, and one grows41 characters while still
compiling. Conversion subprocess times span4.08..52.13 seconds; none reaches
the240-second per-run bound. Their summed subprocess conversion time is328s.

private-case-103 has24->18 sync comments. Excluding comment-only/blank lines and
trailing comments, its code text is7578->7424 characters, a2.03% reduction.
Both have20 envelope definitions occupying671 characters and32 macros.
Thus the4.98% total saving includes fewer sync comments and is not all musical
command compression. Character counts remain the user's source-size metric;
successful compilation is checked separately.

## Preservation checks

For all eight pairs:

- Native PSG/SCC Segment dataclass fields, including register periods, source
  timestamps/vgmticks, volume and waveform evidence, are identical. Target
  annotation columns such as envelope IDs and loop paths are compared separately
  or excluded from this native-field comparison.
- Expanding final MML loops/macros and applying software-envelope holds gives
  the same effective pitch, octave, volume, PSG mode/noise/hardware-envelope
  settings and SCC waveform ID at every ordinary source tick in both variants.
- Each variant's effective timeline also matches its native Segment timeline
  under the existing target pitch interpretation.
- All16 final MMLs compile successfully; no new buffer failure is hidden by
  manually editing tracks or allocations.

These checks do not establish sample-exact frequencies, oscillator phase,
release tails, or audio equivalence. No MGS->VGM roundtrip or native WSL compiler
run is performed here. Existing reversible source-plan and macro expansion
assertions also run during conversion.

## What the intermediate structure shows

The selected source tree and final physical bracket syntax are distinct.
Counting brackets includes generated macro bodies and their continuation
lines, excludes metadata/comments, and does not multiply definitions by calls.

| Input | Source markers (new) | Source depth (new) | Final physical loops old->new | Final depth old->new |
| --- | ---: | ---: | ---: | ---: |
| private-case-100 | 16 | 1 | 5->5 | 1->1 |
| private-case-103 | 106 | 2 | 53->52 | 2->2 |
| split VGM01 | 7 | 1 | 4->3 | 1->1 |
| split VGM02 | 86 | 2 | 15->17 | 2->1 |
| split VGM03 | 56 | 2 | 14->15 | 1->1 |
| split VGM04 | 46 | 3 | 33->30 | 2->2 |
| split VGM05 | 65 | 2 | 17->17 | 1->1 |
| split VGM06 | 82 | 3 | 33->33 | 2->2 |

The old bank has no equivalent source-marker CSV, so its zero report count
must not be described as zero loop detection. It already emits target loops.

For private-case-103, stored volume-curve representative occurrences fall from the
1295 expanded occurrences to632 before envelope selection. For split VGM04
they are404->187 and VGM06 is474->268. These are counts of observed curve
occurrences, not discarded notes or a corresponding MML saving percentage.
All original occurrences are rendered. Longer curves retain envelope priority.

Repeated source keys do not guarantee one identical target command body:
initialization, inherited command state and later macro allocation affect
physical output. Projection keeps differing commands expanded, and brackets
are emitted only when their exact expansion is preserved and saves text.
Consequently more source structure can coexist with fewer physical brackets,
the same macro count, or almost unchanged final size. Structure is useful but
the final character/compile checks remain necessary.

## Authored reference and split-file limits

LF-normalized original reference syntax:

| Reference | Characters | Physical loops | Maximum lexical depth | Macro definitions |
| --- | ---: | ---: | ---: | ---: |
| private-case-099.mml | 21094 | 63 | 2 | 17 |
| private-case-100.mml | 3201 | 13 | 1 | 0 |
| private-case-103.mml | 3889 | 52 | 3 | 5 |

These are authored-source syntax counts, not interchangeable with expanded VGM
duration or generated-source size. In particular, private-case-103 includes indefinite
loops; the capture is finite. The score auditor fully parses private-case-100 and
finds13 loops: eleven repeated twice and two repeated15 times. It cannot fully
audit private-case-099's multi-argument hardware-vibrato syntax or private-case-103's macro
call durations. Physical syntax inspection is reported instead of silently
dropping those constructs. Exact reference loop-window recovery is not claimed.

The first inventory mixed two generations of split MML. The user clarified
that run_convert_to_sync_blocks.sh invokes mml_sync_split.py and cuts at shared
top-level loop boundaries, preserving contained loops. The98 numbered files
previously observed came from run_convert_to_sync_blocks_v2.sh, which invokes
mml_sync_split_v2.py to permit splitting even without suitable loops. They
were not the reference MMLs used to export the six available VGMs. Retract
the earlier suggestion that these six VGM captures lack corresponding loop
blocks: the discrepancy came from the mixed reference-file generations.

After the user regenerated private-case-099 with the first script, the directory has
six numbered MMLs and six matching VGMs, without extra numbered files. The
recomputed marks are0,886,2166,3126,5046,6966,8526, exactly matching all six MML
block comments. Nominal block lengths are886,1280,960,1920,1920,1560 score steps
at tempo75. VGM-header durations exceed those nominal60Hz tick counts by
3.12..4.24 ticks. This coarse duration check is consistent with the new pairing;
it does not establish event-by-event or sample-exact equivalence. The existing
eight-input conversion-size comparison above remains valid because it consumed
the unchanged VGM files, not the previously mixed split MMLs.

Read-only inventory of all17 original songs confirms that all ten songs with
two or more loop-boundary blocks have matching MML/VGM files for every block:

| Song | MML/VGM block pairs |
| --- | ---: |
| private-case-099 | 6 |
| private-case-101 | 2 |
| private-case-102 | 3 |
| private-case-104 | 3 |
| private-case-106 | 2 |
| private-case-108 | 2 |
| private-case-109 | 3 |
| private-case-110 | 7 |
| private-case-111 | 4 |
| private-case-112 | 3 |
| Total | 35 |

All35 numbered MML interval comments agree with independently recomputed
loop-boundary marks, and all35 VGM headers are valid. Header durations differ
from nominal score-derived durations by+2.49..4.92 ordinary ticks; no coarse
duration outlier was found. For the15 folders with their own splitter script,
its analysis functions were used without invoking main or writing fixtures.
private-case-104 and private-case-110 lack the shell wrapper and local splitter copy at inspection time;
the private-case-099 splitter's analysis agrees with their existing block intervals.
Eight multi-block songs have wrappers; including those two additional paired
datasets gives the ten-song/35-block total. Single-block private-case-100 has no split
VGM, outside the user's two-or-more-block criterion. Its original VGM exists.

This inventory supplies explicit filename/score-window pairs for subsequent
reference-loop analysis. The inventory itself did not run conversions; the
subsequent35-block conversion benchmark is recorded in the separate follow-up
note linked below. Prefer these loop-boundary MMLs over v2 fine-grained splits
when evaluating authored loop recovery.

The references still show room for higher-level reconstruction: generated
private-case-103 has depth2 versus authored depth3, and full reference001 uses reusable
drum-control recipes. This experiment confirms a small full-pipeline benefit
from the ordering change; it does not demonstrate reconstruction of all authored
loops/macros, nor that unsplit private-case-099 now fits its track buffers.

## Artifacts and next bounds

Private output directory on the Codex host: <private-output>/private-collection-016-source-structure.
comparison.csv and comparison.json retain all final metrics; each input has
legacy/structural MML, MGS, conversion/compile logs and full --dump-passes CSVs.
references.json retains separate authored-source syntax statistics and audit
limitations. Local harnesses are outside the repository; private fixture
contents are not copied into this note.
sync-pairs.csv/json record the corrected17-song inventory, source marks,
per-block MML intervals, file existence and VGM-header duration checks.

Subsequent user-requested follow-up completed the35 paired loop-block conversion
benchmark and reference-window audit. See2026-10-03_scc_loop_block_benchmark.md
for those results; the earlier inventory-only limitation is superseded for the
35 blocks. No full17-song unsplit catalog, long unsplit private-case-099, enhanced-macro
private-case-166 pair or audio comparison has been run. Do not infer those results from
the eight cases or35 blocks.
