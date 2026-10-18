"""Independent, bounded SCC waveform to YM2151 voice experiment.

No native source interpretation or production MML rendering happens here.
Operator arrays use register-bank order M1, M2, C1, C2.
"""
import csv
import ctypes
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

SEARCH_VERSION = 'bounded-grid-v1'
CARRIERS = {0: [3], 1: [3], 2: [3], 3: [3], 4: [2, 3],
            5: [1, 2, 3], 6: [1, 2, 3], 7: [0, 1, 2, 3]}


def wave_bytes(value):
    raw = bytes.fromhex(value) if isinstance(value, str) else bytes(int(v) % 256 for v in value)
    if len(raw) != 32:
        raise ValueError('An SCC waveform must contain exactly 32 bytes')
    return raw


def read_waveforms(path):
    path = Path(path)
    if path.suffix.lower() == '.csv':
        with path.open(newline='', encoding='utf-8-sig') as stream:
            rows = list(csv.DictReader(stream))
        waves = [wave_bytes(row.get('waveform_hex', row.get('hex', ''))) for row in rows]
    else:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(value, dict):
            value = value.get('waveforms', value.get('waveform_hex', value))
        if isinstance(value, str) or (isinstance(value, list) and len(value) == 32 and all(isinstance(v, int) for v in value)):
            value = [value]
        waves = [wave_bytes(v) for v in value]
    return list(dict.fromkeys(waves))


def part(algorithm=7, feedback=0, muls=(1, 1, 1, 1), tls=(127, 127, 127, 127), model='additive'):
    return dict(algorithm=algorithm, feedback=feedback, operator_muls=list(muls),
                operator_tl=list(tls), carriers=CARRIERS[algorithm], model=model)


def attenuation(amplitude):
    return 127 if amplitude <= 1e-12 else max(0, min(127, round(-20 * math.log10(amplitude) / .75)))


