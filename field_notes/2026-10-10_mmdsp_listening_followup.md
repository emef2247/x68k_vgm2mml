# Production listening follow-up and readable export statistics

## User observations

These are user-reported XM6TypeG/MMDSP results. `success` in export results
means artifacts were generated; it does not establish native load, playback,
ending, display or responsiveness. The user copied files to the emulator;
the transferred files were not independently hashed.

| Input group | Native observation |
| --- | --- |
| BOSCON04, BOSCON06, BOSCON08 | Play and stop correctly; GUI animation remains absent |
| Other successful BOSCON exports: 03, 07, 09, 12 | Track buffer insufficient; cannot load |
| BOSCON01, 02, 05, 10, 11 | Export blocked; not native playback failures |
| Public stream94_supply_stop, stream_stopped_supply_restart, stream_supply_only | User reports load error and clicks |
| Other public opm_oki6258 exports | Click-like sounds; possibly brief meter activity, not established animation pass |
| F_A01 | Export blocked in both strict and best-effort |
| ARMBS1 | Plays and animates; sound remains after ending |
| NEMESIS GRA1_01 through GRA1_14 | All play and stop; no animation; MMDSP does not accept controls during playback |

An attached screenshot also shows a PCM-load error for stream_delayed_chip_stop.
Keep this image observation distinct from the explicit three-file list above.
Earlier six-file extended finite_end_tail native playback/ending passes remain
valid; this follow-up concerns production conversions.

## Artifact inspection

No local_only conversion was rerun for this investigation. Existing generated
artifacts were inspected, with private content kept out of this document.

The public stream inputs are arithmetic decoder tests, not listening phrases.
stream94_supply_stop contains a 2-byte sample; its PDX is 770 bytes including
the 768-byte bank table. stream_stopped_supply_restart contains 3- and 4-byte
samples; its PDX is 775 bytes. Actual sample ranges and SHA-256 values agree
with fixture expectations. These bytes are present after the table, not merely
declared. The stream fixtures last fractions of a millisecond to about one
millisecond. Click-like sound is consistent with those durations, but does not
explain or excuse a native load error.

stream_supply_only has no chip PLAY, no PCM note and no PDX reference/file.
That is an intentional stopped-supply source case, not missing audible content.
Other public inputs contain larger samples: long_hold_stop 1024 bytes,
opm_pcm_rates 128 bytes and reset_pan_hold 512 bytes. Their source samples are
constructed byte patterns, so no familiar musical waveform is promised.

The long public basenames are embedded verbatim as PDX references. Name
resolution after transfer to the emulator is a candidate for investigation,
not a confirmed cause or a claim about a universal filename limit. A useful
next public probe is an unchanged source under a short ASCII basename,
regenerated so its MDX reference and PDX filename agree. Renaming only the PDX
after compilation is not equivalent.

F_A01 is blocked by ADPCM3 versus the currently required ADPCM4 codec and a
262888-byte sample beyond the verified 65535-byte projection scope. The latter
is an implementation verification boundary, not a claim that extended MDX
cannot represent larger samples. BOSCON01/02 diagnostics include MDX offset
capacity failure. Historical `_errors` logs can be stale; current results.csv
and assessment must determine current status.

ARMBS1 has no PCM. Its compiled tracks have finite ends, so its residual sound
needs FM ending/source-boundary investigation; PCM packing cannot explain it.
Read-only command analysis finds timed NOTE commands in BOSCON06 and GRA1_01,
including many hold chunks. Their timer is 256 microseconds per tick, while
animated ARMBS1 uses 8192 microseconds. Interrupt load is a hypothesis for
display/responsiveness, not established causation. Do not coarsen timing or
discard boundaries without inspecting source, Segment and target timing.

## Export report

export_mdx.py now writes `<stem>.report.txt` for success, blocked and failed
inputs, with its path in results.csv. It preserves intermediate artifacts.
The report contains one-pass source duration; OPM register-08 requests and
separate operator rising/falling edges; encoded MDX note/hold/rest census;
PDX sample identity against packing inputs; exact rational PCM frequency
mapping counts; projected timing errors; and grouped loss/unverified/fail codes.

The Rust helper's `--inspect-commands` reads the compiled MDX without replay.
Counts describe encoded commands, not expanded loops or inferred physical
Key-Off events. PCM byte identity is not decoder-state or waveform equivalence.
Independent OPM pitch reproduction and native runtime outcomes are unmeasured
unless separately tested. Missing/old census helpers leave explicit unavailable
statistics, rather than invalidate otherwise generated playback artifacts.

Do not delete diagnostics during this validation stage. User requested eventual
listening-folder cleanup while retaining MML and TXT, after validation finishes.

## Next work

