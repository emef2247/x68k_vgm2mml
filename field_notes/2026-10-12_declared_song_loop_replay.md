# Declared song loops through the ordinary Segment pipeline

The user confirmed the intended design: replay the declared VGM loop in the
reader, then let existing routines structure the increased Segment sequence.

The shared cursor keeps source byte addresses, wait overrides and chip state
across intermediate EOF. Native OPM and musical PSG/SCC use two bounded
traversals. Original command identity and first-pass timestamps remain separate
from occurrence identity, replay timestamps and iteration number.

MML repeats the second traversal with L. First-pass initialization is executed
once. A gate crossing the loop marker remains explicit controls, avoiding a
new attack or automatic note release at that boundary. Finite compression sees
the marker as a separator and setter compaction resets its cached entry state.

PCM requires independent sample starts; loop-crossing decoder continuation
is rejected explicitly. No synthetic reset or silent finite fallback is added.
--no-song-loop preserves finite one-pass output. --no-loops is separate.

Validation uses only public and synthetic sources. Reader, target marker,
end-to-end native/PSG, and PCM checks retain intermediate dumps and inspect
compiled F1 destinations. Native MMDSP listening remains the user's next step.
No repository Git mutations were performed.
