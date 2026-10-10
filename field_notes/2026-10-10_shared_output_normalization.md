# Shared structured MDX output normalization

The user ended the authored clock_control experiment: all cases are inaudible,
counters advance, and MMDSP remains responsive. Further pattern debugging is
canceled. This supports responsiveness only; it does not prove the timer cause
of frozen animation. See the clock baseline failure note.

## Background and ownership

Reviewed the MSX [normalization design](https://github.com/emef2247/msx_vgm2mml/blob/main/docs/note_normalization.md),
[implementation](https://github.com/emef2247/msx_vgm2mml/blob/main/py/note_normalization.py)
and [regression record](https://github.com/emef2247/msx_vgm2mml/blob/main/field_notes/2026-10-02_normalize_lengths_regression.md)
against their local copies. The three user-supplied design conversations were
also read: [first](https://chatgpt.com/share/6aca1a55-c6b8-83e8-940d-2fc574796c24),
[second](https://chatgpt.com/share/6aca19c5-b380-83ec-ac47-85cdd99c2432),
[third](https://chatgpt.com/share/6aca19f0-f0b4-83ec-b780-9ef72fdd056a).
Their relevant context is transparent source analysis, independent reference
validation, immutable Segment/PCM evidence, distinct timbre projection and
target formatting, and fallback within the same structured projection.
Historical proposals are background, not instructions to enlarge this change.

The current estimator's 12/6 values are musical score subdivisions. They are
not a six-source-tick pruning rule. Its 735-sample maximum correction is one
nominal 60 Hz frame, not a required minimum MDX timer period. Baseline clock
inference and normalized candidate checks include intervening control and
PCM boundaries, not just note-on IOI. Do not describe 256 us as proof of a
short-note source or as a proven cause of MMDSP failure.

## Implementation

PSG FM/additive and SCC structured output already enter the canonical OPM
normalizer; tests now exercise successful SCC and additive PSG adoption as
well as the existing FM PSG and original-source rejection checks. Registers
holding remains an explicit compatibility path; no new articulation option.

Removed the blanket PCM bypass. Logical PCM playback starts join OPM attacks
as estimator anchors. PCM start/end/all control boundaries share candidate
validation with OPM controls, Key edges, Segments, source end and valid loops.
Raw byte supply is not a musical anchor. All positive boundary intervals must
survive and corrections must remain within the fitted tolerance. Sparse and
irregular fits still abstain; no unfitted coarse-clock quantization was added.

The selected multiplier now drives PCM projection as well as FM. Candidate-only
PCM projection/score failure falls back atomically to baseline structured timing;
ordinary source eligibility errors retain their existing diagnostics. Before
MML includes the baseline PCM track and PDX header when representable. Source
Segment/PCM IR and encoded samples remain unchanged. The normalization CSV
labels OPM/PCM/shared evidence and preserves before/candidate timing.

## Public outcomes

Actual export of all 16 `public/opm/from_fm` files succeeds with native MXC:
MML, MDX and replay VGM generated. Source/name hashes and published artifact
hashes were independently checked. `mdxinfo -u -H` reports Success, matching
titles and nine tracks for all 16. Source routing now distinguishes silent
compatibility setup while retaining used-command evidence; see the separate
source initialization note.

All 16 enter normalization, but none adopt it: 12 have no confident shared
clock, four would collapse positive source intervals. All remain at 256 us.
The four rejected fits are block_boundary, custom_voice, highlow_range and
rhythm_mode_toggle. This fixes conversion failures and PCM participation;
it does not fix the actual fine-clock/animation issue.

Actual public OPM/PCM export succeeds 11/11 with best-effort and no replay.
These short fixtures all abstain for insufficient clock evidence. mdxinfo
reports Success and resolves all requested PDX files. Its known zero-tone-offset
limitation reports Tracks=-1 for ten packages, so it does not certify their
extended track mode. Existing typed layout checks remain independent evidence.

Authored automated cases cover accepted OPM, PSG FM/additive, SCC, PCM-only
and mixed OPM/PCM correction, unchanged source evidence/PDX payloads, explicit
OFF and positive-boundary/score fallback. No local_only conversion was run;
native audio/display/end verification remains the user's check.

Reproduction:

```sh
python scripts/export_mdx.py tests/fixtures/public/opm/from_fm \
  --outdir outputs/listen/opm/from_fm
python scripts/export_mdx.py tests/fixtures/public/opm_oki6258 \
  --outdir outputs/listen/normalization_pcm_public --no-vgm --pcm-policy best-effort
```

Listening files are under `tracks/<safe_stem>/<safe_stem>.mml/.mdx/.pdx/.txt`;
full diagnostics remain under `_diagnostics`. The original source mapping is
in results.csv and listening_manifest.json. Independent audit metadata and a
short normalization_summary.txt are retained in each output root.
