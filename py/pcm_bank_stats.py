"""Inspectable bank/mix output statistics, separate from runtime buffer fitness."""
import csv
import json
from pathlib import Path
import struct

from pcm_assessment import generated_binary_artifacts
from pcm_capacity import PDX_BYTE_LIMIT


RESULT_FIELDS = (
    'pcm_bank_route', 'pcm_bank_fallback', 'pcm_bank_source_gates', 'pcm_bank_source_parts',
    'pcm_bank_silent_gates', 'pcm_bank_rom_views', 'pcm_bank_trajectory_variants',
    'pcm_bank_samples', 'pcm_bank_playbacks', 'pcm_bank_reused_playbacks',
    'pcm_bank_asset_bytes', 'pcm_bank_retained_samples', 'pcm_bank_retained_playbacks',
    'pcm_bank_retained_bytes', 'pcm_bank_tracks', 'pcm_bank_omitted_playbacks', 'pcm_bank_pdx_bytes',
    'pcm_bank_merge_mode', 'pcm_bank_merge_samples_before', 'pcm_bank_merge_samples_after',
    'pcm_bank_merge_bytes_before', 'pcm_bank_merge_bytes_after', 'pcm_bank_merged_playbacks',
    'pcm_bank_recovered_playbacks',
    'pcm_bank_newly_omitted_playbacks', 'pcm_bank_retained_playback_delta',
    'pcm_bank_budget_limit', 'pcm_bank_forced_samples', 'pcm_bank_forced_playbacks',
    'pcm_bank_pdx_byte_limit', 'pcm_bank_pdx_byte_budget_satisfied',
    'pcm_bank_budget_input_pdx_bytes', 'pcm_bank_budget_output_pdx_bytes',
    'pcm_bank_pdx_format', 'pcm_bank_sample_byte_limit',
)


