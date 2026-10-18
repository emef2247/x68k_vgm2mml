#!/usr/bin/env python3
"""Fit static SCC waveforms; this is an experiment, not a VGM frontend."""
import argparse
import csv
import json
from pathlib import Path
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'py'))
from scc_fm_fit import OpmProbe, fit_bank, read_waveforms


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('waveforms', type=Path, nargs='+', help='JSON 32-byte waveform(s), hex string(s), or SCC waveform CSV')
    parser.add_argument('--outdir', required=True, type=Path)
    parser.add_argument('--frequency', type=float, default=440.)
    parser.add_argument('--check-frequency', type=float, action='append', help='Repeat to override default half/reference/double pitch checks')
    parser.add_argument('--clock', type=int, default=4000000)
    parser.add_argument('--gain', type=float, default=.125)
    parser.add_argument('--audio', action='store_true', help='Also save matched-scale source and candidate WAVs')
    args = parser.parse_args(argv)
    try:
        waves = list(dict.fromkeys(raw for path in args.waveforms for raw in read_waveforms(path)))
        probe = OpmProbe(clock=args.clock, frequency=args.frequency)
        args.outdir.mkdir(parents=True, exist_ok=True)
        bank = fit_bank(waves, probe, args.gain, args.outdir / 'cache', args.check_frequency)
        (args.outdir / 'voices.json').write_text(json.dumps(bank, indent=2) + '\n')
        with (args.outdir / 'metrics.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['waveform_sha256', 'model', 'channels', 'measurement', 'requested_frequency_hz', 'actual_frequency_hz', 'kc', 'kf', 'reference_gain', 'rms_gain_ratio', 'reoptimized', 'spectral_error', 'rms', 'reference_rms'])
            writer.writeheader()
            for identity, entry in bank['waveforms'].items():
                for model, candidate in entry['candidates'].items():
                    for check in candidate['pitch_checks']:
                        writer.writerow(dict(waveform_sha256=identity, model=model, channels=len(candidate['parts']),
                                             measurement='fixed_voice_pitch_transfer', **check))
                if args.audio:
                    signals = {'source': probe.reference(bytes.fromhex(entry['waveform_hex']), args.gain)}
                    signals.update({model: probe.render(value['parts']) for model, value in entry['candidates'].items()})
                    for model, signal in signals.items():
                        # Fixed common scale: never normalize each file independently.
                        pcm = probe.np.clip(signal * 32767, -32768, 32767).astype('<i2').tobytes()
                        with wave.open(str(args.outdir / (identity[:16] + '_' + model + '.wav')), 'wb') as stream:
                            stream.setnchannels(1)
                            stream.setsampwidth(2)
                            stream.setframerate(probe.rate)
                            stream.writeframes(pcm)
        print('Voice bank:', args.outdir / 'voices.json')
        print('Metrics:', args.outdir / 'metrics.csv')
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
