# Note-duration splitting in MDX MML

Japanese original: [mdx_note_durationsJ.md](mdx_note_durationsJ.md).

When generating MDX MML, long notes and rests are split so that no single command
exceeds 256 clocks. This is a target-notation operation that avoids MXC errors
for long durations.

Split notes are joined with ties (`&`) and treated as one sounding gate. Split
rests retain their total duration. Splitting does not change the original
Segments or PCM IR, total playback time, or pitch.

Dotted notation is checked using its actual clock count. With the MDX notation's
192-clock whole note, `1.` is 288 clocks and `1..` is 336 clocks, so neither is
emitted as a single command.

The shared duration formatter is in `py/mdx_duration.py`. It chooses readable
note lengths or explicit clock lengths (`%`) and keeps every split piece within
the limit. Typed PCM commands also split long durations, distinguishing
continuation from retriggering. See [PCM output processing](pcm_pdx.md).

Duration splitting is separate from timing normalization. MDX MML durations are
still split when short-gate omission and timing approximation controlled by
`--normalization-ms` are disabled.
