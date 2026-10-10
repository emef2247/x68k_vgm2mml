# Public listening evidence and private FF4SIREN phrases

The user listened to the copied public reference patterns in MMDSP. All four
animate correctly and are audible. HOLDEND stops correctly. RATES continues
with noise after the data ends. GATEEND stopping was not separately reported.
Keep these results separate from static generation checks; public
`listening_results.json` records them. Copied file identities are reported
filenames, not independently measured hashes. No RATES cause is established.

## Timing correction

The earlier seconds annotations incorrectly treated 1024 Timer B clock cycles
as 1024 microseconds. At 4 MHz, one tick is 256 * (256-tempo) microseconds,
consistent with production projection and independent mdxtools timer source.
At @t240, HOLDEND gate/end are 1.31072/1.572864 seconds. Public MDX/PDX bytes and
user observations are unchanged; only timing annotations and descriptions are
corrected. RATES F4 exhausts its short asset before gate, F0 needs early gating.
GATEEND's short asset also needs gating (49.152 ms vs 51.2 ms nominal duration).

## Private reference-derived patterns

The user authorized fixtures preserving FF4SIREN's actual performance, voices,
controls and PCM. Production conversion is unchanged. The reusable generator
contains no copied private music/payload and writes only beneath ignored roots.

| Case | Selection | Nominal duration | PCM NOTE requests |
| --- | --- | --- | --- |
| FS432 | Original beginning through tick 432 | 5.86 s | 3 |
| FS768 | Original beginning through tick 768 | 10.42 s | 30 |
| FSONE | Original intro and one complete traversal | 49.66 s | 255 |

Short cases use shared original event boundaries and retain all nine tracks.
Finite repeats are expanded only to select these prefixes, with original line
and repeat-iteration CSV provenance. No note is shortened. FSONE retains
original finite repeats and removes song-loop markers. Eight tracks end at
3648 ticks, G at 3660: its r16 preserves the original 12-tick rest delay, while
D4 is detune. All original voices and gate/LFO/detune/tempo/pan/volume controls
are retained, including relative volume and unspecified initial PCM pan/volume.

Direct candidate/reference comparison checks raw musical/control opcode
operands and ticks in execution order, complete event/state attributes, tone
bytes and exact ending boundaries. Repeat mechanics and song-loop/finite
termination are deliberate differences. FSONE also retains zero-time controls
at the original cycle boundary. Titles and PDX-name casing change. No forced
stop, extra silence, re-encoding or cross-boundary shortening hides a failure.
Static control comparison does not certify effective LFO or physical stopping.

The original PCM payload is saved as an independent expectation and repacked
with the external tool. The complete PDX, not only sample bytes, matches the
original byte for byte including slot-1 binding. PCM expectations distinguish
MDX requests from observed source IR; physical reset/stop/consumption remain
unknown. JSON sample-relative paths resolve before and after listening-copy
creation and match recorded hashes/lengths.

## Evidence and next work

Generated private assets: `tests/fixtures/local_only/derived_mdx/FF4SIREN/`.
Listening copy: `outputs/listen/reference_ff4siren/`, including MML, MDX, PDX,
PCM JSON, token CSV, prepared compiler inputs, original/candidate expectations
and observation sheet. Playback needs the three MDX files and FF4SIREN.PDX.
All derived reference music/sample data remain ignored/private.

Native MXC compilation, independent commands/events/state/tones, whole-PDX
equality and copied sample-path checks pass for all three. mdxinfo reports
Success, correct titles, nine tracks and resolved PDX. Twelve reader/public
tests and three authored selector tests pass. Architect review identified the
G timing, seconds correction and expectation-path issues; each was addressed.
Public binary hashes still match the already-listened artifacts.

Regenerate in WSL with
`python3 tests/scripts/generate_local_mdx_reference_phrases.py`.
This bounded selector rejects unsupported syntax and unsafe cuts; it is not
a general MML parser or production conversion path. Local native playback is
unverified pending user listening. VGM capture and vgm2mml Segment/PCM extraction
comparison have not run. Next, record each private pattern's display and ending
result, then investigate defects supported by those observations. Do not infer
RATES' cause, repair unrelated replay tools, or change production in this trial.
