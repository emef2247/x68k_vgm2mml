# OPNA source analysis and MUCOMVGM tool check

Scope after user corrections: YM2608/OPNA only; exclude OPN and OPN2.
Start in x68k_vgm2mml because its native OPM and PCM evidence/timing boundaries
provide a fuller source-stage baseline than the MSX sibling. No MDX projection
is used to reconstruct OPNA source state. The sibling's public OPNA fixtures
are used read-only when absent here; no MSX implementation is changed yet.

New source path: native register CSV -> immutable FM State -> integrated FM
control-state Segment CSV. Unmodeled SSG/rhythm/ADPCM registers and associated
DELTA-T data blocks/DAC stream operands remain inspectable evidence. PCM
samples/playback Segments, source acoustic simulation and MUCOM MML generation
are not implemented. See docs/opna_segments.md for mappings and limits.

Focused OPNA suite: 15 tests pass, covering 29 public VGM inputs plus synthetic
cases. Retained evidence: outputs/opna_reader_2026-10-12/results.csv and per-input
Raw/State/Segment/unmodeled/manifest files. Public inputs have 13907 raw writes,
18486 State events, 6391 Segments, 996 rising operator edges. Match source VGM
commands and real key masks, rather than assuming original OPLL behavior.

MUCOMVGM-Studio is a GUI wrapper; the separate wingghost/MUCOMVGM repository
distributes the requested mucomvgm.exe. Version0.0.5 installed under ignored
.tools with release SHA256 recorded in docs/opna_segments.md. Self-authored
MUC -> VGM -> Segment check passes: two quarter-note gates at T120, each22050
samples, total88200; 8 rising and8 falling operator edges. This is source-stage
validation, not generated-MML roundtrip. Keep compiler limitations separate
from Yamaha semantics. In particular T is BPM and lowercase t is Timer-B.

Broader public/synthetic regression run before the final OPNA-only scope:
643 tests, 9 failures, 11 errors, 3 skips. All 20 failing cases reproduce
against HEAD: nine failures and the PSG/SCC evidence error in the isolated
HEAD snapshot on Windows; the remaining ten MDX replay errors in WSL, using
HEAD Python production/test modules and the existing external executable/public
authored voices. The latter all fail because IdentitySamples lacks
source_clock_hz. Evidence: outputs/head_replay_baseline_2026-10-12.log.
Do not report a passing full suite or expand this task into unrelated fixes.
After OPNA-only consolidation, all 15 focused tests pass on Windows and WSL;
nearby VGM tests have19/20 pass and OPM reader5/6, with the same pre-existing
GD3 title-space and missing OPLL declaration failures. No private fixture
checks or Git mutations are part of the validation workflow.
