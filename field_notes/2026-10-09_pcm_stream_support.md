# Finite OKIM6258 Data Bank / DAC Stream support

## Scope and result

Resume PCM source conversion independently of the completed CLI cleanup.
Compiler/MMDSP display and native PCM-stop investigations remain paused.
Implement finite bank-4 supplies, preserve original commands/bytes/timing,
and assess target losses separately. Do not use soundlog PCM replay as an
oracle, change source timing, relax the one-sample cadence check or silently
discard source semantics.

`py/pcm_stream.py` expands uncompressed `0x04` banks and stream commands into
an immutable packed supply log. Original B7 writes stay in `pcm_raw.csv`;
derived supplies carry their own sequence, triggering event/address, stream,
bank/block position and byte index in `pcm_stream_supplies.csv`. Stream control
snapshots and nonfatal observations also have separate CSVs. Source header,
reference revision, blocks and exact sample bytes remain inspectable.

Supported starts are `0x95` finite blocks with flags zero and `0x93` modes 1
(command count) and 3 (bank end), using one primary OKIM6258 data register.
Step zero means one; base and concatenated bank positions are respected.
`0x94` and stop-all `0xFF` stop only supplies. Exhaustion creates no chip STOP,
PLAY or reset. Same-tick original commands precede derived DAC supplies.
Frequency changes preserve phase; zero frequency pauses an already started
stream. A zero-frequency START is explicitly rejected: libvgm's pre-step can
emit an initial byte even at zero, and a same-tick change can yield two writes.
Compressed banks, reverse/stream loops, other length modes, frequencies above
44100 and active data-setup changes remain explicit diagnostics.

## Independent reference and codec correction

Reference revision: libvgm `70e1d1fad8c03df2ce4bfb13f8599c56920dcdc8`.

