#!/usr/bin/env python3
"""Run Drama-3 with mixed 4/8-bit MLX weights on Apple Silicon."""

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from viettts.paths import ROOT, uv_command

REPO = 'mlx-community/fish-audio-drama-3-4bit'
REVISION = '2b0c8028998533972e77359cce56b8bf1c5d6d4a'  # V2: converted from Fish Audio's 2026-10-29 weights
MODEL = ROOT / 'models' / 'drama3-4bit-v2'
REFERENCE_TEXT = 'Xin chào! Hôm nay chúng ta kiểm tra chất lượng giọng nói tiếng Việt.'


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog='python3 -m viettts speak --engine drama3', description=__doc__)
    text = p.add_mutually_exclusive_group()
    text.add_argument('--text', default='Xin chào các anh, em là AI nè')
    text.add_argument('--input', type=Path, help='Markdown or plain-text story')
    text.add_argument('--tagged-input', type=Path, help='One tagged chunk per nonempty line; tags preserved')
    p.add_argument('--ref-audio', type=Path)
    p.add_argument('--ref-text', help='Exact transcript of the reference audio')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--resume-dir', type=Path, help='Resume a failed run with the same model, seed and reference')
    p.add_argument('--download-only', action='store_true')
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    if bool(args.ref_audio) != bool(args.ref_text):
        p.error('--ref-audio and --ref-text must be supplied together')
    return args


def story_chunks(text):
    from viettts.text import split_chunks

    return split_chunks(text, max_chars=120)


def spoken_text(text):
    return re.sub(r'\s+', ' ', re.sub(r'\[[^\[\]]*\]|<[^>]+>', '', text)).strip()


def tagged_chunks(text):
    chunks = [line.strip() for line in text.splitlines() if line.strip()]
    for line in chunks:
        if len(line.encode('utf-8')) > 300:
            raise ValueError('Tagged lines must fit 300 UTF-8 bytes; shorten the line with balanced tags.')
        if not spoken_text(line):
            raise ValueError('Every tagged line needs spoken text.')
        stack = []
        for tag in re.findall(r'<[^>]+>', line):
            if tag == '<whisper>':
                stack.append('whisper')
            elif tag == '</whisper>' and stack:
                stack.pop()
            else:
                raise ValueError(f'Unsupported or unmatched scoped tag: {tag}')
        if stack or line.count('[') != line.count(']'):
            raise ValueError('Unbalanced tags in line.')
    return chunks