1. Test short-name public source copies to isolate PCM filename resolution.
2. Provide longer authored listening fixtures separately from tiny decoder cases.
3. Inspect ARMBS1 source/target final gate state before changing finite FM endings.
4. Test shared-clock interrupt/load hypotheses with safe timing projections.

Neither compiler switching nor MML control-order changes follow from these
observations alone. No conversion semantics changed in this follow-up.

## Additional user comparison after usage reset

ARMBS1 replay confirms animation/playback and residual sound after completion.
The user supplied vgm-conv OPM versions of all 14 NEMESIS inputs and exported
them through the native OPM route successfully. Multi-dot native filenames
caused MMDSP file-read errors; manually reducing names to one extension fixed
loading in the user's environment. Animation nevertheless remains fixed.
This separates observed name resolution from display behavior, and means the
internal PSG projection is not the sole established cause of absent animation.
The user suggests inspecting update granularity and asks for longer-update VGM
comparisons. Inspect the common OPM-to-MDX timer selection as well as projected
event density; do not conflate a dense event timeline with timer frequency.

Read-only GRA1_01 comparison:

| Path | Source writes | MDX size | Nominal tick |
| --- | --- | --- | --- |
| Native PSG projection | 2595 PSG writes | 13583 bytes | 256 us |
| vgm-conv OPM | 2912 OPM writes | 11741 bytes | 256 us |
| ARMBS1 native OPM | 2391 OPM writes | 1731 bytes | 8192 us |

The diagnostic score reader interprets 2778 note events in the native PSG
projection, including 2769 continuations and nine non-continuation attacks.
The vgm-conv source has four register-08 Key-On requests, all at time zero,
and no falling operator edges. Its MDX has no musical NOTE events; held raw
register playback is represented with rests between controls. ARMBS1 has 514
interpreted notes without split holds. These score-reader counts can include
finite repeat expansion; they are not identical to the report's encoded census.

Optional note normalization requires enough clustered musical attacks and
within-channel intervals. Nine native PSG attacks and the single clustered
vgm-conv onset do not meet those eligibility requirements. Separately,
`infer_clock` checks every observed Segment boundary and the song end, bounds
timing error to six source samples, and rejects coarser clocks that collapse
positive intervals. Therefore normalization abstention alone does not explain
the fine target clock. Do not relax all-control timing preservation just to
make the optional attack-based estimator fit.

## Public comparison prepared

`tests/fixtures/public/opm/clock_listening/CLOCK.vgm` is an original eight-note
FM phrase with volume/pan changes, explicit Key-Off and a final silent interval.
The source is generated from an authored native-MXC 16384-us score, is 2132
bytes and lasts about 8.3886 seconds. Segment onset/release boundaries match
the authored reference within one VGM sample. The ordinary converter selects
8192 us/tick (@t224); it was also compiled with native MXC.

Four controlled reference MDX files use 256, 2048, 8192 and 16384 us clocks.
Their independent decoded physical attacks/releases, pitch, volume and pan
match. They are authored references, not an experimental converter override.
Reference VGM sizes are respectively 99428, 12932, 3668 and 2132 bytes:
wait-command emission can enlarge VGM without increasing musical updates.
All native listening/display/response outcomes remain unverified.

The exporter CLI now keeps canonical converter/compiler evidence under
`_diagnostics/`, byte-identical staging under `_source_inputs/`, and publishes
single-extension MML/MDX/PDX/TXT/optionalVGM under `tracks/<safe_stem>/`.
Portable eight-character ASCII stems remain unchanged; longer/multi-dot names
receive deterministic short names. Title behavior and PCM internal references
are preserved by naming the staged source before conversion, not patching MDX.
`listening_manifest.json` and results.csv retain original names and hashes.
Owned publications are verified before replacement; unowned/modified files and
case-insensitive name collisions are diagnosed. Native filename compatibility
still requires listening; this is a structural correction, not a GUI fix.

## Validation of this follow-up

- Export/report/listening tests: 42 passed, including stale statistics,
  PDX payload identity, namespace ownership, title preservation and setup
  failure preserving previous publications.
- Rust command-census tests: 13 passed; release helper rebuilt.
- Actual public PCM export: 11/11 succeeded with short names and TXT reports.
  Separate audit verified unchanged staged source bytes, publication hashes,
  single-extension names, finite decoded commands and matching PDX references;
  all occupied PDX ranges were valid. Native load/playback remains unverified.
- Actual public CLOCK export: 1/1 succeeded through native MXC, with eight FM
  NOTE commands and selected @t224. Four reference clocks' independent score
  comparisons and source Segment boundary assertions passed.

The new short-name public PCM package is `outputs/listen/public_safe_names/`.
The ordinary long-update conversion is `outputs/listen/clock_native/tracks/CLOCK/`.
The four clock references are `outputs/listen/clock_listening_reference/`.
No local_only conversion or automatic diagnostic cleanup was performed.
