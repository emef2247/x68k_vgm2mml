"""PSG/SCC OPM target projections with selectable PSG tone models.

No source Key events are invented: target oscillators stay keyed on and source
amplitude/muting is projected separately. Scoped noise-only output is approximated; hardware EG remains unsupported.
This is a spectral approximation, not a native OPM interpretation of the input.
"""
from dataclasses import asdict, dataclass
import cmath
import csv
import hashlib
import json
import math
from pathlib import Path

from opm_mdx import mdx_tick, projected_samples
from psg_opm_fm import FmVoice, tone_tl

KC_CODES = (0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14)
OPM_CLOCK = 4000000


@dataclass(frozen=True)
class AdditiveVoice:
    identity: str
    harmonics: tuple
    amplitudes: tuple
    phases: tuple
    dc: float
    retained_ac_fraction: float


def square_voice():
    return AdditiveVoice('psg_square', (1, 3, 5, 7),
                         tuple(4 / (math.pi * n) for n in (1, 3, 5, 7)),
                         (0.,) * 4, 0., sum(8 / (math.pi * n) ** 2 for n in (1, 3, 5, 7)))


def waveform_voice(waveform_hex,*,offset=0):
    raw = bytes.fromhex(waveform_hex)
    if len(raw) != 32:
        raise ValueError('SCC additive target requires all 32 waveform bytes')
    x = [(b if b < 128 else b - 256) / 128 for b in raw]
    dc = sum(x) / 32
    ft = [sum((v - dc) * cmath.exp(-2j * math.pi * k * j / 32)
              for j, v in enumerate(x)) / 32 for k in range(17)]
    energy = [abs(v) ** 2 * (1 if k in (0, 16) else 2) for k, v in enumerate(ft)]
    chosen = sorted(sorted(range(1,16),key=lambda k:(-energy[k],k))[offset:offset+4])
    total = sum(energy[1:])
    return AdditiveVoice('scc_' + hashlib.sha256(raw).hexdigest()[:16]+('_extra' if offset else ''),
                         tuple(chosen), tuple(2 * abs(ft[k]) for k in chosen),
                         tuple(cmath.phase(ft[k]) for k in chosen), dc,
                         sum(energy[k] for k in chosen) / total if total > 1e-20 else 0.)


def source_frequency(chip, clock_hz, period):
    """VGM AY clock /16; VGM K051649 convention /16/(period+1).

    The VGM/libvgm SCC clock is half the physical wave-step clock. Do not
    apply the physical-clock /32 formula directly to this header field.
    """
    if chip == 'psg':
        return clock_hz / (16 * max(1, period))
    if chip == 'scc':
        return 0. if period <= 8 else clock_hz / (16 * (period + 1))
    raise ValueError('Unknown source chip')


def opm_pitch(frequency_hz, clock_hz=OPM_CLOCK, *, clamp=False):
    # Yamaha reference: OCT4 NOTE10 KF0 MUL1 at 3.579545 MHz = 440 Hz.
    if not math.isfinite(frequency_hz) or frequency_hz <= 0:
        raise ValueError('OPM pitch requires a finite positive frequency')
    reference = 440 * clock_hz / 3579545
    q = int(math.floor((56 + 12 * math.log2(frequency_hz / reference)) * 64 + .5))
    if not 0 <= q < 96 * 64:
        if not clamp:
            raise ValueError(f'Frequency outside OPM KC/KF range: {frequency_hz:.6f} Hz')
        q = max(0, min(96 * 64 - 1, q))
    note, fraction = divmod(q, 64)
    octave, index = divmod(note, 12)
    actual = reference * 2 ** ((q / 64 - 56) / 12)
    return octave * 16 + KC_CODES[index], fraction * 4, actual


def carrier_tl(amplitude):
    if amplitude <= 1e-10:
        return 127
    return max(0, min(127, int(math.floor(-20 * math.log10(amplitude) / .75 + .5))))


