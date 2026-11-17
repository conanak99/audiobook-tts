"""Cached audiobook synthesis jobs, run inside the selected engine environment."""

import json
import os
import time

from viettts.paths import ROOT


def cmd_worker(args):
    # The build helpers are stdlib-only; SDKs stay inside this worker.
    from viettts.audiobook.build import MAX_SILENCE_S, clock, frame_budget, level, longest_silence, squeeze

    os.environ['HF_HUB_DISABLE_SYMLINKS'] = '1'
    for name, suffix in [
        ('HF_HOME', 'huggingface'),
        ('XDG_CACHE_HOME', ''),
        ('NUMBA_CACHE_DIR', 'numba'),
        ('MPLCONFIGDIR', 'matplotlib'),
    ]:
        os.environ.setdefault(name, str(ROOT / '.cache' / suffix))
    import numpy as np
    import soundfile as sf

    jobs = [json.loads(line) for line in args.jobs.read_text(encoding='utf-8').splitlines() if line.strip()]
    out = args.out
    started = time.perf_counter()
    if args.engine == 'vieneu':
        from vieneu import Vieneu

        tts = Vieneu(backend='onnx', device='cpu', precision='fp32', threads=args.threads)

        def synth(job):
            tmp = out / f'{job["id"]}.tmp.wav'
            tts.save(tts.infer(job['text'], voice=job['voice']), str(tmp))
            samples, rate = sf.read(tmp, dtype='float32', always_2d=True)
            tmp.unlink()
            return samples[:, 0], rate
    else:
        import mlx.core as mx
        from huggingface_hub import snapshot_download
        from mlx_audio.tts.utils import load_model

        from .drama3 import MODEL, REPO, REVISION, check_frame_limit

        model = load_model(snapshot_download(REPO, revision=REVISION, local_dir=MODEL, max_workers=4))

        def synth(job):
            best = None
            # A tagged chunk whose every take is rejected falls back to its plain words.
            for fallback, text in enumerate([job['text']] + ([job['plain']] if job.get('plain') else [])):
                if fallback:
                    job['fell_back'] = True
                    print(f'[drama3]   every tagged take was rejected; trying without tags: {text[:60]}', flush=True)
                limit = frame_budget(text)
                for attempt in range(4):
                    mx.random.seed(int(job['id'][:8], 16) + attempt * 1000)
                    try:
                        parts = []
                        for result in model.generate(
                            text=text,
                            ref_audio=job['voice']['ref_audio'],
                            ref_text=job['voice']['ref_text'],
                            temperature=0.7,
                            top_p=0.7,
                            top_k=30,
                            max_tokens=limit,
                            stream=False,
                        ):
                            mx.eval(result.audio)
                            check_frame_limit(result.token_count, limit)
                            parts.append(np.asarray(result.audio, dtype=np.float32).reshape(-1))
                        if not parts:
                            raise RuntimeError('no audio')
                        audio = np.concatenate(parts)
                        gap = longest_silence(audio, model.sample_rate, np)
                        if best is None or gap < best[0]:
                            best = (gap, audio)
                        if gap <= MAX_SILENCE_S:
                            return audio, model.sample_rate
                        print(f'[drama3]   attempt {attempt + 1} has {gap:.1f}s of silence; retrying', flush=True)
                    except RuntimeError as error:
                        print(f'[drama3]   attempt {attempt + 1} rejected ({error}); retrying', flush=True)
                if best is not None:
                    return best[1], model.sample_rate
            raise RuntimeError(f'Drama-3 failed 4 times on: {job["text"][:60]}')

    total_chars = sum(len(job['text']) for job in jobs)
    print(
        f'[{args.engine}] model loaded in {time.perf_counter() - started:.1f}s; '
        f'{len(jobs)} chunks, {total_chars} characters',
        flush=True,
    )
    synth_start, done_chars, audio_seconds = time.perf_counter(), 0, 0.0
    for i, job in enumerate(jobs, 1):
        tick = time.perf_counter()
        try:
            samples, rate = synth(job)
        except RuntimeError as error:
            if not args.skip_failed:
                raise
            print(f'[{args.engine}] {i}/{len(jobs)} FAILED {job["id"]}: {error}', flush=True)
            continue
        if not samples.size or not np.isfinite(samples).all() or not np.any(samples):
            raise RuntimeError(f'Silent or invalid audio for: {job["text"][:60]}')
        samples = level(squeeze(samples, rate, np), np)
        tmp = out / f'{job["id"]}.part.wav'
        sf.write(str(tmp), samples, rate, subtype='PCM_16')
        tmp.rename(out / f'{job["id"]}.wav')
        if job.get('fell_back'):
            (out / f'{job["id"]}.plain').write_text(job['text'] + '\n', encoding='utf-8')
        done_chars += len(job['text'])
        audio_seconds += len(samples) / rate
        elapsed = time.perf_counter() - synth_start
        eta = elapsed / done_chars * (total_chars - done_chars)
        print(
            f'[{args.engine}] {i}/{len(jobs)} ({100 * done_chars / total_chars:5.1f}%) '
            f'chunk {time.perf_counter() - tick:5.2f}s · elapsed {clock(elapsed)} · ETA {clock(eta)} · '
            f'audio {audio_seconds / 60:.1f} min',
            flush=True,
        )
    print(f'[{args.engine}] finished {len(jobs)} chunks in {clock(time.perf_counter() - synth_start)}', flush=True)
