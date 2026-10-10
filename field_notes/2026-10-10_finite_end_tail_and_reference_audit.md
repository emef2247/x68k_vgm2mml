# Finite ending, manual stop and original PCM-last reference audit

## Subsequent listening: tail extension fails

The user explicitly confirmed every MDX in finite_end_tail leaves continuing
noise: RATES, RATESF, RATESP, FS432, FS432F and FS432P. This includes both
unchanged original controls, not only the four tail variants.
Extending only FM A or only PCM P therefore did not solve the
reported problem. Noise onset relative to the old/new ending and F7 during the
tail have not been separately reported. Static validation stays pass; native
cessation is fail. The generated package has separate listening_results.json.

RATES later emits scale-like sounds with rising octaves after an interval of
noise, while the GUI remains stopped with no corresponding display activity.
FM is the user's tentative identification, not independently established. This
does not prove a memory overrun, sample/address defect or sequencer execution.

The final explicit clarification confirms both RAY01C and RAYFOR0 in
finite_end_references end normally. This supersedes the intervening ambiguous
noise report/question reply. Both are user-confirmed finite-ending references;
their copied-file hashes have not independently been measured on the emulator.
RAY2C continues looping, consistent with the encoded audit; it is not finite.

Focused structural inspection of RAY01C, RAYFOR0, HOLDEND, RATES and FS432 finds
F1 00 at the exact end of every track, valid track/tone offsets and valid ranges
for the first 96 PDX slots. No trailing bytes remain in these track regions.
These checks do not prove the loader's in-memory addresses or physical stop.
The finite originals use a 16-track header and one E8 command; HOLDEND/RATES/
FS432 use 9 tracks without E8. HOLDEND's successful stopping prevents treating
the layout difference alone as a sufficient cause. Full private inspection is
in outputs/reference_validation_2026-10-10/ending_structure/; no production
conversion or source IR change was made.

## New user observations

Original FF4SIREN keeps playing, consistent with its encoded song loops; manual
MMDSP F7 during playback stops it. RATES leaves noise after finite completion;
F7 during playback works, but F7 after the noise starts does not. Private FS432,
FS768 and FSONE play normally and animate, then leave the same noise after
completion. Replaying and pressing F7 during playback stops the sound. F7 after
completion was specifically tested/reported for RATES, not separately for each
private case. Buffer overrun is a user hypothesis, not established evidence.
MMDSP's F7 key and MDX's F7 hold opcode are different concepts.

Observations are retained independently in public/private listening_results.json
and copied observation sheets. No production converter/player change was made.
These native-MXC reference-derived failures do not require VGM extraction, so
they do not identify a vgm2mml Segment/PCM source-decoder defect by themselves.

## Ending data and bounded source evidence

RATES already has 72-tick rests on both A and P after their last notes. Last
notes end at168, sequence ends240; at @t240 the silence intent is294.912ms.
HOLDEND has64-tick rests, and the user reports successful cessation. FS432 and
FS768 P notes end exactly at the finite P end; FSONE P ends3648, G ends3660.
The original FF4SIREN loops and cannot certify natural finite-ending cleanup.

MXDRV2.06+17 reference disassembly distinguishes explicit StopPlayback
(lines739-785, PausePlayback at795-823) from finite EndPlayCommand
(2140-2174). PausePlayback includes IOCS trap15/D0=0x67/D1=0; StopPlayback also
handles resident PCM extension trap2 and OPM silencing. EndPlayCommand clears
channel masks/end flags and conditionally handles the enabled PCM extension;
it does not invoke the unconditional standard IOCS stop path in this routine.
Gate expiry calls SendKeyOff separately (1645-1694,1840-1850).
This explains why manual-stop and sequence-end requests must be inspected
separately; it does not prove how the current runtime executes or identify the
noise. In particular, extension trap2 requests are not standard IOCS calls.
The supplied screenshots show MADRV; the reference source is not asserted to be
that exact runtime. Additional environment questions are not prerequisites.

## Controlled tail trials

`tests/scripts/generate_mdx_end_tail_trials.py` creates four native MXC trials:

| Case | Sole changed lifetime | Added rest | Whole-song end |
| --- | --- | --- | --- |
| RATESF | A (FM) |1024ticks /4.194304s |5.177344s |
| RATESP | P (PCM) |1024ticks /4.194304s |5.177344s |
| FS432F | A (FM) |384ticks /5.210112s |11.071488s |
| FS432P | P (PCM) |384ticks /5.210112s |11.071488s |

Every original note/control/state/voice before the original ending is checked
unchanged. Only the selected track's ending is delayed by explicit rests; PCM
commands are unchanged in F cases, FM unchanged in P cases. PDX files and
failing originals are byte-preserved. This deliberately changes termination
order and is not reference-equivalent or a confirmed fix. Longer tails allow
manual F7 during the otherwise silent interval. Observe noise onset at original
end versus new end, cessation, and F7 during/after tail separately, starting from
silence so a preceding failure does not contaminate observation.

Package: ignored `outputs/listen/finite_end_tail/`, with original/trial MML/MDX,
both PDX, expected command/event CSV/JSON, compiler inputs, mdxinfo and observation
sheet. All four builds, unchanged-prefix/state/voice/PDX and added-rest checks,
and mdxinfo checks pass. Native outcomes remain unverified.

## Original collection requested by the user

The diagnostic scanner now supports opt-in16-track encoded timelines, expanding
finite repeats/escapes and a bounded first song-loop traversal. E8 PCM8-enable
and F2 portamento are retained as fixed-length encoded controls without claiming
effective trajectories. Unsupported synchronization/dynamic fade remain
incomplete rather than guessed. Normal reader defaults stay standard9; this
change does not add production PCM8 source/target support.

All15 original MDX files in local_only/opm_oki6258/mdx_pdx decode within that
bounded domain and have their declared PDX. Thirteen loop, two end finitely:

| Original pair | Last FM note/release request | Last PCM note/release request | Observation |
| --- | --- | --- | --- |
| CHAMA/RAY01C.MDX + RAY01C.PDX |3864tick |4080tick | U/V/W unheld q8 PCM notes immediately precede finite end |
| RAYFOR0.MDX + RAYFOR.PDX |3122tick |3192tick | U/V encoded volume0; Q/S/T final notes held, so acoustic end uncertain |

RAY01C is the clear requested-timeline PCM-last example. All16 tracks terminate
at4080; FM has216 ticks of final rest after its last note, while U/V/W have no
trailing rest. RAYFOR0's FM sequence ends3122 and PCM ends3192, but do not claim
audible PCM-last from encoded volume0 or derive physical release of held notes.
PCM sample exhaustion, playback modes and physical stopping are not proved by
NOTE/gate timing. PDX inspection covers the standard first96 slots only, not
complete PCM8 extended-bank semantics.

Full audit plus compact overview.csv: ignored
`outputs/reference_validation_2026-10-10/original_end_timeline/`.
Byte-exact original candidate copies: `outputs/listen/finite_end_references/`.
No copied private melody, tone or sample payload is put in committed notes/tests.
Seventeen reader/public/audit tests plus five selector/tail tests pass. Next,
listen to tail variants and the finite original RAY01C pair, retaining the failing
originals. Do not infer a production fix, buffer-overrun cause or source-IR
completeness from this preparatory static success.