@dataclass(frozen=True)
class TargetWrite:
    write_id: int
    source_chip: str
    source_ch: int | None
    source_row: int | None
    vgmticks: int
    mdx_tick: int
    target_ch: int
    register: int
    data: int
    reason: str


@dataclass
class AdditivePlan:
    writes: list
    rows: list
    voices: dict
    source_end: int
    settings: dict
    # Optional result of the separate musical projection and canonical OPM path.
    structured_context: object = None
    source_music: object = None
    source_music_segments: object = None
    scc_music: object = None
    scc_music_segments: object = None

    @property
    def end_tick(self):
        return mdx_tick(self.source_end)

    def scheduled_writes(self):
        return sorted(self.writes, key=lambda w: (w.mdx_tick, w.target_ch, w.write_id))

    def render(self, title):
        title = title.replace('"', "'").replace('\r', ' ').replace('\n', ' ')
        lines = [f'#title "{title}"',
                 '; PSG/SCC OPM target; PSG model=' + self.settings.get('psg_model', 'additive') + '.',
                 '; A..E=SCC1..5; PSG fixed map in target JSON; noise owns H. Held keys; raw controls retain trajectories.',
                 '; Scoped noise-only support; hardware envelope unsupported; phase/mix approximate.', 'A @t255']
        for ch in sorted({w.target_ch for w in self.writes}):
            track = chr(65 + ch)
            tick = 0
            for w in (w for w in self.writes if w.target_ch == ch):
                gap = w.mdx_tick - tick
                while gap:
                    count = min(gap, 65535)
                    lines.append(f'{track} r%{count}')
                    gap -= count
                lines.append(f'{track} y{w.register},{w.data}')
                tick = w.mdx_tick
            gap = self.end_tick - tick
            while gap:
                count = min(gap, 65535)
                lines.append(f'{track} r%{count}')
                gap -= count
        return '\n'.join(lines) + '\n'

    def dump(self, out, stem):
        out = Path(out)
        def csv_file(suffix, rows):
            if not rows:
                return
            with (out / (stem + suffix)).open('w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        if self.source_music is not None:
            from psg_note_units import dump
            dump(self.source_music,self.source_music_segments,out/(stem+'.psg.music.csv'))
        if self.scc_music is not None:
            from scc_note_units import dump
            dump(self.scc_music,self.scc_music_segments,out/(stem+'.scc.music.csv'))
        csv_file('.opm_target.csv', self.rows)
        csv_file('.opm_writes.csv', [asdict(w) for w in self.writes])
        voice_rows = [asdict(v) for v in self.voices.values()]
        columns = tuple(dict.fromkeys(k for r in voice_rows for k in r))
        csv_file('.opm_voices.csv', [{k: r.get(k, '') for k in columns} for r in voice_rows])
        from opm_target_state import build_target_trajectory
        trajectory = build_target_trajectory(self.scheduled_writes(), end_tick=self.end_tick,
                                             source_end_vgmticks=self.source_end)
        trajectory.dump(state_csv=out / (stem + '.opm_target.state.csv'),
                        intervals_csv=out / (stem + '.opm_target.intervals.csv'))
        report = dict(self.settings, source_end_vgmticks=self.source_end,
                      end_mdx_tick=self.end_tick, returned_end_expected=projected_samples(self.end_tick),
                      target_writes=len(self.writes), target_rows=len(self.rows),
                      source_rows=len({(r['source_chip'],r['source_ch'],r['source_row']) for r in self.rows}), voices=len(self.voices),
                      musical_note_count_not_inferred=True,
                      source_scc_musical_note_count=sum(not note.rest for notes in (self.scc_music or {}).values() for note in notes),
                      source_musical_note_count=sum(not note.rest for notes in (self.source_music or {}).values() for note in notes),
                      phase_matching=False,
                      gain_calibrated=False,
                      psg_volume_model=('fixed TL curve with 8-step headroom' if self.settings.get('psg_model') == 'fm'
                                        else 'approximate 3 dB per level'),
                      range_clamped_rows=sum('clamped' in r['approximation'] for r in self.rows),
                      scc_volume_model='linear volume/15', source_loop_policy='rendered traversal; original loop metadata retained separately',
                      projected_state_trajectory=trajectory.summary())
        (out / (stem + '.opm_target.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def project(psg, scc, *, psg_clock, scc_clock, end_vgmticks, psg_gain=None,
            scc_gain=.125, psg_model='additive', pitch_policy=None, force=False, noise_source_ch='auto',
            scc_model='additive',scc_voice_bank=None,source_selection='all',psg_output='opm'):
    if psg_output not in ('opm','pcm'):raise ValueError('PSG output must be opm or pcm')
    if source_selection=='scc' and psg_output=='pcm':raise ValueError('--scc-only cannot include PSG PCM output')
    if source_selection not in ('all','psg','scc'):
        raise ValueError('Source selection must be all, psg or scc')
    if psg_model not in ('fm', 'additive'):
        raise ValueError('PSG model must be fm or additive')
    pitch_policy = pitch_policy or ('clamp' if psg_model == 'fm' else 'error')
    if pitch_policy not in ('clamp', 'error'):
        raise ValueError('Pitch policy must be clamp or error')
    psg_gain = (1. if psg_model == 'fm' else .125) if psg_gain is None else psg_gain
    if not math.isfinite(psg_gain) or not 0 < psg_gain <= (1. if psg_model == 'fm' or psg_output=='pcm' else .5):
        raise ValueError('PSG gain exceeds the selected model range')
    if not math.isfinite(scc_gain) or not 0 < scc_gain <= .5:
        raise ValueError('SCC gain must be positive and at most 0.5')
    plan = AdditivePlan([], [], {}, end_vgmticks,
                        dict(psg_clock=psg_clock, scc_clock=scc_clock, target_clock=OPM_CLOCK,
                             psg_gain=psg_gain, scc_gain=scc_gain, psg_model=psg_model,
                             pitch_policy=pitch_policy, scc_model='additive', force_enabled=force, forced_omissions=[]))
    from psg_note_units import interpret, membership, interval_end
    plan.source_music=interpret(psg,end=end_vgmticks)
    plan.source_music_segments=psg
    note_membership=membership(plan.source_music)
    from scc_note_units import interpret as interpret_scc
    plan.scc_music=interpret_scc(scc.segments,end=end_vgmticks)
    plan.scc_music_segments=scc.segments
    scc_membership=membership(plan.scc_music)
    selected_psg=psg if source_selection!='scc' and psg_output=='opm' else {}
    selected_scc=scc.segments if source_selection!='psg' else {}
    plan.settings.update(psg_output=psg_output,source_selection=source_selection,excluded_sources=[dict(
        chip=chip,reason='explicit source-only target selection',
        source_rows=sum(map(len,channels.values()))) for chip,channels in
        (('psg',psg),('scc',scc.segments)) if source_selection!='all' and chip!=source_selection],
        source_segments_retained=True)
    from psg_opm_noise import NoiseVoice, candidates as noise_candidates, rate as noise_rate
    candidates=noise_candidates(selected_psg,end=end_vgmticks)
    noise_owner=(candidates[0] if candidates and psg_model=='fm' else None) if noise_source_ch=='auto' else noise_source_ch
    if psg_model!='fm':noise_owner=None
    psg_map={ch:ch+5 for ch in range(3)}
    if noise_owner is not None:
        psg_map[2],psg_map[noise_owner]=psg_map[noise_owner],7
    plan.settings.update(psg_channel_map=psg_map,noise_source_ch=noise_owner,
        noise_policy='one fixed noise-only owner on OPM7; N0..30 nearest nominal shift rate',
        noise_phase_matching=False,source_note_policy='MSX PSG/SCC extract_notes in original samples; software volume runs retained',
        source_interval_extensions=[dict(source_ch=ch,source_row=len(rows)-1,
            original_end=rows[-1].vgmticks_end,interpreted_end=end_vgmticks,
            reason='last observed state carried through remaining VGM wait')
            for ch,rows in psg.items() if rows and rows[-1].vgmticks_end<end_vgmticks],
        scc_source_interval_extensions=[dict(source_ch=ch,source_row=len(rows)-1,
            original_end=rows[-1].vgmticks_end,interpreted_end=end_vgmticks,
            reason='last observed SCC state carried through remaining VGM wait')
            for ch,rows in scc.segments.items() if rows and rows[-1].vgmticks_end<end_vgmticks])
    from scc_voice_bank import prepare,FittedVoice,levels as fitted_levels
    select_scc,extra_map,scc_report=prepare(selected_scc,selected_psg,psg_map,end=end_vgmticks,
        model=scc_model,bank_path=scc_voice_bank,clock=OPM_CLOCK,voice=waveform_voice,interval_end=interval_end)
    plan.settings.update(scc_model=scc_model,scc_voice_projection=scc_report)
    for chip, channels, clock, gain in [('scc', selected_scc, scc_clock, scc_gain),
                                        ('psg', selected_psg, psg_clock, psg_gain)]:
        for ch, segments in sorted(channels.items()):
            if not 0 <= ch < (5 if chip == 'scc' else 3):
                raise ValueError('Unsupported source channel')
            target = ch if chip == 'scc' else psg_map[ch]
            lanes=[(target,0)]+([(extra_map[ch],1)] if chip=='scc' and ch in extra_map else [])
            for target,lane in lanes:
                fm = chip == 'psg' and psg_model == 'fm'
                voice_profile = FmVoice() if fm else None
                control = (voice_profile.feedback << 3 | voice_profile.algorithm) if fm else 7
                # Silent-only parts still appear in the projection CSV, but receive
                # no target oscillator. Hardware-EG/noise checks below are separate.
                used = any((s.volume > 0 or (chip == 'psg' and s.envelope_enabled)) and (s.enabled if chip == 'scc' else s.mode)
                           for s in segments)
                if used and clock <= 0:
                    raise ValueError('Missing source clock for an active part')
                cache = {}
                row_id = None
                sample = 0
                def emit(reg, data, reason, force=False):
                    if not force and cache.get(reg) == data:
                        return
                    cache[reg] = data
                    plan.writes.append(TargetWrite(len(plan.writes), chip, ch, row_id, sample,
                                                    mdx_tick(sample), target, reg, data, reason))
                if used:
                    emit(8, target, 'initial key off', True)
                    if chip=='psg' and ch==noise_owner:emit(15,0,'initial noise disabled')
                    emit(0x20 + target, control, 'selected voice; outputs muted')
                    emit(0x38 + target, 0, 'disable channel LFO')
                    emit(0x28 + target, 0, 'initial pitch')
                    emit(0x30 + target, 0, 'initial pitch')
                    for bank in range(4):
                        offset = target + 8 * bank
                        for reg, data in [(0x40, voice_profile.operator_muls[bank] if fm else 1),
                                          (0x60, 27 if fm and bank == 0 else 127), (0x80, 31),
                                          (0xa0, 0), (0xc0, 0), (0xe0, 0 if fm else 15)]:
                            emit(reg + offset, data, 'held voice operator')
                    emit(8, 0x78 + target, 'one held key per source part', True)
                for row_id, s in enumerate(segments):
                    sample = s.vgmticks
                    if sample is None or s.vgmticks_end is None or not 0 <= sample <= s.vgmticks_end <= end_vgmticks:
                        raise ValueError('Segment needs valid native sample boundaries')
                    interpreted_end=interval_end(segments,row_id,end_vgmticks)
                    omission_reason = ''
                    if chip == 'psg' and s.mode and (s.volume or s.envelope_enabled):
                        if s.envelope_enabled or s.mode==3 or (s.mode==2 and ch!=noise_owner and interpreted_end>sample):
                            if not force:
                                raise ValueError(f'PSG ch{ch} row{row_id}: noise/hardware EG not implemented')
                            reasons = []
                            if s.mode in (2, 3):
                                reasons.append('psg_noise' if s.mode==3 or psg_model!='fm' else 'psg_noise_owner_conflict')
                            if s.envelope_enabled:
                                reasons.append('psg_hardware_envelope')
                            omission_reason = '+'.join(reasons)
                            plan.settings['forced_omissions'].append(dict(source_ch=ch, source_row=row_id,
                                source_channel=ch+1, start_vgmticks=sample, end_vgmticks=interpreted_end,
                                source_segment_end_vgmticks=s.vgmticks_end,reason=omission_reason))
                    active = bool(not omission_reason and s.volume and (s.enabled if chip == 'scc' else s.mode))
                    zero_noise=bool(chip=='psg' and s.mode==2 and interpreted_end==sample and ch!=noise_owner)
                    if zero_noise:active=False
                    segment_clock = getattr(s, 'source_clock_hz', clock)
                    noise=bool(chip=='psg' and ch==noise_owner and s.mode==2 and active)
                    noise_n=noise_source_rate=noise_target_rate=noise_error=''
                    if noise:
                        noise_n,noise_source_rate,noise_target_rate,noise_error=noise_rate(segment_clock,s.noise_period)
                    freq = source_frequency(chip, segment_clock, s.tone_period) if active and not noise else (440. if noise else 0.)
                    approximation = ('--force: ' + omission_reason + '; entire interval muted' if omission_reason else
                                     'zero-source-duration noise state; no target oscillator' if zero_noise else '')
                    if active and freq and not noise:
                        try:
                            opm_pitch(freq)
                        except ValueError:
                            if pitch_policy == 'clamp':
                                approximation = 'out-of-range pitch clamped to nearest KC/KF boundary'
                            else:
                                if mdx_tick(sample) != mdx_tick(s.vgmticks_end):
                                    raise
                                approximation = 'out-of-range transient has zero target duration; omitted'
                                active = False
                    voice = None
                    kc = kf = actual = error = ''
                    tls = ()
                    first = len(plan.writes)
                    if active and freq:
                        control=7 if noise else ((voice_profile.feedback<<3 | voice_profile.algorithm) if fm else 7)
                        if chip=='psg' and ch==noise_owner:
                            emit(15,(128|noise_n) if noise else 0,'noise-only rate approximation' if noise else 'restore tone; noise disabled')
                        voice = NoiseVoice() if noise else voice_profile if fm else (select_scc(s.waveform_hex,lane,ch) if chip=='scc' else square_voice())
                        if voice is None:
                            voice=AdditiveVoice('scc_silent_secondary',(1,1,1,1),(0.,)*4,(0.,)*4,0.,0.)
                        plan.voices.setdefault(voice.identity, voice)
                        fitted=isinstance(voice,FittedVoice)
                        if fitted:control=voice.algorithm | voice.feedback<<3
                        active=fm or (any(voice.operator_tl[i]<127 for i in voice.carriers) if fitted else any(a>1e-10 for a in voice.amplitudes))
                        if active:
                            kc, kf, actual = opm_pitch(freq, clamp=pitch_policy == 'clamp')
                            error = 1200 * math.log2(actual / freq)
                            level = s.volume / 15 if chip == 'scc' else 10 ** (-3 * (15 - s.volume) / 20)
                            tls = ((127,127,127,tone_tl(s.volume,gain)) if noise else
                                   (27,127,tone_tl(s.volume,gain),127) if fm else fitted_levels(voice,gain,s.volume) if fitted else
                                   tuple(carrier_tl(gain*level*a) for a in voice.amplitudes))
                            if noise:approximation='noise-only nominal shift-rate approximation; phase/spectrum unverified'
                            emit(0x28 + target, kc, 'noise carrier placeholder pitch' if noise else 'source pitch')
                            emit(0x30 + target, kf, 'source pitch')
                            for bank, (harmonic, tl) in enumerate(zip(voice.operator_muls if fm or fitted else voice.harmonics, tls)):
                                emit(0x40 + target + bank * 8, harmonic, 'FM multiplier' if fm else 'selected harmonic')
                                emit(0x60 + target + bank * 8, tl, 'FM carrier level' if fm else 'spectrum times source volume')
                            emit(0x20 + target, 0xc0 | control, 'enable stereo output')
                    else:
                        active = False
                    if not active and used:
                        emit(0x20 + target, control, 'source mute or nonoscillating source')
                    note=(note_membership if chip=='psg' else scc_membership).get((ch,row_id))
                    plan.rows.append(dict(source_chip=chip, source_ch=ch, source_row=row_id,
                                          noise_period=getattr(s,'noise_period',''),
                                          noise_effective_clock_hz=segment_clock if noise else '',
                                          noise_n=noise_n,noise_source_rate_hz=noise_source_rate,
                                          noise_target_rate_hz=noise_target_rate,noise_error_cents=noise_error,
                                          musical_note_id=note[0] if note else None,
                                          musical_note_start=note[1] if note else None,
                                          musical_note_end=note[2] if note else None,
                                          musical_note_rest=note[3] if note else None,
                                          vgmticks=sample, vgmticks_end=s.vgmticks_end,
                                          interpreted_vgmticks_end=interpreted_end,
                                          mdx_tick=mdx_tick(sample), target_track=chr(65 + target),
                                          source_period=s.tone_period, source_volume=s.volume,
                                          source_waveform_id=getattr(s, 'waveform_id', ''),
                                          source_mode=getattr(s, 'mode', ''), target_audible=active,
                                          approximation=approximation,
                                          voice_id=voice.identity if voice else '',
                                          voice_model='noise-only' if noise else 'fm' if fm else voice.model if isinstance(voice,FittedVoice) else 'additive',
                                          target_lane=lane,requested_scc_model=scc_model if chip=='scc' else '',
                                          target_algorithm=control & 7, target_feedback=control >> 3, frequency_hz='' if noise else freq,
                                          target_kc=kc, target_kf=kf, target_frequency_hz='' if noise else actual,
                                          pitch_error_cents='' if noise else error, carrier_tl=json.dumps(tls),
                                          target_write_ids=json.dumps(list(range(first, len(plan.writes))))))
                if used:
                    sample, row_id = end_vgmticks, None
                    if chip=='psg' and ch==noise_owner:emit(15,0,'terminal noise disabled')
                    emit(0x20 + target, control, 'terminal mute at VGM end')
                    emit(8, target, 'terminal key off', True)
    return plan


def verify_writes(plan, returned_controls, initialization, returned_end):
    """Check the generated target plan, not cross-chip acoustic equivalence."""
    prefix_ok = returned_controls[:len(initialization)] == initialization
    actual = returned_controls[len(initialization):] if prefix_ok else returned_controls
    expected = [(projected_samples(w.mdx_tick), w.register, w.data) for w in plan.scheduled_writes()]
    mismatches = [(i, a, b) for i, (a, b) in enumerate(zip(expected, actual)) if a != b]
    key_expected = [x for x in expected if x[1] == 8]
    key_actual = [x for x in actual if x[1] == 8]
    return dict(passed=prefix_ok and expected == actual and returned_end == projected_samples(plan.end_tick),
                scope='exact generated OPM target controls/timing; not source acoustic equivalence',
                initializer_matches=prefix_ok, expected_controls=len(expected), returned_controls=len(actual),
                control_mismatches=len(mismatches) + abs(len(expected) - len(actual)),
                first_mismatches=mismatches[:8], key_commands_match=key_expected == key_actual,
                target_keyon_commands=sum(bool(data & 0x78) for _, _, data in key_expected),
                returned_keyon_commands=sum(bool(data & 0x78) for _, _, data in key_actual),
                expected_end=projected_samples(plan.end_tick), returned_end=returned_end)
