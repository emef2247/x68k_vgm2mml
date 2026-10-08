# Original OKIM6258 fixtures

These VGM files contain arithmetic byte patterns written for this project,
not game audio or ROM samples. They are distributed under the repository's
MIT license. Regenerate with `python tests/scripts/generate_pcm_fixtures.py`.

- `reset_pan_hold`: PCM-only, observed STOP/PLAY resets, identical sample reuse,
  left/right/mute/center changes inside a long held sample, and a rest.
- `opm_pcm_rates`: simultaneous OPM and PCM, with one encoded sample reused at
  exact standard F0 and F4 rates.
- `long_hold_stop`: a 512-tick PCM note on the 256-us clock, requiring F7
  before its first 256-tick chunk, followed by STOP and a rest.

`reset_pan_hold` intentionally requires best-effort for the pinned standard
PCM1 profile: its held pan changes are diagnosed as known loss. Each complete
playback fits one note, so the target does not invent pan-driven ties or attacks.

Byte writes follow `floor(i * 88200 * divider / clock)` VGM samples. The adjacent
JSON files specify independently constructed source times, sample hashes and
target bindings/rates/pans. They do not assert measured decoder consumption,
waveform equivalence or successful third-party PCM VGM replay.
