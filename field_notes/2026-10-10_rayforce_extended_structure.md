# RayForce structure and controlled extended-mode tail trials

## Scope and current outcome

The user confirms both copied RAY01C and RAYFOR0 originals play and end normally,
whereas all six original files in finite_end_tail leave continuing noise. The
user asks for a toolchain that produces normal MDX/PDX from generated MML and
neutral PCM IR; MXC is not a requirement. No production conversion or source IR
was changed. Additional command-order investigation is now paused at the user's
request; the next step is listening to the updated finite_end_tail package.

Static structure and byte packing have been checked. The new extended trials'
natural ending and MMDSP animation remain unverified until the user tests them.

## Verified structural differences

| Item | RAY01C | RAYFOR0 | Original finite_end_tail |
| --- | --- | --- | --- |
| MDX tracks |16, A-H/P-W |16, A-H/P-W |9, A-H/P |
| Initial PCM-mode declaration |E8 |E8 |absent |
| PDX tables |3 x96 entries |1 x96 entries |1 x96 entries |
| Populated slots by bank |64/66/26 |28 |PUBPCM2; FF4SIREN1 |
| MDX banks used |0,1 |0 |0 |
| End command |F1 00 |F1 00 |F1 00 |
| Native finite ending |user pass |user pass |user fail |

RAY01C has three consecutive768-byte tables and payload starts at2304. This is
not concluded solely from that offset: all288 entries have been checked against
the full table boundary and file size; the MDX selects banks0/1; all360 interpreted
PCM requests resolve to populated samples. Bank2 has26 populated slots but is not
used by this particular MDX. RAYFOR has96 entries; all446 interpreted PCM requests
resolve. Unknown unwritten rate/pan/volume remain unknown rather than being
invented as source evidence. Full private CSV/JSON is under
outputs/reference_validation_2026-10-10/rayforce_structure/.

All original endings are inside the track boundary, with no bytes after the
executed F1 00 before the next region. PDX contains offsets, lengths and payloads;
there is no discovered special end-of-song sentinel to append to ADPCM data.
Playback requests/end commands belong to MDX. A valid byte range does not prove
physical cessation. HOLDEND is a successful9-track/no-E8 case, so the difference
above is a testable mode difference, not a sufficient explanation of failure.

E8 is a PCM4/8-enable request in the native reference. It changes the selected
PCM playback path, not merely the number of header offsets. This is why both
format and mode are identified explicitly in the comparison.

## PDX packing established independently

soundlog0.15.0 PdxDocument/PdxBuilder was used without its VGM replay path.
PdxBuilder::from_document supplies the exact encoded sample bytes for every
bank/slot to the existing packer. The new table/payload is independently checked
in Python for every slot's length, hash and binding.

Both regenerated PDX files are fully byte-identical to the supplied originals:

| File | Banks | Bytes | Table offsets/payloads/full file |
| --- | --- | --- | --- |
| RAY01C.PDX |3 |840134 |identical |
| RAYFOR.PDX |1 |187296 |identical |

This establishes that this existing packer can reproduce these PDX structures
from exact encoded samples. It does not establish that vgm2mml extracted the
right samples/timing, or that another PCM source is representable. The production
helper currently rejects nonzero banks despite the library's multi-bank API;
that limit was not changed. Private regenerated samples remain ignored.

## Compiler and ordering evidence

Native MXC v1.01 reproduces original FF4SIREN MDX byte-for-byte. RAY2C's supplied
MML targets NOTE v0.07.0 and is rejected by the installed MXC; this dialect result
does not imply the binary RayForce format cannot be produced by another chain.
No original RAY01C/RAYFOR0 MML compilation has been claimed.

The normal renderer puts @voice, @v, p, q, D, o before the note. Pitch and duration
are carried together in the compiled timed NOTE; o/l are compiler state rather
than separate MDX octave/default-length commands. Five short native-MXC probes
checked independent pre-note setters and voice/volume ordering. The tested
pre-note permutations preserve note state/time; moving volume/pan/octave after
the first note changes the next note. This is a bounded syntax/command-order
result, not proof all controls commute or that MMDSP animation is unaffected.
The optional probes/results are preserved in outputs/listen/mode_order_trials/.
No further ordering probes should be run before the requested listening test.

The older DSLY4_03 generated MDX contains646/672/701 timed NOTE events on F/G/H,
plus57/56/46 direct register commands, none targeting Key-On register08. It is
not wholly raw-register key sequencing. The existence of NOTE commands does not
prove display correctness; runtime animation still needs its own evidence.

## Applied finite_end_tail generation

The six root MDX files are now16-track/E8 variants of the original native-MXC
outputs. soundlog0.15.0 MdxDocument performs typed serialization; no raw offset
patching or replacement compiler was written. For every case, the original
commands and their ordering, notes, control state, durations, gate/hold intent,
tone bytes, title and PDX reference are checked unchanged except:

- Insert E8 at the beginning of A.
- Add inactive Q-W tracks containing only finite endings.

The two PDX files and all source MML remain unchanged. Old failed9-track MDX,
MML, PDX, validation and listening evidence are saved under original_standard9/.
New native outcomes are unverified and indexed by new hashes; old failures are
not attached to new bytes. mdxinfo reports Success,16 tracks, PCM8=1 and resolved
PDX for all six. Relevant23 tests passed (17reference,3bank,3mode-preservation).
The nine-track reserialization control in mode_order_trials was byte-identical
to RATES, separating serialization from deliberate extended-mode changes.

Reproduce using the existing native9-tail baseline and the diagnostic tool:

```sh
cargo build --release --locked --offline --manifest-path tests/scripts/mdx_structure_probe/Cargo.toml
python3 tests/scripts/generate_mdx_extended_tail_trials.py
```

The archived original_standard9/ baseline is consumed on reruns. Do not rerun
generate_mdx_end_tail_trials.py or the ignored historical recording helpers
against the updated root package: they can restore9-track outputs or attach
historical failures to the new generation. Original expected/ and compiler_inputs/
describe the native9 stage; expected_extended/, validation_extended.json and
mdxinfo_extended.tsv describe the current16 stage. No source IR fields were changed.

Next allowed action: user MMDSP listening of all six current MDX with fixed
PUBPCM.PDX/FF4SIREN.PDX. Only then decide whether this is a usable toolchain or
whether further differences require investigation. No success claim, production
mode default change, or automatic adoption of extended PCM follows from static
inspection. No additional ordering work is authorized before that checkpoint.

## Subsequent confirmed result and adoption

The user confirmed all six current finite_end_tail root MDX play and stop correctly.
This supersedes the pending listening checkpoint above. Hashes, retained failed
standard-nine evidence, production adoption and public-only checks are recorded
in field_notes/2026-10-10_pcm_extended_production.md. Ordering work remains paused.
