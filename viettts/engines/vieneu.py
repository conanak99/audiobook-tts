"""Generate Vietnamese speech with VieNeu's ONNX CPU runtime."""

import argparse
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime

from viettts.paths import ROOT, uv_command

# Keep ONNX external data beside its graph as real files.
os.environ['HF_HUB_DISABLE_SYMLINKS'] = '1'
os.environ.setdefault('HF_HOME', str(ROOT / '.cache' / 'huggingface'))
os.environ.setdefault('XDG_CACHE_HOME', str(ROOT / '.cache'))
os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT / '.cache' / 'numba'))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.cache' / 'matplotlib'))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='python3 -m viettts speak --engine vieneu', description=__doc__)
    parser.add_argument('--text', default='Xin chào! Hôm nay chúng ta kiểm tra chất lượng giọng nói tiếng Việt.')
    parser.add_argument('--voice', help='Default: Hải Đăng')
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--list-voices', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.runs < 1 or args.warmup < 0 or args.threads < 1 or not args.text.strip():
        parser.error('Use nonempty text, runs >= 1, warmup >= 0 and threads >= 1.')

    if not args.worker:
        command, env = uv_command('vieneu', '-m', 'viettts', 'speak', '--engine', 'vieneu', *argv, '--worker')
        raise SystemExit(subprocess.run(command, env=env).returncode)
    started = time.perf_counter()
    from vieneu import Vieneu

    tts = Vieneu(backend='onnx', device='cpu', precision='fp32', threads=args.threads)
    voice = args.voice or 'Hải Đăng'

    def generate():
        return tts.infer(args.text, voice=voice)

    save = tts.save
    voices = tts.list_preset_voices
    backend = tts.backend
    initialize_seconds = time.perf_counter() - started
    if args.list_voices:
        print(voices())
        return

    import numpy as np
    import soundfile as sf

    directory = ROOT / 'outputs' / ('vieneu-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    directory.mkdir(parents=True)
    for _ in range(args.warmup):
        generate()
    runs = []
    for i in range(args.runs):
        start = time.perf_counter()
        audio = generate()
        elapsed = time.perf_counter() - start
        wav = directory / f'run-{i + 1}.wav'
        save(audio, str(wav))
        samples, rate = sf.read(wav)
        if not samples.size or not np.isfinite(samples).all() or not np.any(samples):
            raise RuntimeError(f'Invalid or silent audio: {wav}')
        seconds = len(samples) / rate
        runs.append(
            {
                'file': str(wav),
                'synthesis_seconds': elapsed,
                'audio_seconds': seconds,
                'rtf': elapsed / seconds,
                'sample_rate': rate,
            }
        )
        print(json.dumps(runs[-1], ensure_ascii=False), flush=True)
    report = {
        'engine': 'vieneu',
        'package_version': importlib.metadata.version('vieneu'),
        'python': platform.python_version(),
        'machine': platform.platform(),
        'backend': backend,
        'precision': 'fp32',
        'threads': args.threads,
        'text': args.text,
        'voice': voice,
        'warmup_runs': args.warmup,
        'initialize_seconds_including_downloads': initialize_seconds,
        'runs': runs,
        'median_synthesis_seconds': statistics.median(r['synthesis_seconds'] for r in runs),
        'median_rtf': statistics.median(r['rtf'] for r in runs),
    }
    (directory / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Results: {directory / "results.json"}')


if __name__ == '__main__':
    main()
