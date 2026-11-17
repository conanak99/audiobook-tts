"""Generate Vietnamese speech with VieNeu: GGUF on audio.cpp Metal by default, ONNX CPU as the fallback."""

import argparse
import atexit
import importlib.metadata
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

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
    parser.add_argument(
        '--backend',
        choices=['gguf', 'onnx'],
        default='gguf',
        help='gguf: audio.cpp on Metal (default; ONNX for anything it cannot do); onnx: CPU',
    )
    parser.add_argument('--list-voices', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.runs < 1 or args.warmup < 0 or args.threads < 1 or not args.text.strip():
        parser.error('Use nonempty text, runs >= 1, warmup >= 0 and threads >= 1.')

    if not args.worker:
        command, env = uv_command('vieneu', '-m', 'viettts', 'speak', '--engine', 'vieneu', *argv, '--worker')
        raise SystemExit(subprocess.run(command, env=env).returncode)
    import numpy as np
    import soundfile as sf

    started = time.perf_counter()
    voice = args.voice or 'Hải Đăng'
    onnx_model: list = []

    def onnx_tts():
        if not onnx_model:
            from vieneu import Vieneu

            onnx_model.append(Vieneu(backend='onnx', device='cpu', precision='fp32', threads=args.threads))
        return onnx_model[0]

    if args.list_voices:
        print(onnx_tts().list_preset_voices())
        return

    def onnx_generate():
        tts = onnx_tts()
        tmp = directory / '.onnx.wav'
        tts.save(tts.infer(args.text, voice=voice), str(tmp))
        samples, rate = sf.read(tmp, dtype='float32')
        tmp.unlink()
        return samples, rate

    directory = ROOT / 'outputs' / ('vieneu-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    directory.mkdir(parents=True)
    reason = None
    if args.backend == 'gguf':
        from . import vieneu_gguf

        reason = vieneu_gguf.unavailable()
        if reason is None:
            try:
                vieneu_gguf.ensure_model()
            except Exception as error:
                reason = f'could not get {vieneu_gguf.FILENAME} ({error})'
        if reason:
            print(f'GGUF unavailable: {reason}; using ONNX', file=sys.stderr, flush=True)
    # One GGUF session serves the warm-up and every run; each yield arrives when its take is done.
    takes = None
    if args.backend == 'gguf' and reason is None:
        jobs = [dict(id=f'take-{n}', text=args.text, voice=voice) for n in range(args.warmup + args.runs)]
        scratch = Path(tempfile.mkdtemp(prefix='vieneu-gguf-'))
        atexit.register(shutil.rmtree, scratch, True)
        takes = vieneu_gguf.synthesize(jobs, args.threads, scratch)
    else:
        onnx_tts()
    initialize_seconds = time.perf_counter() - started

    def generate():
        if takes is not None:
            _, samples, rate, error = next(takes)
            if samples is not None:
                return samples, rate, 'gguf'
            print(f'GGUF failed ({error}); using ONNX for this take', file=sys.stderr, flush=True)
        return (*onnx_generate(), 'onnx')

    for _ in range(args.warmup):
        generate()
    runs = []
    for i in range(args.runs):
        start = time.perf_counter()
        samples, rate, backend = generate()
        elapsed = time.perf_counter() - start
        wav = directory / f'run-{i + 1}.wav'
        sf.write(wav, samples, rate, subtype='PCM_16')
        if not samples.size or not np.isfinite(samples).all() or not np.any(samples):
            raise RuntimeError(f'Invalid or silent audio: {wav}')
        seconds = len(samples) / rate
        runs.append(
            {
                'file': str(wav),
                'backend': backend,
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
        'backend': 'gguf' if takes is not None else 'onnx',
        'gguf_unavailable': reason,
        'precision': 'q8_0' if takes is not None else 'fp32',
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
