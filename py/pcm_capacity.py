"""Operational limits for the current single-bank MDX/PDX target.

These are target policies, not native PCM semantics or universal format limits.
The encoded PDX budget includes its table; decoded player workspace is excluded.
"""

SLOT_LIMIT = 96
MAX_SAMPLE_BYTES = 65535
PDX_TABLE_BYTES = SLOT_LIMIT * 8
PDX_BYTE_LIMIT = 1_200_000


def packed_pdx_bytes(samples):
    """Estimate this packer's one-bank file, counting each bound asset once."""
    return PDX_TABLE_BYTES + sum(len(sample.encoded_bytes) for sample in samples)
