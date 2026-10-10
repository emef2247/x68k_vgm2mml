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
