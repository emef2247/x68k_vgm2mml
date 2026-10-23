"""Operational limits for the current single-bank MDX/PDX target.

These are target policies, not native PCM semantics or universal format limits.
The encoded PDX budget includes its table; decoded player workspace is excluded.
"""

SLOT_LIMIT = 96
MAX_SAMPLE_BYTES = 65535  # Legacy standard-PDX length; use sample_byte_limit for a selected target.
PDX_TABLE_BYTES = SLOT_LIMIT * 8
PDX_BYTE_LIMIT = 1_200_000


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