class OpmProbe:
    def __init__(self, root=None, clock=4000000, frequency=440., rate=48000):
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError('SCC fitting requires NumPy in the selected Python environment') from exc
        from psg_scc_opm import opm_pitch
        if not all(math.isfinite(v) and v > 0 for v in (clock, rate, frequency)):
            raise ValueError('Probe clock, sample rate and frequency must be finite and positive')
        self.np = np
        self.clock, self.rate = int(clock), int(rate)
        self.kc, self.kf, self.frequency = opm_pitch(frequency, clock)
        self.warmup = max(2048, math.ceil(16 * rate / self.frequency))
        self.frames = max(4096, math.ceil(32 * rate / self.frequency))
        if self.warmup + self.frames > 1000000:
            raise ValueError('Reference pitch is too low for the bounded probe')
        root = Path(root or Path(__file__).resolve().parents[1])
        self.root, self.requested_frequency = root, frequency
        core = root / '.tools/mdxtools'
        names = ('ym2151.c', 'ym2151.h', 'mamedef.h')
        if not all((core / n).is_file() for n in names):
            raise RuntimeError('Missing external YM2151 core; run bash scripts/setup_tools.sh --with-mdxtools')
        wrapper = root / 'scripts/scc_opm_probe.c'
        hashes = {n: hashlib.sha256((core / n).read_bytes()).hexdigest() for n in names}
        hashes['scc_opm_probe.c'] = hashlib.sha256(wrapper.read_bytes()).hexdigest()
        self.metadata = dict(core='external mdxtools YM2151', source_sha256=hashes,
                             sample_rate_hz=rate, warmup_frames=self.warmup, measured_frames=self.frames)
        digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:20]
        build = root / '.tools/scc-fm-fit'
        build.mkdir(parents=True, exist_ok=True)
        library = build / ('probe_' + digest + '.so')
        if not library.exists():
            gcc = shutil.which('gcc')
            if not gcc:
                raise RuntimeError('SCC fitting requires GCC (run this experiment in WSL)')
            result = subprocess.run([gcc, '-shared', '-fPIC', '-O2', '-I', str(core), str(wrapper),
                                     str(core / 'ym2151.c'), '-lm', '-o', str(library)],
                                    capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise RuntimeError('Failed to build external YM2151 probe: ' + result.stderr)
        self.library = ctypes.CDLL(str(library))
        self.library.scc_probe.argtypes = [ctypes.c_int] * 4 + [ctypes.POINTER(ctypes.c_int)] + [ctypes.c_int] * 3 + [ctypes.POINTER(ctypes.c_double)]
        self.library.scc_probe.restype = ctypes.c_int
        self.cache = {}
        calibration = part(tls=(0, 127, 127, 127))
        sine = self.render([calibration], normalized=False)
        self.calibration = float(np.sqrt(np.mean(sine * sine)) * math.sqrt(2))
        if self.calibration <= 0:
            raise RuntimeError('YM2151 carrier calibration produced silence')
        self.metadata['carrier_tl0_peak_units'] = self.calibration
        self.window = np.hanning(self.frames)

    def render(self, parts, normalized=True):
        key = json.dumps(parts, sort_keys=True)
        if normalized and key in self.cache:
            return self.cache[key]
        flat = [v for p in parts for v in [p['algorithm'], p['feedback'], *p['operator_muls'], *p['operator_tl']]]
        config = (ctypes.c_int * len(flat))(*flat)
        result = self.np.zeros(self.frames, dtype=self.np.float64)
        status = self.library.scc_probe(self.clock, self.rate, self.kc, self.kf, config,
                                       len(parts), self.warmup, self.frames,
                                       result.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
        if status:
            raise RuntimeError(f'YM2151 probe failed: {status}')
        if normalized:
            result /= self.calibration
            self.cache[key] = result
        return result

    def reference(self, raw, gain):
        np = self.np
        phase = np.arange(self.warmup, self.warmup + self.frames) * self.frequency / self.rate
        samples = np.array([v if v < 128 else v - 256 for v in raw], dtype=float) / 128
        samples -= samples.mean()
        return samples[np.floor((phase % 1) * 32).astype(int)] * gain

    def spectrum(self, signal):
        return abs(self.np.fft.rfft(signal * self.window)) * 2 / self.window.sum()

    def error(self, reference_spectrum, signal):
        difference = self.spectrum(signal) - reference_spectrum
        return float(self.np.sum(difference * difference) / max(1e-20, self.np.sum(reference_spectrum ** 2)))


def _additive(raw, gain, groups):
    import numpy as np
    x = np.array([v if v < 128 else v - 256 for v in raw]) / 128
    spectrum = np.fft.rfft(x - x.mean()) / 32
    amplitude = abs(spectrum) * 2
    return [part(muls=tuple(group) + (1,) * (4 - len(group)),
                 tls=tuple(attenuation(float(amplitude[k]) * gain) for k in group) + (127,) * (4 - len(group)))
            for group in groups]


def fit_waveform(raw, probe, gain=.125):
    """Fit finite candidates; all scores include unwanted FFT bins and gain error."""
    np = probe.np
    raw = wave_bytes(raw)
    probe.cache.clear()
    x = np.array([v if v < 128 else v - 256 for v in raw]) / 128
    amplitudes = abs(np.fft.rfft(x - x.mean()))
    dominant = sorted(range(1, 16), key=lambda h: (-float(amplitudes[h]), h))
    reference = probe.reference(raw, gain)
    spec = probe.spectrum(reference)
    candidates = {}
    def save(name, parts):
        signal = probe.render(parts)
        candidates[name] = dict(parts=parts, spectral_error=probe.error(spec, signal),
                                rms=float(np.sqrt(np.mean(signal ** 2))),
                                reference_rms=float(np.sqrt(np.mean(reference ** 2))))
    save('additive', _additive(raw, gain, [sorted(dominant[:4])]))
    save('additive8', _additive(raw, gain, [sorted(dominant[:4]), sorted(dominant[4:8])]))
    low = sorted(range(1, 8), key=lambda h: (-float(amplitudes[h]), h))[:4]
    high = sorted(range(8, 16), key=lambda h: (-float(amplitudes[h]), h))[:4]
    save('additive8-lowhigh', _additive(raw, gain, [sorted(low), sorted(high)]))
    fm_candidates = []
    # Fixed, finite coarse grid. Carrier-only scaling leaves modulation indices fixed.
    for algorithm in (0, 4, 5, 6):
        for ratio in (1, 2, 3, 5, 7):
            for feedback in (0, 3):
                for level in (24, 40, 56):
                    tls = [level] * 4
                    for op in CARRIERS[algorithm]:
                        tls[op] = attenuation(gain / len(CARRIERS[algorithm]))
                    p = part(algorithm, feedback, (ratio, 1, 1, 1), tls, 'fm')
                    fm_candidates.append((probe.error(spec, probe.render([p])), p))
    fm_candidates.sort(key=lambda item: item[0])
    # Local TL refinement of the best coarse voices, including independent modulator TL.
    refined = fm_candidates[:]
    for _, seed in fm_candidates[:3]:
        for op in range(4):
            for delta in (-8, 8):
                p = dict(seed, operator_tl=list(seed['operator_tl']))
                p['operator_tl'][op] = max(0, min(127, p['operator_tl'][op] + delta))
                refined.append((probe.error(spec, probe.render([p])), p))
    refined.sort(key=lambda item: item[0])
    best = refined[0][1]
    # Rank deficits, but rescore actual A+B. No imaginary negative-phase cancellation.
    residual = np.maximum(0, spec - probe.spectrum(probe.render([best])))
    bins = np.fft.rfftfreq(probe.frames, 1 / probe.rate)
    strengths = []
    for h in range(1, 16):
        region = abs(bins - h * probe.frequency) <= 2 * probe.rate / probe.frames
        strengths.append((float(np.max(residual[region])) if np.any(region) else 0., h))
    selected = sorted(sorted(strengths, reverse=True)[:4], key=lambda v: v[1])
    correction = part(muls=[h for _, h in selected],
                      tls=[attenuation(a) for a, _ in selected])
    additive_options = [correction, part()] + _additive(raw, gain * .5, [sorted(dominant[:4])])
    options = [[a, b] for _, a in refined[:4] for b in additive_options]
    save('fm-additive', min(options, key=lambda parts: probe.error(spec, probe.render(parts))))
    # Coarse joint two-voice search: independent carrier attenuation, same fixed FM grid.
    halves = []
    for _, seed in refined[:6]:
        p = dict(seed, operator_tl=list(seed['operator_tl']))
        for op in p['carriers']:
            p['operator_tl'][op] = min(127, p['operator_tl'][op] + 8)
        halves.append(p)
    pairs = [[a, b] for i, a in enumerate(halves) for b in halves[i:]]
    pairs += [[best, part(model='fm')]]
    save('fm-fm', min(pairs, key=lambda parts: probe.error(spec, probe.render(parts))))
    return dict(waveform_hex=raw.hex(), waveform_sha256=hashlib.sha256(raw).hexdigest(),
                source_dc=float(x.mean()), candidates=candidates), reference


def pitch_check(raw, parts, probe, gain):
    """Measure unchanged fitted parameters at another pitch; no reoptimization."""
    np = probe.np
    signal = probe.render(parts)
    reference = probe.reference(raw, gain)
    rms = float(np.sqrt(np.mean(signal ** 2)))
    reference_rms = float(np.sqrt(np.mean(reference ** 2)))
    return dict(requested_frequency_hz=probe.requested_frequency,
                actual_frequency_hz=probe.frequency, kc=probe.kc, kf=probe.kf,
                spectral_error=probe.error(probe.spectrum(reference), signal),
                reference_gain=gain, rms=rms, reference_rms=reference_rms,
                rms_gain_ratio=rms / reference_rms if reference_rms > 1e-20 else None,
                reoptimized=False)


def fit_bank(waveforms, probe, gain=.125, cache_dir=None, check_frequencies=None):
    if not math.isfinite(gain) or not 0 < gain <= 1:
        raise ValueError('Reference gain must be finite and in (0,1]')
    requested = list(dict.fromkeys(check_frequencies if check_frequencies is not None else
                                   (probe.requested_frequency / 2, probe.requested_frequency, probe.requested_frequency * 2)))
    check_probes = [probe if frequency == probe.requested_frequency else
                    OpmProbe(probe.root, probe.clock, frequency, probe.rate) for frequency in requested]
    bank = dict(schema='scc-fm-fit-v1', target_chip='YM2151', target_clock_hz=probe.clock,
                reference_gain=gain, reference_frequency_hz=probe.frequency,
                search_version=SEARCH_VERSION, emulator=probe.metadata,
                check_frequencies_hz=requested, waveforms={})
    cache_dir = Path(cache_dir) if cache_dir else None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
    for raw in map(wave_bytes, waveforms):
        wave_hash = hashlib.sha256(raw).hexdigest()
        identity = dict(wave=wave_hash, version=SEARCH_VERSION, clock=probe.clock,
                        frequency=probe.frequency, gain=gain, emulator=probe.metadata)
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        path = cache_dir / (key + '.json') if cache_dir else None
        if path and path.exists():
            result = json.loads(path.read_text())
        else:
            result, _ = fit_waveform(raw, probe, gain)
            if path:
                path.write_text(json.dumps(result, indent=2) + '\n')
        for candidate in result['candidates'].values():
            candidate['pitch_checks'] = [pitch_check(raw, candidate['parts'], check, gain) for check in check_probes]
        for check in check_probes:
            if check is not probe:
                check.cache.clear()
        bank['waveforms'][wave_hash] = result
    return bank
