"""Render library sounds with MOSS-SoundEffect v2 (runs in engines/sfx: python -m viettts.sfx.generate).

Called as the MOSS demo does (50 steps, CFG 4.0, sigma_shift 5.0): the pipeline denoises its full 30 s
window and crops. Never shrink that window (max_inference_seconds): the model is trained on 30 s and a
smaller one gives loud, broken audio. A take that is near silence (common) is retried with the next seed;
the best take is resampled to 44.1 kHz, levelled to LEVEL_DBFS (measured against its own peak) and faded.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('TORCHDYNAMO_DISABLE', '1')  # torch.compile targets Triton/CUDA graphs
os.environ.setdefault('PYTORCH_ENABLE_MPS_FALLBACK', '1')

from viettts.paths import ROOT  # noqa: E402
from viettts.sfx import library as lib  # noqa: E402

REPO = 'OpenMOSS-Team/MOSS-SoundEffect-v2.0'
REVISION = 'e35df4d82fbe87fcd5d14e5d100e349c0c3c076d'
MODEL = ROOT / 'models' / 'moss-soundeffect-v2'
STEPS = 50  # the demo default; 100 (the model card) sounds no better and takes twice as long
CFG = 4.0
SEEDS = (0, 1, 2)
MIN_PEAK_DBFS = -30.0  # quieter than this is the model's near-silence, not a sound
MIN_ACTIVE = {'loop': 0.3, 'oneshot': 0.05}  # share of 20 ms frames within RANGE_DB of the take's peak
RANGE_DB = 40.0
PEAK_DBFS = -1.0


def patch_for_mps():
    """MPS has no float64: compute the timestep embedding on the CPU and keep RoPE tables as complex64
    (rope_apply casts them to fp32 anyway), instead of the upstream float64/complex128 tensors."""
    import torch
    from moss_soundeffect_v2.diffsynth.models import wan_audio_dit, wan_video_dit
    from moss_soundeffect_v2.diffsynth.pipelines import wan_audio

    def sinusoidal_embedding_1d(dim, position):
        pos = position.detach().float().cpu().double()
        sinusoid = torch.outer(pos, torch.pow(10000, -torch.arange(dim // 2, dtype=torch.float64).div(dim // 2)))
        x = torch.cat([torch.cos(sinusoid), torch.sin(sinusoid)], dim=1)
        return x.to(device=position.device, dtype=position.dtype)

    original = wan_audio_dit.precompute_freqs_cis

    def precompute_freqs_cis(*args, **kwargs):
        return original(*args, **kwargs).to(torch.complex64)

    for module in (wan_audio, wan_audio_dit, wan_video_dit):
        if hasattr(module, 'sinusoidal_embedding_1d'):
            module.sinusoidal_embedding_1d = sinusoidal_embedding_1d
    wan_audio_dit.precompute_freqs_cis = precompute_freqs_cis


def load_pipeline():
    import torch
    from huggingface_hub import snapshot_download
    from moss_soundeffect_v2 import MossSoundEffectPipeline

    if not (MODEL / 'model_index.json').is_file():
        snapshot_download(REPO, revision=REVISION, local_dir=MODEL, max_workers=4)
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    if device == 'mps':
        patch_for_mps()
    pipe = MossSoundEffectPipeline.from_pretrained(str(MODEL), torch_dtype=torch.bfloat16, device=device)
    release_memory()  # the loader's CPU copies of the DiT weights, and the GPU blocks loading left cached
    return pipe


def release_memory():
    """Free what Python no longer references and hand PyTorch's cached GPU blocks back to Metal.

    Only between takes, never inside the denoising loop: within a take the steps reuse cached buffers."""
    import gc

    import torch

    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()


def frame_rms(x, rate):
    import numpy as np

    hop = rate // 50
    frames = len(x) // hop
    return np.sqrt((x[: frames * hop].reshape(frames, hop) ** 2).mean(axis=1))


def measure(x, rate):
    """(peak dBFS, share of 20 ms frames within RANGE_DB of the peak). Relative, because a real sound is
    often a short event in silence (a kiss, a knock), and the model's level varies a lot between takes."""
    import numpy as np

    peak = float(np.abs(x).max()) if len(x) else 0.0
    rms = frame_rms(x, rate)
    if not peak or not len(rms):
        return -120.0, 0.0
    return 20 * float(np.log10(peak)), float((rms > peak * 10 ** (-RANGE_DB / 20)).mean())


def finish(x, rate, kind):
    """Resample to the library rate, level the audible part to LEVEL_DBFS (peak at most PEAK_DBFS), fade."""
    import numpy as np
    import torch
    import torchaudio.functional as F

    x = F.resample(torch.from_numpy(x).unsqueeze(0), rate, lib.SAMPLE_RATE)[0].numpy()
    env = frame_rms(x, lib.SAMPLE_RATE)
    loud = env[env > float(np.abs(x).max()) * 10 ** (-RANGE_DB / 20)]
    rms = float(np.sqrt((loud**2).mean())) if len(loud) else 1e-9
    x = x * (10 ** (lib.LEVEL_DBFS / 20) / rms)
    peak = float(np.abs(x).max())
    if peak > 10 ** (PEAK_DBFS / 20):
        x = x * (10 ** (PEAK_DBFS / 20) / peak)
    fade_in = int(lib.SAMPLE_RATE * (0.01 if kind == 'loop' else 0.003))
    fade_out = int(lib.SAMPLE_RATE * (0.12 if kind == 'loop' else 0.05))
    x[:fade_in] *= np.linspace(0, 1, fade_in)
    x[-fade_out:] *= np.linspace(1, 0, fade_out)
    return x.astype(np.float32)