- [VGM 1.71 stream specification](https://raw.githubusercontent.com/vgmrips/vgmplay-legacy/master/VGMPlay/vgmspec171.txt)
  defines bank selection, stream operands and the distinction from chip control.
- [DAC controller](https://github.com/ValleyBell/libvgm/blob/70e1d1fad8c03df2ce4bfb13f8599c56920dcdc8/emu/dac_control.c)
  and [RatioCntr](https://github.com/ValleyBell/libvgm/blob/70e1d1fad8c03df2ce4bfb13f8599c56920dcdc8/emu/RatioCntr.h)
  define the selected 44100 Hz, 32.32 transfer scheduling profile.
- [Player](https://github.com/ValleyBell/libvgm/blob/70e1d1fad8c03df2ce4bfb13f8599c56920dcdc8/player/vgmplayer.cpp)
  runs source commands before the tick's DAC update and interprets header bit 2
  set as 4-bit ADPCM. The previous converter had that interpretation reversed.
  Public authored flags changed from `0x02` to `0x06`; encoded payloads did not.
- [OKIM6258 core](https://github.com/ValleyBell/libvgm/blob/70e1d1fad8c03df2ce4bfb13f8599c56920dcdc8/emu/cores/okim6258.c)
  has no consumption during STOP and reinitializes its FIFO on stopped-to-PLAY.
  This resolves stopped stream supplies under that implementation profile.
  [Current MAME](https://github.com/mamedev/mame/blob/master/src/devices/sound/okim6258.cpp)
  differs in its data-register model; neither core certifies native IOCS behavior.

SHA-256 of pinned reference files:

| File | SHA-256 |
|---|---|
| `emu/RatioCntr.h` | `33176556dc40f8389c7746fff8cb15bdc021fabbbe33f1cc2ea6363a1a1395dd` |
| `emu/dac_control.c` | `6f3e1ed026845ba31021a8e484702fd17e5e3fecf5d85217cee67be4abdd40cd` |
| `emu/cores/okim6258.c` | `67a4ead490281d481cab7f2836be7cc6608b7de68359234f3fb2d0bc3552a04a` |
| `player/vgmplayer.cpp` | `f1661f89171fea9e674b90e99747236970f89a843bfad9d928e567030f9cdb54` |

An ignored C harness compiled the original upstream counter header and stepped
it once per VGM tick. Project supplies matched every timestamp for 7813 Hz /
5527 bytes, 5208 Hz / 2772 bytes, 11025 Hz / 100 bytes, 44100 Hz / 100 bytes and
1 Hz / 3 bytes. This validates the transfer counter, not decoder consumption.
Evidence: `outputs/pcm_stream_2026-10-09/reference/result.json` and the pinned
source files/harness in that ignored directory.

## Target policy

Source `independently_playable` and its one-sample cadence/tail checks are
unchanged. A failed source cadence check is not converted to source success.
For complete finite stream supplies with known reset, stable supported decoder
rate and no unresolved source issue, target best-effort can use continuous
unchanged PDX bytes (`byte_supply_schedule_not_preserved`). Diagnostics retain
the affected playback interval, maximum cadence error and nominal unsupplied
PLAY tail. No padding, source-clock change or re-encoding occurs. Source PLAY
and STOP boundaries use the existing shared projection; a sample can exhaust
before the later target note ends. The audible effect and consumption remain
unverified. Direct irregular B7 supply has no newly defined fallback.

Stopped stream supplies remain in source evidence. Their omission is explicit
target loss under the named libvgm reset profile; native buffered state is
unverified separately. Song-loop entry retains source decoder state, while
`song_loop_not_emitted` reports finite-pass output whether entry is active or
stopped. Strict blocks all these known losses. Best-effort does not bypass
incomplete setup, missing banks or unsupported stream semantics.

Helper errors explicitly reporting track-offset overflow or the conservative
combined-size limit are `mdx_capacity_exceeded`, with MDX blocked. Generated
MML/PDX and target dumps survive; runtime remains not_run/unverified and no
unexpected playback mismatch is invented. No truncation/splitting is defined.

## BOSCON01 inspection

The private fixture is unchanged. Only metadata is recorded here:

- Eight bank-4 blocks, 15332 bytes; 571 original B7 controls; 304957 derived
  supplies; 232 playback spans; 51 distinct observed byte sequences/prefixes.
- The previous unsupported-bank/stream source issues are resolved. 102 supplies
  while stopped remain observations. Song-loop tick 812538 enters active PCM.
- 115 spans require the continuous-delivery fallback. The largest cadence
  deviation is 3.2544 VGM samples in playback 129, ticks 1284043..1289383.
  Playback 47, ticks 393530..424986, has a 257.1904-sample nominal unsupplied
  tail after 5527 supplied bytes. This is not a claim about audible hold.
- Default strict blocks delivery/stopped-supply/song-loop loss. Explicit
  best-effort produces `BOSCON01.mdx.mml` (152658 bytes) and `BOSCON01.pdx`
  (54571 bytes); all 51 allocated PDX payloads equal source-derived bytes.
- The full MDX still cannot be built: track 8 offset exceeds `0xfffe`.
  `assessment_status=lossy`, `artifact_status=blocked`, runtime unverified/not_run.
  MML/PDX are partial outputs, not a completed MDX/PDX pair.

Ignored evidence: `outputs/pcm_stream_2026-10-09/{before,expanded,strict,best-effort}/`
and `boscon_audit.json`. Pass dumps include detailed structured target units,
controls and timing even when MDX construction fails. Private bytes and
generated binaries are not staged.

### Native track-size investigation

A read-only probe compiles each generated FM track separately with the same
existing mmlx/soundlog libraries. It excludes other track lines, retains the
same voice definitions, and totals serialized command bytes. This measures
encoded size only; it is not a playback or musical-equivalence oracle.

| FM track | Encoded command bytes |
|---|---:|
| A | 9424 |
| B | 7734 |
| C | 7349 |
| D | 10641 |
| E | 14606 |
| F | 4274 |
| G | 11040 |
| H | 4959 |
| Total | 70027 |

The FM-only compilation already exceeds the track-8 start-offset limit before
the typed PCM track is attached. The largest contributor is E; detune, notes
and key-off-disable trajectory commands account for much of the FM size.
PDX payload size is not the cause of this offset failure. Existing exact
loops and setter/duration compaction are already active. No safe capacity
workaround has been established; no clock change, note removal, compiler
switch, track reordering or truncation was introduced.

Ignored evidence: `boscon_track_sizes.tsv` and `reference/track_sizes.rs` under
`outputs/pcm_stream_2026-10-09/`. The compact timing report now scopes byte
preservation to encoded playback samples stored in PDX, distinguishes direct
and profile-derived supply, and explicitly leaves decoder consumption unknown.
It does not claim that omitted stopped supplies were preserved in the target.

The user accepted this capacity limitation for BOSCON01. The relevant size is
compiled FM command data, not MML character count. Keep its MDX generation
blocked with partial MML/PDX evidence; do not treat it as a remaining PCM source
decoder defect or require a capacity workaround to accept this source-support
checkpoint. Capacity optimization is optional future target work.

Capacity terminology: standard MDX stores track starts and the tone-data start
as 16-bit offsets from the table base, not individual track-length fields.
soundlog 0.15.0's builder reserves track offset 0xffff as absent and accepts
starts through 0xfffe (65534); tone starts can reach 0xffff. The project's typed
PCM helper additionally limits the whole serialized file to 65535 bytes as a
conservative policy. Neither limit establishes an independent 64-KiB allowance
per FM track or a universal MDX file-length rule. Driver allocation limits are
separate from these offset/packing checks.

### BOSCON04 trial

The user's normal converter command succeeded with baseline structured timing.
Normalization declined because the nominated clock would collapse a positive
source interval; this is the intended fallback, not conversion failure.
Although the header declares an 8-MHz OKIM6258, actual command inventory contains
only OPM and waits/end: no B7, bank or stream commands, and no PCM sample data.
Thus BOSCON04 does not exercise PCM/PDX generation and needs no PDX.

`scripts/export_mdx.py` subsequently compiled its canonical MML with the default
MXC and exported all three FM artifacts successfully. MDX is 11756 bytes and
has an empty PDX name; the compiler's structure-validation step passed. The
replayed VGM is 118454 bytes. No semantic roundtrip or native playback was run.
Artifacts, compiler inputs/metadata and `BOSCON04.audit.json` are ignored under
`outputs/opm_6258/vgmrips.net/BOSCON/`; the three export products are in
`tracks/BOSCON04.vgm/`. The root and exported canonical MML bytes are identical.

### BOSCON06 / BOSCON07 trial

Both inputs use bank-4 streams and PCM. Default strict conversion blocks known
loss before target generation: song-loop omission, stopped-supply omission and
byte-delivery schedule differences. Source analysis has no blocking issues.
Strict reports remain in `outputs/opm_6258/vgmrips.net/BOSCON/`.

Explicit `--pcm-policy best-effort` with `--dump-passes` succeeded for both:

| Input | MDX bytes | PDX bytes | Distinct samples | Playbacks | Delivery-loss spans |
|---|---:|---:|---:|---:|---:|
| BOSCON06 | 32349 | 71941 | 55 | 140 | 74 |
| BOSCON07 | 33724 | 52859 | 24 | 158 | 67 |

Products and complete pass/assessment dumps are in
`outputs/opm_6258/vgmrips.net/BOSCON/best-effort/`. Each MDX names its adjacent
same-stem PDX and has the standard nine-track layout. All allocated PDX sample
bytes equal source-analysis bytes; all unused slots are empty. A read-only
inspector using pinned mdxtools command boundaries decoded each MDX, and every
PCM opcode/operand exactly matched the typed target plan (1618 / 2198 commands).
Sample references resolve and total PCM ticks match the common MDX end.
Normalization retains the shared OPM/PCM clock as designed.

These are generated lossy artifacts, not strict roundtrip passes. Decoder
consumption, IOCS reset, native buffered-data behavior and runtime playback
remain unverified/not_run. Static command/payload checks do not establish
waveform or MMDSP playback equivalence. Detailed ignored evidence is
`outputs/opm_6258/vgmrips.net/BOSCON/BOSCON06_07.audit.json` and per-file
`*.encoded_commands.csv`. No production code was changed for these trials.

## Verification and next action

- 84 focused tests passed: source OKIM6258, stream scheduling, PCM projection /
  real helper packing, CLI routes and capacity-failure evidence preservation.
- 45 regression tests passed: VGM timing, structured OPM MML, target VGM and
  export behavior. No whole private catalog or native runtime certification.
- Eight authored stream fixtures regenerate exactly. Original public PCM
  fixture encoded payloads are unchanged; only their intended codec flag changed.
- Architect review found the zero-frequency pre-step edge; starts now reject
  it explicitly, including same-tick frequency-change coverage. Buffer semantics
  and capacity status separation were reviewed under the pinned profile.
- After clarifying compact-report preservation scope, all 36 PCM target tests
  passed again, including stopped-supply diagnostics and partial-output handling.

Next PCM work should use the selected standard PCM1 references to extend
independent command/sample evidence toward the C/A/B validation design. Native
playback semantics must retain unverified fields until independently checked.
If capacity optimization is requested later, use compiled track sizes as
evidence and preserve source timing, OPM musical rendering and the shared PCM
clock. Do not solve capacity by silently dropping notes, loosening cadence,
re-encoding samples or switching compiler paths. MMDSP display/PCM stopping
remains paused; independent C/A/B runtime validation remains unimplemented.
