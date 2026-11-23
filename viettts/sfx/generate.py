"""Render library sounds with MOSS-SoundEffect v2 (runs in engines/sfx: python -m viettts.sfx.generate).

The pipeline always denoises max_inference_seconds (30 s) of latents and crops; a window just over the
sound's length is about 4x faster. Each take is gated on level and activity (a near-silent take is common)
and retried with the next seed; the best take is resampled to 44.1 kHz, levelled to LEVEL_DBFS and faded.
"""

import argparse
import json
import math
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
STEPS = 100
CFG = 4.0
SEEDS = (0, 1, 2)
MIN_RMS = 0.004
MIN_ACTIVE = {'loop': 0.6, 'oneshot': 0.15}  # share of 20 ms frames above -45 dBFS
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
    return MossSoundEffectPipeline.from_pretrained(str(MODEL), torch_dtype=torch.bfloat16, device=device)


def active_fraction(x, rate, floor_db=-45.0):
    import numpy as np

    hop = rate // 50
    frames = len(x) // hop
    if not frames:
        return 0.0
    rms = np.sqrt((x[: frames * hop].reshape(frames, hop) ** 2).mean(axis=1))
    return float((20 * np.log10(rms + 1e-9) > floor_db).mean())


def finish(x, rate, kind):
    """Resample to the library rate, level the audible part to LEVEL_DBFS (peak at most PEAK_DBFS), fade."""
    import numpy as np
    import torch
    import torchaudio.functional as F

    x = F.resample(torch.from_numpy(x).unsqueeze(0), rate, lib.SAMPLE_RATE)[0].numpy()
    audible = x[np.abs(x) > 10 ** (-45 / 20)]
    rms = float(np.sqrt((audible**2).mean())) if len(audible) else 1e-9
    x = x * (10 ** (lib.LEVEL_DBFS / 20) / rms)
    peak = float(np.abs(x).max())
    if peak > 10 ** (PEAK_DBFS / 20):
        x = x * (10 ** (PEAK_DBFS / 20) / peak)
    fade_in = int(lib.SAMPLE_RATE * (0.01 if kind == 'loop' else 0.003))
    fade_out = int(lib.SAMPLE_RATE * (0.12 if kind == 'loop' else 0.05))
    x[:fade_in] *= np.linspace(0, 1, fade_in)
    x[-fade_out:] *= np.linspace(1, 0, fade_out)
    return x.astype(np.float32)


def render(pipe, sound, seconds, seeds, steps):
    """The first take that passes the gate, else the best one: (passed, seed, rms, active, samples), and the
    seeds it tried."""
    import numpy as np

    best, tried = None, []
    for seed in seeds:
        tried.append(seed)
        audio = pipe(
            prompt=sound['prompt'],
            seconds=seconds,
            num_inference_steps=steps,
            cfg_scale=CFG,
            seed=seed,
            max_inference_seconds=math.ceil(seconds) + 2,
        )
        x = audio[0, 0].detach().float().cpu().numpy()
        rms, active = float(np.sqrt((x**2).mean())), active_fraction(x, pipe.sample_rate)
        passed = rms >= MIN_RMS and active >= MIN_ACTIVE[sound['kind']]
        if best is None or (passed, active * rms) > (best[0], best[3] * best[2]):
            best = (passed, seed, rms, active, x)
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
    parser.add_argument('--root', type=Path, default=lib.LIBRARY_DIR)
    args = parser.parse_args(argv)
    library = lib.load(args.root)
    known = lib.sounds(library)
    unknown = [i for i in args.ids if i not in known]
    if unknown:
        raise SystemExit(f'Not in the library: {", ".join(unknown)} (add them with: viettts sfx add)')
    if args.force and args.ids:
        for sound_id in args.ids:
            for path in lib.sound_files(known[sound_id], args.root):
                path.unlink()
            known[sound_id]['rendered'] = []
        lib.save(library, args.root)
    todo = [known[i] for i in args.ids] if args.ids else library['sounds']
    todo = [s for s in todo if lib.missing_takes(s, args.root)]
    if not todo:
        print('Nothing to render; every sound has all its takes.')
        return
    first_seeds = [int(s) for s in args.seeds.split(',')]
    total = sum(lib.missing_takes(s, args.root) for s in todo)
    pipe = load_pipeline()
    done = 0
    for sound in todo:
        rendered = list(sound.get('rendered', []))[: lib.takes_wanted(sound)]
        # A new take never reuses a seed any take was rendered with, so every take differs.
        last = max([t['seed'] for t in rendered], default=-1)
        for n in lib.stale_takes(sound, args.root):
            started = time.perf_counter()
            seconds = lib.take_seconds(sound, n)
            seeds = first_seeds if last < 0 else next_seeds(last, len(first_seeds))
            (passed, seed, rms, active, x), tried = render(pipe, sound, seconds, seeds, args.steps)
            last = max(last, *tried)
            rel = lib.take_file(sound, n)
            (args.root / sound['category']).mkdir(parents=True, exist_ok=True)
            sf.write(args.root / rel, finish(x, pipe.sample_rate, sound['kind']), lib.SAMPLE_RATE, subtype='PCM_16')
            take = dict(
                file=rel, seconds=seconds, seed=seed, raw_rms=round(rms, 4), active=round(active, 2), passed_gate=passed
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
            flag = '' if passed else f'  <- failed the gate on seeds {tried}; best kept, listen to it'
            print(
                f'[{done}/{total}] {rel} (take {n}/{lib.takes_wanted(sound)}, {seconds:g}s) seed={seed} rms={rms:.3f} '
                f'active={active:.2f} {time.perf_counter() - started:.0f}s{flag}',
                flush=True,
            )
    print(json.dumps(dict(rendered=done)))


if __name__ == '__main__':
    sys.exit(main())