def rank(kind, passed, peak_db, active):
    """Sort key for tries (higher is better): a passing try first, then a loop's steadiest try (sound in
    most of it, so its bed has no gaps) or a one-shot's clearest (loudest hit)."""
    return (passed, active, peak_db) if kind == 'loop' else (passed, peak_db, active)


def render(pipe, sound, seconds, seeds, steps):
    """The first take that passes the gate, else the best by rank(): (passed, seed, peak_db, active,
    samples), and the seeds it tried."""
    best, best_key, tried = None, None, []
    for seed in seeds:
        tried.append(seed)
        audio = pipe(
            prompt=sound['prompt'],
            seconds=seconds,
            num_inference_steps=steps,
            cfg_scale=CFG,
            seed=seed,
        )
        x = audio[0, 0].detach().float().cpu().numpy()
        peak_db, active = measure(x, pipe.sample_rate)
        passed = peak_db >= MIN_PEAK_DBFS and active >= MIN_ACTIVE[sound['kind']]
        key = rank(sound['kind'], passed, peak_db, active)
        if best_key is None or key > best_key:
            best, best_key = (passed, seed, peak_db, active, x), key
        if passed:
            break
    assert best is not None
    return best, tried


def next_seeds(after, count):
    return list(range(after + 1, after + 1 + count))


def main(argv=None):
    import soundfile as sf

    parser = argparse.ArgumentParser(prog='python -m viettts.sfx.generate')
    parser.add_argument('ids', nargs='*', help='Sounds to render (default: every sound missing takes)')
    parser.add_argument('--force', action='store_true', help='Render every take of the given sounds again')
    parser.add_argument('--seeds', default=','.join(map(str, SEEDS)), help='Seeds to try first, in order')
    parser.add_argument('--steps', type=int, default=STEPS)
    parser.add_argument(
        '--takes', type=int, help='Render only the first N takes of each sound (1: fast, for a sound heard once)'
    )
    parser.add_argument('--root', type=Path, default=lib.LIBRARY_DIR)
    args = parser.parse_args(argv)
    if args.takes is not None and args.takes < 1:
        parser.error('--takes must be at least 1')
    library = lib.load(args.root)
    known = lib.sounds(library)
    unknown = [i for i in args.ids if i not in known]
    if unknown:
        raise SystemExit(f'Not in the library: {", ".join(unknown)} (add them with: viettts sfx add)')
    if args.force and args.ids:
        for sound_id in args.ids:
            sound = known[sound_id]
            if args.takes is None:
                for path in lib.sound_files(sound, args.root):
                    path.unlink()
                sound['rendered'] = []
            else:  # only the takes this run renders again; later takes stay
                for take in sound.get('rendered', [])[: args.takes]:
                    (args.root / take['file']).unlink(missing_ok=True)
        lib.save(library, args.root)
    todo = [known[i] for i in args.ids] if args.ids else library['sounds']
    todo = [s for s in todo if lib.missing_takes(s, args.root, args.takes)]
    if not todo:
        print('Nothing to render; every sound has its takes.')
        return
    first_seeds = [int(s) for s in args.seeds.split(',')]
    total = sum(lib.missing_takes(s, args.root, args.takes) for s in todo)
    pipe = load_pipeline()
    done = 0
    for sound in todo:
        rendered = list(sound.get('rendered', []))[: lib.takes_wanted(sound)]
        # A new take never reuses a seed any take was rendered with, so every take differs.
        last = max([t['seed'] for t in rendered], default=-1)
        for n in lib.stale_takes(sound, args.root, args.takes):
            started = time.perf_counter()
            seconds = lib.take_seconds(sound, n)
            seeds = first_seeds if last < 0 else next_seeds(last, len(first_seeds))
            (passed, seed, peak_db, active, x), tried = render(pipe, sound, seconds, seeds, args.steps)
            last = max(last, *tried)
            rel = lib.take_file(sound, n)
            (args.root / sound['category']).mkdir(parents=True, exist_ok=True)
            sf.write(args.root / rel, finish(x, pipe.sample_rate, sound['kind']), lib.SAMPLE_RATE, subtype='PCM_16')
            take = dict(
                file=rel,
                seconds=seconds,
                seed=seed,
                raw_peak_db=round(peak_db, 1),
                active=round(active, 2),
                passed_gate=passed,
            )
            if n <= len(rendered):
                rendered[n - 1] = take
            else:
                rendered.append(take)
            library = lib.load(args.root)  # re-read: keep entries added meanwhile
            entry = lib.sounds(library)[sound['id']]
            entry.update(rendered=rendered, steps=args.steps, model=f'{REPO}@{REVISION[:7]}')
            lib.save(library, args.root)
            done += 1
            del x
            release_memory()
            flag = '' if passed else f'  <- failed the gate on seeds {tried}; best kept, listen to it'
            print(
                f'[{done}/{total}] {rel} (take {n}/{lib.takes_wanted(sound)}, {seconds:g}s) seed={seed} steps={args.steps} peak={peak_db:.1f}dB '
                f'active={active:.2f} {time.perf_counter() - started:.0f}s{flag}',
                flush=True,
            )
    print(json.dumps(dict(rendered=done)))


if __name__ == '__main__':
    sys.exit(main())
