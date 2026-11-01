"""Operational limits for the current single-bank MDX/PDX target.

These are target policies, not native PCM semantics or universal format limits.
The encoded PDX budget includes its table; decoded player workspace is excluded.
"""
from dataclasses import dataclass

SLOT_LIMIT = 96
MAX_SAMPLE_BYTES = 65535  # Legacy standard-PDX length; use sample_byte_limit for a selected target.
PDX_TABLE_BYTES = SLOT_LIMIT * 8
# Observed MXDRV initial allocation, MXCTRL wrapper and conservative headroom.
# This is a default target budget, not detection of the installed resident.
PDX_BYTE_LIMIT = 312 * 1024 - 270 - 4096


@dataclass(frozen=True)
class PcmCapacityPolicy:
    """Resolved target memory settings; never mutate source PCM evidence."""
    buffer_bytes: int | None = None
    loader: str = 'direct'
    margin_bytes: int = 4096

    def __post_init__(self):
        if self.loader not in ('direct', 'mxctrl'):
            raise ValueError('PCM loader must be direct or mxctrl')
        if type(self.margin_bytes) is not int or self.margin_bytes < 0:
            raise ValueError('PCM buffer margin must be a nonnegative integer byte count')
        if self.buffer_bytes is None:
            if self.loader != 'direct':
                raise ValueError('PCM loader selection requires --pcm-buffer-kib')
        elif type(self.buffer_bytes) is not int or self.buffer_bytes <= 0:
            raise ValueError('PCM buffer must contain a positive integer byte count')
        if self.pdx_byte_limit < PDX_TABLE_BYTES:
            raise ValueError('PCM buffer leaves less than the 768-byte PDX table after loader overhead and margin')

    @property
    def loader_overhead_bytes(self):
        return 270 if self.loader == 'mxctrl' else 0

    @property
    def pdx_byte_limit(self):
        if self.buffer_bytes is None:return PDX_BYTE_LIMIT
        return self.buffer_bytes - self.loader_overhead_bytes - self.margin_bytes

    def summary(self, pdx_bytes=None):
        if pdx_bytes is not None and (type(pdx_bytes) is not int or pdx_bytes < 0):
            raise ValueError('PDX measured size must be a nonnegative integer byte count')
        transfer = (pdx_bytes + self.loader_overhead_bytes if pdx_bytes else 0) if pdx_bytes is not None else None
        check = ('unconfigured' if self.buffer_bytes is None else 'unmeasured' if pdx_bytes is None else
                 'not_required' if not pdx_bytes else 'within_budget' if pdx_bytes <= self.pdx_byte_limit else 'exceeds_budget')
        return dict(pdx_operational_byte_limit=self.pdx_byte_limit, pdx_byte_limit=self.pdx_byte_limit,
            pcm_buffer_bytes=self.buffer_bytes, pcm_loader=self.loader,
            pcm_loader_overhead_bytes=self.loader_overhead_bytes,
            pcm_buffer_margin_bytes=self.margin_bytes if self.buffer_bytes is not None else 0,
            pcm_transfer_bytes=transfer, pcm_buffer_capacity_check=check,
            runtime_buffer_fit='unmeasured',
            memory_scope='encoded PDX transfer only; excludes temporary loader memory, MDX and other residents')


def resolve_pcm_capacity(*, buffer_kib=None, loader='direct', margin_bytes=4096):
    if buffer_kib is not None and (type(buffer_kib) is not int or buffer_kib <= 0):
        raise ValueError('--pcm-buffer-kib must be a positive integer KiB count')
    if buffer_kib is None and margin_bytes != 4096:
        raise ValueError('--pcm-buffer-margin-bytes requires --pcm-buffer-kib')
    return PcmCapacityPolicy(None if buffer_kib is None else buffer_kib * 1024, loader, margin_bytes)


def add_capacity_arguments(parser):
    parser.add_argument('--pcm-buffer-kib', type=int,
        help='Resident encoded-PCM buffer in KiB; omitted uses the 315,122-byte default PDX cap (312 KiB minus MXCTRL overhead and 4 KiB margin)')
    parser.add_argument('--pcm-loader', choices=('direct', 'mxctrl'), default='direct',
        help='PDX transfer overhead: direct=0, MMDSP MXCTRL=270 bytes (requires --pcm-buffer-kib)')
    parser.add_argument('--pcm-buffer-margin-bytes', type=int, default=4096,
        help='Reserved room inside a configured PCM buffer (default: 4096 bytes; not a playback guarantee)')


def packed_pdx_bytes(samples):
    """Estimate this packer's one-bank file, counting each bound asset once."""
    return PDX_TABLE_BYTES + sum(len(sample.encoded_bytes) for sample in samples)


PDX_FORMATS = ('ex-pdx', 'standard')


def sample_byte_limit(pdx_format='ex-pdx'):
    """The PCM8 length occupies 24 bits; its upper byte is a playback mode.

    EX-PDX serializes a long length. This target deliberately stays inside
    the PCM8 call's 24-bit length, as well as the separate total-file budget.
    Standard PDX reserves the upper length word and uses only its low word.
    """
    if pdx_format not in PDX_FORMATS:
        raise ValueError('PDX format must be ex-pdx or standard')
    return 0x00ffffff if pdx_format == 'ex-pdx' else MAX_SAMPLE_BYTES