def check_frame_limit(frames, limit):
    if frames >= limit:
        raise RuntimeError(f'Generation reached its {limit}-frame cap without ending.')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('This runner requires Apple Silicon. NVIDIA uses a different Drama-3 INT4 runtime.')
    if not args.worker:
        command, env = uv_command('drama3', '-m', 'viettts', 'speak', '--engine', 'drama3', *argv, '--worker')
        raise SystemExit(subprocess.run(command, env=env).returncode)

    os.environ.setdefault('HF_HOME', str(ROOT / '.cache' / 'huggingface'))
    from huggingface_hub import snapshot_download

    download_start = time.perf_counter()
    model_path = snapshot_download(REPO, revision=REVISION, local_dir=MODEL, max_workers=4)
    download_seconds = time.perf_counter() - download_start
    if args.download_only:
        print(f'Model ready: {model_path}')
        return

    from viettts.text import plain_text

    if args.tagged_input:
        text = args.tagged_input.read_text(encoding='utf-8-sig').strip()
        chunks = tagged_chunks(text)
    else:
        text = plain_text(args.input.read_text(encoding='utf-8-sig')) if args.input else args.text.strip()
        chunks = story_chunks(text)
    if not text:
        raise SystemExit('No narration text.')
    reference = args.ref_audio or ROOT / 'references' / 'maichi-synthetic.wav'
    if not reference.is_file():
        raise SystemExit(f'Missing reference: {reference}. Supply --ref-audio and --ref-text.')
    ref_text = args.ref_text or REFERENCE_TEXT
    import mlx.core as mx
    import numpy as np
    import soundfile as sf
    from mlx_audio.tts.utils import load_model

    output = args.resume_dir or ROOT / 'outputs' / ('drama3-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    if args.resume_dir and (output / 'summary.json').exists():
        raise SystemExit('This run already completed; choose a new output.')
    output.mkdir(parents=True, exist_ok=bool(args.resume_dir))
    (output / 'text.txt').write_text(text, encoding='utf-8')
    started = time.perf_counter()
    mx.random.seed(args.seed)
    model = load_model(model_path)
    mx.synchronize()
    load_seconds = time.perf_counter() - started
    print(f'Model loaded in {load_seconds:.2f}s; starting synthesis.', flush=True)
    rows = []
    if args.resume_dir:
        events = [json.loads(line) for line in (output / 'performance.jsonl').read_text().splitlines()]
        rows = [r for r in events if 'synthesis_seconds' in r]
        if [r['text'] for r in rows] != chunks[: len(rows)]:
            raise ValueError('Completed text differs; cannot resume safely.')
        print(f'Resuming after {len(rows)} completed chunks.', flush=True)
    completed = len(rows)
    (output / 'chunks.json').write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding='utf-8')
    merged_path = output / 'drama3.wav'
    with (
        sf.SoundFile(str(merged_path), mode='w', samplerate=model.sample_rate, channels=1, subtype='PCM_16') as merged,
        (output / 'performance.jsonl').open('a' if args.resume_dir else 'w') as log,
    ):
        for chunk, chunk_text in enumerate(chunks, 1):
            if chunk <= completed:
                old, rate = sf.read(output / f'{chunk:04d}.wav', dtype='float32')
                if rate != model.sample_rate or not old.size:
                    raise RuntimeError('Invalid saved chunk.')
                if chunk > 1:
                    merged.write(np.zeros(round(rate * 0.15), dtype=np.float32))
                merged.write(old)
                continue
            previous = time.perf_counter()
            limit = min(600, max(256 if args.tagged_input else 128, len(spoken_text(chunk_text)) * 3))
            for attempt in range(1, 4):
                mx.random.seed(args.seed + chunk - 1 + (attempt - 1) * 1000)
                parts = []
                frames = 0
                try:
                    for result in model.generate(
                        text=chunk_text,
                        ref_audio=str(reference),
                        ref_text=ref_text,
                        temperature=0.7,
                        top_p=0.7,
                        top_k=30,
                        max_tokens=limit,
                        stream=False,
                    ):
                        mx.eval(result.audio)
                        check_frame_limit(result.token_count, limit)
                        frames += result.token_count
                        samples = np.asarray(result.audio, dtype=np.float32).reshape(-1)
                        if samples.size == 0 or not np.isfinite(samples).all() or not np.any(samples):
                            raise RuntimeError('Empty, invalid or silent audio chunk.')
                        if result.sample_rate != model.sample_rate:
                            raise RuntimeError('Unexpected sample rate change.')
                        parts.append(samples)
                    if not parts:
                        raise RuntimeError('No audio generated.')
                    break
                except RuntimeError as error:
                    log.write(json.dumps(dict(chunk=chunk, attempt=attempt, rejected=str(error))) + '\n')
                    log.flush()
                    print(f'Chunk {chunk}/{len(chunks)} attempt {attempt} rejected: {error}', flush=True)
                    if attempt == 3:
                        raise
            samples = np.concatenate(parts)
            elapsed = time.perf_counter() - previous
            sf.write(str(output / f'{chunk:04d}.wav'), samples, model.sample_rate, subtype='PCM_16')
            if chunk > 1:
                merged.write(np.zeros(round(model.sample_rate * 0.15), dtype=np.float32))
            merged.write(samples)
            duration = len(samples) / model.sample_rate
            row = dict(
                chunk=chunk,
                text=chunk_text,
                attempts=attempt,
                frames=frames,
                frame_limit=limit,
                synthesis_seconds=elapsed,
                audio_seconds=duration,
                rtf=elapsed / duration,
            )
            rows.append(row)
            log.write(json.dumps(row, ensure_ascii=False) + '\n')
            log.flush()
            print(
                f'Chunk {chunk}/{len(chunks)}: {elapsed:.2f}s synthesis, {duration:.2f}s audio, attempts={attempt}',
                flush=True,
            )
    if not rows:
        raise RuntimeError('Model produced no audio.')
    synthesis = sum(r['synthesis_seconds'] for r in rows)
    duration = sum(r['audio_seconds'] for r in rows)
    report = dict(
        model=REPO,
        revision=REVISION,
        quantization='experts INT4; dense/audio tower INT8',
        backend='MLX Metal',
        seed=args.seed,
        reference_audio=str(reference.resolve()),
        reference_text=ref_text,
        text=text,
        chunks=len(rows),
        sample_rate=model.sample_rate,
        download_check_seconds=download_seconds,
        load_seconds=load_seconds,
        synthesis_seconds=synthesis,
        average_synthesis_seconds_per_chunk=statistics.mean(r['synthesis_seconds'] for r in rows),
        audio_seconds=duration,
        merged_audio_seconds=sf.info(str(merged_path)).duration,
        chunking=(
            'tagged lines preserved'
            if args.tagged_input
            else 'sentence-first, <=120 characters, independent reference conditioning'
        ),
        pause_ms=150,
        rtf=synthesis / duration,
        peak_mlx_memory_gb=mx.get_peak_memory() / 1e9,
        wall_seconds_this_invocation=time.perf_counter() - started,
        resumed_completed_chunks=completed,
        output=str(merged_path),
        runs=rows,
    )
    (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(
        json.dumps({k: v for k, v in report.items() if k not in ('text', 'runs')}, ensure_ascii=False, indent=2),
        flush=True,
    )


if __name__ == '__main__':
    main()