def _rows(path):
    if not path.is_file():
        return None
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def summarize(folder, stem, *, allow_binary=False):
    """Read this attempt's selection; trust binaries only with ownership/caller evidence.

    ``allow_binary`` is for an exporter that removed stale artifacts before this
    attempt and has recorded a current PDX. Mere file presence is insufficient.
    Candidate asset totals and retained packed totals deliberately remain separate.
    """
    folder = Path(folder)
    selection = folder / f'{stem}.segapcm_projection.json'
    route_label = 'SegaPCM'
    if selection.is_file():
        value = json.loads(selection.read_text(encoding='utf-8'))
    else:
        merge_path = folder / f'{stem}.pcm_bank_merge.json'
        if not merge_path.is_file():
            timing_path = folder / f'{stem}.pcm.timing.json'
            if not timing_path.is_file():
                return {}
            timing = json.loads(timing_path.read_text(encoding='utf-8'))
            shared = dict(mode=timing.get('pcm_source_origin', 'PCM'),
                          input_sample_count=None, input_payload_bytes=None)
        else:
            shared = json.loads(merge_path.read_text(encoding='utf-8'))['summary']
        validation = folder / f'{stem}.pcm_bank.source_validation.json'
        origin = (json.loads(validation.read_text(encoding='utf-8')).get('source_origin', 'shared_bank')
                  if validation.is_file() else shared['mode'] if not merge_path.is_file() else 'shared_bank')
        events = _rows(folder / f'{stem}.pcm_bank_merge.playbacks.csv') or []
        value = dict(requested=shared['mode'], selected=origin,
                     sample_count=shared['input_sample_count'], playback_count=len(events) if merge_path.is_file() else None,
                     stats=dict(unique_sample_count=shared['input_sample_count'],
                                asset_payload_bytes=shared['input_payload_bytes']))
        route_label = 'PCM'
    if not isinstance(value, dict) or not isinstance(value.get('stats', {}), dict):
        raise ValueError('SegaPCM projection statistics must be JSON objects')
    source = value.get('stats', {})
    fallback = value.get('fallback')
    if isinstance(fallback, dict):
        fallback = ': '.join(str(fallback[k]) for k in ('code', 'detail') if fallback.get(k))
    result = dict(requested=value.get('requested'), selected=value.get('selected'),
                  route_label=route_label,
                  fallback_reason=fallback or '',
                  source_gate_count=source.get('source_gate_count'),
                  source_part_count=source.get('source_part_count'),
                  silent_gate_count=source.get('silent_gate_count'),
                  rom_view_count=source.get('rom_view_count'),
                  trajectory_variant_count=source.get('trajectory_variant_count'),
                  sample_count=source.get('unique_sample_count', value.get('sample_count')),
                  playback_count=value.get('playback_count'),
                  reused_playback_count=source.get('reused_playback_count'),
                  asset_payload_bytes=source.get('asset_payload_bytes'),
                  source_channel_count=source.get('source_channel_count'),
                  retained_sample_count=None, retained_playback_count=None,
                  retained_payload_bytes=None, tracks=None, omitted_playback_count=None,
                  pdx_bytes=None, binary_evidence='unverified', runtime_buffer_fit='unmeasured',
                  pdx_byte_limit=PDX_BYTE_LIMIT, pdx_byte_budget_satisfied=None,
                  budget_input_pdx_bytes=None, budget_output_pdx_bytes=None,
                  merge_mode=None, merge_samples_before=None, merge_samples_after=None,
                  merge_bytes_before=None, merge_bytes_after=None, merged_playback_count=None,
                  recovered_playback_count=None)
    timing_path = folder / f'{stem}.pcm.timing.json'
    timing = json.loads(timing_path.read_text(encoding='utf-8')) if timing_path.is_file() else {}
    result.update(pdx_format=timing.get('pcm_pdx_format'),
                  sample_byte_limit=timing.get('pcm_sample_byte_limit'))
    merge_path = folder / f'{stem}.pcm_bank_merge.json'
    if merge_path.is_file():
        merge = json.loads(merge_path.read_text(encoding='utf-8'))
        if not isinstance(merge, dict) or not isinstance(merge.get('summary'), dict):
            raise ValueError('PCM bank reduction report must contain a summary object')
        merge = merge['summary']
        result.update(merge_mode=merge.get('mode'),
                      merge_samples_before=merge.get('input_sample_count'),
                      merge_samples_after=merge.get('output_sample_count'),
                      merge_bytes_before=merge.get('input_payload_bytes'),
                      merge_bytes_after=merge.get('output_payload_bytes'),
                      merged_playback_count=merge.get('merged_playback_count'),
                      recovered_playback_count=merge.get('recovered_playback_count'))
        result.update(merge_preview_directory=merge.get('preview_directory'),
                      merge_preview_wav_count=merge.get('preview_wav_count'),
                      newly_omitted_playback_count=merge.get('newly_omitted_playback_count'),
                      retained_playback_delta=merge.get('retained_playback_delta'))
        result.update(budget_input_pdx_bytes=merge.get('budget_input_pdx_bytes'),
                      budget_output_pdx_bytes=merge.get('budget_output_pdx_bytes'))
        result.update(budget_limit=merge.get('budget_limit'),
                      budget_input_sample_count=merge.get('budget_input_sample_count'),
                      forced_sample_count=merge.get('forced_sample_count'),
                      forced_playback_count=merge.get('forced_playback_count'))
    preview = folder / f'{stem}.pcm_block_previews.json'
    if preview.is_file():
        value = json.loads(preview.read_text(encoding='utf-8'))
        result.update(preview_directory=value['directory'], preview_wav_count=value['wav_count'])
    pdx = folder / f'{stem}.pdx'
    owned = pdx in generated_binary_artifacts(folder, stem)
    if not pdx.is_file() or not (allow_binary or owned):
        return result
    payload = pdx.read_bytes()
    bindings = _rows(folder / f'{stem}.pcm_bindings.csv')
    projections = _rows(folder / f'{stem}.pcm_projection.csv')
    omissions = _rows(folder / f'{stem}.pcm_omitted_playbacks.csv')
    result.update(pdx_byte_budget_satisfied=len(payload) <= PDX_BYTE_LIMIT)
    result.update(pdx_bytes=len(payload), binary_evidence='assessment_sha256' if owned else 'current_export_attempt')
    if bindings is not None:
        stored = 0
        for binding in bindings:
            bank, slot = int(binding['bank']), int(binding['slot'])
            position = (bank * 96 + slot) * 8
            if bank != 0 or not 0 <= slot < 96 or position + 8 > len(payload):
                raise ValueError('PCM bank statistics exceed the verified single-bank PDX scope')
            offset, length = struct.unpack_from('>II', payload, position)
            if offset < 768 or offset + length > len(payload):
                raise ValueError('PCM binding exceeds current packed PDX bytes')
            stored += length
        result.update(retained_sample_count=len(bindings), retained_payload_bytes=stored)
    if projections is not None:
        result.update(retained_playback_count=len({r['playback_id'] for r in projections}),
                      tracks=sorted({r.get('mdx_track') or r.get('target_track') or r.get('track') or 'P'
                                     for r in projections}))
    if omissions is not None:
        omitted_ids = {str(r['playback_id']) for r in omissions}
        capacity = folder / f'{stem}.pcm.force_capacity.json'
        if capacity.is_file():
            # Capacity omissions are a separate source-preserving selection view.
            omitted_ids.update(str(r['playback_id']) for r in
                json.loads(capacity.read_text(encoding='utf-8')).get('rows', ())
                if r['action'] in ('omit', 'omit_normalization'))
        result['omitted_playback_count'] = len(omitted_ids)
    return result


