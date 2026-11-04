"""ZMUSIC (ZMD) side output for the MDX conversion.

A musical sink for opm_conversion.convert: when a conversion
is asked to also emit ZMD, this renders the same MusicalMdx
the MDX renderer consumed, plus the PCM projection's typed
commands and a PDX image packed from the projection's own
sample files (byte-identical to the generator's packing).
"""
import re
from pathlib import Path

from zmd_emit import pack_pdx, render_zmd


def write_zmd(musical, pcm_plan, *, outdir, stem):
    """Render and write <stem>.zmd; returns (path, losses)."""
    timer = re.search(r'@t(\d+)', musical.text)
    if timer is None:
        raise ValueError('musical text carries no @t timer value')
    pcm_commands = None
    pdx_bytes = None
    if pcm_plan is not None and pcm_plan.bindings:
        pcm_commands = [dict(row) for row in pcm_plan.typed_commands]
        # The projection writes its sample files under
        # <stem>.pcm/ beside its own outputs; projected routes
        # nest those under projected_opm/ before the caller
        # copies the PCM pair up, so accept either location.
        samples = {}
        for binding in pcm_plan.bindings:
            if binding.bank != 0:
                continue
            for base in (Path(outdir), Path(outdir) / 'projected_opm'):
                candidate = base / (stem + '.pcm') / binding.file
                if candidate.is_file():
                    samples[binding.slot] = candidate.read_bytes()
                    break
            else:
                raise ValueError(
                    f'PCM sample file not found for binding {binding.file}')
        pdx_bytes = pack_pdx(samples)
    data, losses = render_zmd(musical, timer_value=int(timer.group(1)),
                              title=stem, pcm_commands=pcm_commands,
                              pdx_bytes=pdx_bytes)
    path = Path(outdir) / (stem + '.zmd')
    path.write_bytes(data)
    return path, losses
