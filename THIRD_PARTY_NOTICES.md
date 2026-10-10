# Third-party attribution and notices

## vgm-conv

Project: [digital-sound-antiques/vgm-conv](https://github.com/digital-sound-antiques/vgm-conv)

Reference revision: `780a20ed505e23eb21aa9c6ce3f349029718b5a0`

Reference source:
[src/converter/ay8910-to-opm-coverter.ts](https://github.com/digital-sound-antiques/vgm-conv/blob/780a20ed505e23eb21aa9c6ce3f349029718b5a0/src/converter/ay8910-to-opm-coverter.ts)

The PSG FM projection in `py/psg_opm_fm.py` uses the published AY8910-to-OPM
voice parameters and volume-to-TL mapping as a reference. This includes
AL4/FB7, the MUL2/TL27 modulator, MUL1 carrier, fixed-level TL table and eight
attenuation steps of headroom. Segment processing and target generation are
implemented in this project; the external converter is not a runtime dependency.
The upstream notice is retained for these referenced mapping materials.

Upstream [LICENSE.md](https://github.com/digital-sound-antiques/vgm-conv/blob/780a20ed505e23eb21aa9c6ce3f349029718b5a0/LICENSE.md):

```text
ISC License

Copyright (c) 2023 Mitsutaka Okazaki and Contributors

Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```