def result_columns(summary):
    keys = ('selected', 'fallback_reason', 'source_gate_count', 'source_part_count',
            'silent_gate_count', 'rom_view_count', 'trajectory_variant_count',
            'sample_count', 'playback_count', 'reused_playback_count', 'asset_payload_bytes',
            'retained_sample_count', 'retained_playback_count', 'retained_payload_bytes',
            'tracks', 'omitted_playback_count', 'pdx_bytes',
            'merge_mode', 'merge_samples_before', 'merge_samples_after',
            'merge_bytes_before', 'merge_bytes_after', 'merged_playback_count', 'recovered_playback_count',
            'newly_omitted_playback_count', 'retained_playback_delta',
            'budget_limit', 'forced_sample_count', 'forced_playback_count',
            'pdx_byte_limit', 'pdx_byte_budget_satisfied',
            'budget_input_pdx_bytes', 'budget_output_pdx_bytes', 'pdx_format', 'sample_byte_limit')
    return {field: (','.join(summary[key]) if key == 'tracks' and summary.get(key) is not None
                    else summary.get(key) if summary.get(key) is not None else '')
            for field, key in zip(RESULT_FIELDS, keys)}


def format_lines(summary):
    if not summary:
        return []
    def number(key):
        return str(summary[key]) if summary.get(key) is not None else 'unmeasured'
    lines = [f"{summary.get('route_label', 'SegaPCM')} route: {summary.get('selected') or 'unmeasured'} (requested {summary.get('requested') or 'unmeasured'})",
             f"  Source gates {number('source_gate_count')}; parts {number('source_part_count')}; "
             f"silent gates {number('silent_gate_count')}; ROM views {number('rom_view_count')}; "
             f"trajectory variants {number('trajectory_variant_count')}",
             f"  Assets {number('sample_count')}; playbacks {number('playback_count')}; "
             f"reused playbacks {number('reused_playback_count')}; asset payload {number('asset_payload_bytes')} bytes",
             f"  Retained {number('retained_sample_count')} samples / {number('retained_playback_count')} playbacks; "
             f"payload {number('retained_payload_bytes')} bytes; tracks "
             f"{','.join(summary['tracks']) if summary.get('tracks') is not None else 'unmeasured'}; "
             f"omitted playbacks {number('omitted_playback_count')}; PDX {number('pdx_bytes')} bytes (including table)"]
    if summary.get('pdx_format') is not None:
        lines.append(f"  PDX format: {summary['pdx_format']}; sample byte limit {number('sample_byte_limit')}")
    if summary.get('fallback_reason'):
        lines.append('  Mix fallback: ' + str(summary['fallback_reason']).replace('\n', ' '))
    if summary.get('merge_mode') is not None:
        lines.extend([f"  Bank reduction: {summary['merge_mode']}; samples {number('merge_samples_before')} -> "
                      f"{number('merge_samples_after')}; payload {number('merge_bytes_before')} -> {number('merge_bytes_after')} bytes",
                      f"  Merged playbacks {number('merged_playback_count')}; "
                      f"recovered capacity playbacks {number('recovered_playback_count')}; "
                      f"newly omitted {number('newly_omitted_playback_count')}; "
                      f"retained delta {number('retained_playback_delta')}"])
    if summary.get('budget_limit') is not None:
        lines.append(f"  Budget cap {number('budget_limit')}; after similarity {number('budget_input_sample_count')} -> "
                     f"{number('merge_samples_after')}; forced replacement {number('forced_sample_count')} samples / "
                     f"{number('forced_playback_count')} playbacks")
    lines.append(f"  PDX byte budget: {number('pdx_bytes')}/{number('pdx_byte_limit')} bytes including table; "
                 f"within budget={number('pdx_byte_budget_satisfied')}")
    if summary.get('budget_input_pdx_bytes') is not None:
        lines.append(f"  Planned PDX bytes: {number('budget_input_pdx_bytes')} -> {number('budget_output_pdx_bytes')}")
    if summary.get('preview_directory'):
        lines.append(f"  PCM block WAVs: {summary['preview_directory']} ({summary['preview_wav_count']} files; all candidates)")
    if summary.get('merge_preview_directory'):
        lines.append(f"  PCM merge A/B WAVs: {summary['merge_preview_directory']} ({summary['merge_preview_wav_count']} files)")
    lines.append('  Runtime PCM buffer fit: unmeasured; packed size is not a playback guarantee')
    return lines


def console_lines(folder, stem, *, allow_binary=False):
    return format_lines(summarize(folder, stem, allow_binary=allow_binary))
