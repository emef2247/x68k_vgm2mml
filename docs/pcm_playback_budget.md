# Export default update (2026-10-30)

For ordinary MDX CLI exports, `scripts/export_mdx.py` now defaults to
`--pcm-buffer-kib 1200 --pcm-policy best-effort --no-vgm`.
The existing direct-loader/default4096-byte margin gives a1224704-byte
PDX budget (1200KiB=1228800bytes). Explicit options override these choices;
`--vgm` enables verification replay. The canonical converter and direct Python
batch API retain their own defaults. The315122-byte fallback described below
still applies when those entry points have no configured resident buffer.

# PCM resident-buffer budgets

The default is a maximum **315,122-byte PDX file**, including its 96-entry
table, padding and payload. This comes from the examined MXDRV initial PCM
allocation of312KiB minus270bytes for MXCTRL and4096bytes of headroom.
It is a conservative target budget for user playback testing, not detection
of the currently resident driver. Explicit buffer settings raise the file budget directly; there is no separate
1,200,000-byte ceiling.

Both `vgm2mml.py` and `scripts/export_mdx.py` accept:

| Option | Meaning |
| --- | --- |
| `--pcm-buffer-kib N` | Actual configured resident encoded-PCM buffer, in integer KiB |
| `--pcm-loader direct` | Transfer without an additional wrapper; default |
| `--pcm-loader mxctrl` | MMDSP MXCTRL transfer, with a270-byte wrapper |
| `--pcm-buffer-margin-bytes N` | Space reserved inside the buffer; default4096 bytes |

For example, **if** the installed MXDRV has a312KiB PCM buffer and MMDSP uses
MXCTRL, request:

```sh
python scripts/export_mdx.py INPUT --outdir OUTPUT \
  --pcm-buffer-kib 312 --pcm-loader mxctrl --pcm-policy best-effort
```

This yields a table-inclusive PDX budget of
`312*1024 - 270 - 4096 = 315122` bytes. The reserved4KiB is a
configurable conservative allowance, not a measured guarantee of boundary
safety. A nondefault margin or MXCTRL loader option requires an explicit buffer.
Settings leaving less than the768-byte table are rejected before conversion.

The312KiB reference applies to the examined MXDRV2.06+17 Rel.X5-S initial
allocation. It does not establish a MADRV default or the user's current
resident configuration. Select the loader according to the actual playback
path. The converter neither changes guest startup settings nor detects the
resident buffer from emulator RAM settings. Omitting `--pcm-buffer-kib` retains
the default315,122-byte cap and reports the actual resident check as unconfigured.
For a known larger allocation, specify `--pcm-buffer-kib N` and the actual
loader; for example4096KiB with direct loading permits4190208bytes after the default margin.

## Selection and final validation

One immutable resolved target policy passes through bank preflight, quality
sharing, capacity-priority representative selection, representative repair,
force omission, single/parallel binding and final packing. Reusing a retained
sample consumes no additional payload storage. Table bytes count before
selection. The final file is checked again, including unexpected packer padding.
No payload is truncated; source State/Segments/PCM IR remain unchanged.

Default `budget96` can use existing representatives within the smaller file
budget, subject to the established explicit loss policy. `similar`, `off`,
`strict` and `--force` keep their meanings; a smaller budget does not silently
enable new source omissions or transcoding. Slots, per-sample PDX/PCM8 lengths,
eight-voice allocation and MDX limits remain separate constraints.

The policy reaches native MSM6258, Delta-T, SegaPCM, C140, MSM6295 and PSG PCM
outputs through their shared target pipeline. PSG continuous mixes still do
not enter approximate representative sharing, but binding and final-file checks
use the same budget. Rate profiles remain explicitly selected using
`--pcm-profile`; automatic rate-profile retries are outside this change.

## Diagnostics and limits

Conversion metadata, source-validation/merge reports, `.pcm.timing.json`, PCM
format metadata and batch CSV retain effective/operational file caps, configured
buffer, loader overhead and margin. Console/CSV distinguish estimated selected
bytes, actual verified PDX size, transfer bytes, configured capacity compliance
and native playback. Runtime playback remains **unmeasured**.

Capacity compliance is a target calculation, not proof of loading, correct sound
or safe total RAM usage. Temporary loader buffers, MDX, resident software and
driver workspaces also consume RAM. NanoDrive8's decoded workspace is not added
to this encoded budget. EX-PDX, additional banks, file compression and changing
packers do not themselves reduce a PDX transferred in full by this loader.

## Future multi-bank layouts

Multiple96-slot banks increase addressable sample entries, but do not by
themselves reduce resident memory if the player loads all banks at once.
Bank-local size and total transferred size must be measured separately. A
future bank-switching scheme must establish what the driver can load or switch
during playback, including active voices and ADPCM state. This update only
changes the default single-bank byte budget; no automatic bank splitting or
stream truncation is introduced.

## One buffer setting controls the limit

Use `--pcm-buffer-kib N` to match the allocation configured in MXDRV
(1KiB=1024bytes). The PDX limit is that allocation minus the selected loader's
transfer overhead and configured margin. There is no separate file-limit
option and no1.2MB fixed ceiling. Example for a1MiB MXDRV allocation:

```sh
python scripts/export_mdx.py INPUT --outdir OUTPUT \
  --pcm-buffer-kib 1024 --pcm-loader mxctrl
```

The resulting whole-file limit is1044210bytes, including the PDX table.
The converter does not change the player's allocation. Omitting the buffer
keeps the315122-byte conservative default. Slot count, sample encoding limits
and MDX limits are unchanged.
