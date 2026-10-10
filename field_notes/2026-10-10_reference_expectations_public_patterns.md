# Independent reference expectations and authored public patterns

The immediate objective is evaluating VGM-extracted OPM Segments and neutral
PCM IR. This change prepares independent expectations and listening assets;
it does not change production conversion or demonstrate extraction completeness.

## FF4SIREN independent expectation

The existing native MXC reference-compilation trial established exact MDX
reproduction. Its PDX was copied in that trial, so it did not establish an
IR-to-PDX generation path. A separate direct MDX/PDX reader now retains original
commands, expanded requested events, controls, tone definitions, slot mappings,
exact sample bytes and sample identities. It imports no production converter,
source PCM decoder or soundlog player.

Private evidence remains in ignored
`outputs/reference_validation_2026-10-10/FF4SIREN/expected/`: JSON and CSV,
`pcm_ir.expected.json`, and encoded sample files. Nine tracks decode completely
within the declared supported-command domain. The bounded first song traversal
has 3,648 ticks on eight tracks and 3,660 on G, preserving its 12-tick initial
rest offset; P contains 255 expanded PCM NOTE requests with intro 384 ticks
and loop cycle 3,264 ticks. Its one allocated sample contains 1,453 bytes.
No reference music/sample contents are copied into public fixtures or this note.

PCM expectations are neutral sample data plus MDX-requested playback evidence,
not fabricated source `PcmAnalysis`. MDX ticks, note hold/retrigger intent, gate
release requests and PDX bindings are available; VGM transfer times/event IDs,
decoder reset/consumption, physical STOP and acoustic ending remain unknown.
Direct expectations use variant `decoded-mdx-pdx-requests`; independently
authored intent uses `authored-score-intent`. Both explicitly declare the
comparison domain. Effective LFO trajectories are not validated by static
command decoding, and key-delay controls are recorded separately from note
command times rather than claiming an observed physical key-on trajectory.

## Public authored assets

`tests/fixtures/public/mdx_reference/` contains original MML, encoded triangle
samples, PCM expectation JSON, native MXC MDX and shared PUBPCM.PDX. No FF4SIREN
melody, voice or PCM data was reused. These files are project-authored MIT assets.

| Case | Main observation | Nominal duration |
| --- | --- | --- |
| GATEEND | Early gating of both long and short samples; retriggers | 0.69 s |
| HOLDEND | Hold across two notes; release at 1.31 s; silence before finite end | 1.57 s |
| RATES | Same sample with F4/F0 and p1/p2/p3 requests | 0.98 s |
| FMSTATE | FM keyboard, voice, volume, pan, octave and finite-repeat behavior | 0.79 s |

All scores use native MXC v1.01 through the existing adapter. Encoded samples
use mdxtools' ADPCM library with project-authored exact-pair input glue; the
standalone encoder's feof loop is not used. The external MDX helper only packs
PDX here, never compiles these scores through mmlx. Independent checks compare
packed bounds/empty slots/lengths and exact payloads against pre-pack data.
The long asset is 60,000 bytes (within the selected standard length field) and
lasts nominally 7.68 seconds at F4, beyond HOLDEND's gate and song end. This
prevents natural sample exhaustion from hiding missing requested cessation.
Manual MMDSP Stop at about 0.5 seconds is a separate optional driver observation.

Correction after the first listening report: the initial seconds annotations
used 1024 microseconds per Timer B multiplier instead of 1024 cycles / 4 MHz
(256 microseconds). Corrected annotations are four times shorter; generated
MDX/PDX bytes and user listening results are unchanged. The formula agrees with
the production projection and independent mdxtools timer source.
At corrected time scaling GATEEND's short sample has 51.2 ms nominal duration
and a q4 gate of 49.152 ms; it needs early gating too. RATES at F4 exercises
sample exhaustion before the gate, while F0 needs early gating. Descriptions and
checks are corrected without modifying the already-listened binary.

`validation.json` lists the checked fields: FM pitch/onset/duration, A/P total
ticks, PCM request onset/duration/sample slot/hold/rate/pan/gate, and PDX bytes and
table properties. The pass status is limited to those checks. Separate native
listening results report all four displays/audio pass, HOLDEND cessation pass,
RATES cessation fail, and GATEEND cessation unverified. Converter extraction
is `not_run`. See `listening_results.json` and the private-phrase field note.

`mdxinfo -u -H` independently reports Success for all four MDX files, nine tracks,
the authored title, PUBPCM.PDX name and correct resolved PDX path. Its output
is retained under ignored `outputs/reference_validation_2026-10-10/`.
These patterns intentionally differ from FF4SIREN, so metadata equality is only
expected against their own authored intent, not against the private song.

## Verification and next step

Twelve reader/fixture tests passed. Reader checks cover repeats/escape/loop,
gate/hold, raw controls/tones, PDX payloads/bounds and incomplete unsupported
commands. Public checks cover the explicitly authored event/sample expectations.
Generated binary and intermediate JSON/CSV were inspected. Architect review
found no converter oracle cycle; longer sample lifetime, explicit expectation
variants and checked-field scope address its recommendations.

Listening files are copied to `outputs/listen/reference_public/`; playback needs
the four MDX files and PUBPCM.PDX together. The README and observation CSV keep
display, gate silence, tie continuity, finite end and manual Stop separate.
The user's successful listening confirmation may establish a native baseline.
It cannot by itself establish VGM extraction completeness.

Next, obtain and independently check PCM-preserving source VGM evidence against
FF4SIREN/direct expectations, then compare actual vgm2mml pass outputs. Do not
certify a capture through a known-faulty soundlog PCM replay or repair unrelated
players as a prerequisite. Keep source/capture, source IR, target projection,
compiler/adapter and PDX packing findings separate. Production edits remain
paused until the user reviews an identified defect/change.
