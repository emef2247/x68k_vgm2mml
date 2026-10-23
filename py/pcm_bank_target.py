"""Validate native PCM before creating a separate reusable target-bank view."""
from dataclasses import dataclass, fields
import json
from pathlib import Path

from msm6258 import PcmAnalysis
from pcm_capacity import sample_byte_limit, PDX_BYTE_LIMIT, PDX_TABLE_BYTES


@dataclass(frozen=True)
class NativeBankTarget(PcmAnalysis):
    target_evidence: tuple = ()
    source_origin: str = 'projected_msm6258_from_native_bank'


def prepare(analysis, *, outdir, stem, **projection_options):
    """Keep source reset/supply validation independent of the 96-slot budget.

    Internal force permits capacity omissions only during validation. Every
    original playback still passes the ordinary decoder/rate/control checks;
    its samples, transfer ranges and native control history remain untouched.
    """
    from pcm_mdx import project
    from pcm_assessment import ProjectionError
    path = Path(outdir) / (stem + '.pcm_bank.source_validation.json')
    try:
        checked = project(analysis, stem=stem, force=True, **projection_options)
    except ProjectionError as error:
        path.write_text(json.dumps(dict(status='blocked', source_unchanged=True,
            items=error.assessment.items, reasons=error.assessment.block_reasons), indent=2) + '\n', encoding='utf-8')
        raise
    maximum = min(sample_byte_limit(projection_options.get('pdx_format', 'ex-pdx')),
                  PDX_BYTE_LIMIT - PDX_TABLE_BYTES)
    eligible = any(0 < len(s.encoded_bytes) <= maximum for s in analysis.samples)
    path.write_text(json.dumps(dict(status='validated', source_unchanged=True,
        capacity_scope='capacity omissions allowed for source validation only; final selection follows reduction',
        bank_available=eligible,
        source_origin=getattr(analysis, 'source_origin', 'native_msm6258'),
        pdx_format=projection_options.get('pdx_format', 'ex-pdx'), sample_byte_limit=maximum,
        fallback_reason=None if eligible else 'no existing sample within selected sample/file byte budget',
        source_sample_count=len(analysis.samples), source_playback_count=len(analysis.playbacks),
        items=checked.assessment.items), indent=2) + '\n', encoding='utf-8')
    if not eligible:
        return None
    if hasattr(analysis, 'target_evidence'):
        return analysis
    return NativeBankTarget(**{field.name: getattr(analysis, field.name)
                              for field in fields(PcmAnalysis)})
