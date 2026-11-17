#!/usr/bin/env python3
"""Optional clean-up of a voice's audio: remove background music and/or room echo (reverb).

Drama-3 clones everything in a reference: music under the voice comes out as hiss or warble, and a room's
echo comes out as echo. Both are removed with audio-separator (UVR / Roformer models), which needs torch and
onnxruntime wheels the system Python may not have, so it lives in its own Python 3.12 venv (created with uv
on first use) under ~/.cache/viettts/dereverb, together with the downloaded models.

Run from the repository root:

  # the references made by `voice cut` (music first, then echo; either step alone is fine)
  python3 .opencode/skills/voice-onboarding/scripts/clean_refs.py refs <id> --music --reverb [--preview]

  # a stretch of a source with music playing throughout, before `voice candidates`
  python3 .opencode/skills/voice-onboarding/scripts/clean_refs.py source <file> --id <Name> --from 1:51:00 --to 1:55:00

refs: the originals are kept in outputs/voice-onboarding/<id>/orig-refs/, and every run starts from them,
so rerunning with other steps or models never stacks processing. A new `voice cut` resets everything.
--preview only writes the cleaned clips to outputs/voice-onboarding/<id>/cleaned/ for listening.

source: writes outputs/voice-onboarding/<id>/source-vocals.wav (just that range, music removed). Run
`voice candidates` on that file without --from/--to; candidate times are then relative to --from.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from viettts.voices import onboarding as ob  # noqa: E402

CACHE = Path.home() / '.cache' / 'viettts' / 'dereverb'
VENV = CACHE / '.venv'
SEPARATOR = VENV / 'bin' / 'audio-separator'
MODELS = CACHE / 'models'
PACKAGES = ['audio-separator[cpu]', 'audioread', 'torch', 'onnxruntime']
# Music removal keeps the vocals stem. Alternative: model_bs_roformer_ep_317_sdr_12.9755.ckpt (BS-Roformer).
MUSIC_MODEL = 'vocals_mel_band_roformer.ckpt'
# Echo removal keeps the dry stem. Gentler alternative if it sounds robotic or "underwater":
#   dereverb_mel_band_roformer_less_aggressive_anvuew_sdr_18.8050.ckpt
REVERB_MODEL = 'dereverb_mel_band_roformer_anvuew_sdr_19.1729.ckpt'
KEEP = dict(music=('(vocals)',), reverb=('(noreverb)', '(dry)'))
FADES = 'afade=t=in:d=0.02,areverse,afade=t=in:d=0.03,areverse'


def ensure_venv():
    if SEPARATOR.is_file():
        return
    if not shutil.which('uv'):
        raise SystemExit('Need uv (brew install uv) to create the audio-separator venv.')
    print(f'Creating the audio-separator venv in {VENV} (one-time, a few minutes) ...', flush=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    subprocess.run(['uv', 'venv', '-q', '-p', '3.12', str(VENV)], check=True)
    subprocess.run(['uv', 'pip', 'install', '-q', '-p', str(VENV), *PACKAGES], check=True)


def separate(wav, model, step, out, extra_filter=None):
    """Run one model on a clip and write the kept stem to `out` as 48 kHz mono 16-bit."""
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                str(SEPARATOR), str(wav), '-m', model, '--output_dir', tmp,
                '--model_file_dir', str(MODELS), '--output_format', 'WAV',
            ],
            capture_output=True,
            text=True,
        )
        keep = [p for p in Path(tmp).glob('*.wav') if any(k in p.name.lower().replace(' ', '') for k in KEEP[step])]
        if result.returncode or len(keep) != 1:
            raise SystemExit(f'audio-separator ({model}) failed on {wav.name}:\n{(result.stderr or result.stdout)[-800:]}')
        af = ['-af', extra_filter] if extra_filter else []
        ob.ffmpeg('-i', str(keep[0]), '-ac', '1', '-ar', '48000', *af, '-c:a', 'pcm_s16le', str(out))
    return out


def cmd_refs(args):
    steps = [s for s in ('music', 'reverb') if getattr(args, s)]
    if not steps:
        raise SystemExit('Choose --music, --reverb or both.')
    models = dict(music=args.music_model, reverb=args.reverb_model)
    vid = ob.slugify(args.id)
    meta = ob.load(vid)
    refs = meta.get('references', [])
    if not refs:
        raise SystemExit(f'{vid}: no references yet; run voice cut first.')
    work = ob.WORK / vid
    originals = work / 'orig-refs'
    if not any(r.get('cleaned') or r.get('dereverb') for r in refs):  # fresh from cut: back them up
        shutil.rmtree(originals, ignore_errors=True)
        originals.mkdir(parents=True)
        for r in refs:
            shutil.copy2(ob.voice_dir(vid) / r['file'], originals / r['file'])
    ensure_venv()
    out_dir = work / 'cleaned'
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f'Cleaning {len(refs)} reference(s) of {vid}: {", ".join(f"{s} ({models[s]})" for s in steps)} ...', flush=True)
    for r in refs:
        current = originals / r['file']
        with tempfile.TemporaryDirectory() as tmp:
            for i, step in enumerate(steps):
                last = i == len(steps) - 1
                out = out_dir / r['file'] if last else Path(tmp) / f'{step}.wav'
                # Short fades on the final clip so the stem's edges don't click.
                current = separate(current, models[step], step, out, FADES if last else None)
        if args.preview:
            print(f'  {current.relative_to(ROOT)}')
            continue
        target = ob.voice_dir(vid) / r['file']
        shutil.copy2(current, target)
        before = r.get('lufs')
        gain, _, after = ob.level(target)
        r.pop('dereverb', None)
        r.update(ob.measure(target), cleaned=[models[s] for s in steps], gain_db=round(r.get('gain_db', 0) + gain, 2))
        print(
            f'  {r["file"]}  speech {r["speech_pct"]}%  pause ≤{r["longest_pause"]}s  '
            f'{before} -> {after} LUFS ({gain:+.1f} dB)'
        )
    if args.preview:
        print(f'Listen and compare with {originals.relative_to(ROOT)}/; rerun without --preview to apply.')
        return
    meta['metrics'] = dict(
        duration=round(sum(r['duration'] for r in refs), 2), longest_pause=max(r['longest_pause'] for r in refs)
    )
    meta['samples'] = []  # cloned from the uncleaned clips; regenerate
    ob.save(meta)
    print(
        f'Done. Transcripts stay valid. Originals: {originals.relative_to(ROOT)}/\n'
        f'Next: python3 -m viettts voice samples {vid}'
    )


def cmd_source(args):
    media = Path(args.media).expanduser().resolve()
    if not media.is_file():
        raise SystemExit(f'No such file: {media}')
    vid = ob.slugify(args.id)
    work = ob.WORK / vid
    work.mkdir(parents=True, exist_ok=True)
    ensure_venv()
    start, end = ob.parse_time(args.start_at), ob.parse_time(args.end_at)
    trim = (['-ss', str(start)] if start else []) + (['-to', str(end)] if end else [])
    out = work / 'source-vocals.wav'
    with tempfile.TemporaryDirectory() as tmp:
        extract = Path(tmp) / 'source.wav'
        ob.ffmpeg(*trim, '-i', str(media), '-ac', '2', '-ar', '44100', str(extract))
        print(f'Removing music from {ob.seconds_of(extract) / 60:.1f} min with {args.music_model} ...', flush=True)
        separate(extract, args.music_model, 'music', out)
    offset = f' Candidate times are relative to {args.start_at}.' if start else ''
    print(
        f'Wrote {out.relative_to(ROOT)}.{offset}\n'
        f'Next: python3 -m viettts voice candidates "{out.relative_to(ROOT)}" --id "{args.id}"'
    )


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('refs', help="Clean a voice's reference clips in place (originals kept)")
    s.add_argument('id')
    s.add_argument('--music', action='store_true', help='Remove background music (runs first)')
    s.add_argument('--reverb', action='store_true', help='Remove room echo / reverb')
    s.add_argument('--music-model', default=MUSIC_MODEL)
    s.add_argument('--reverb-model', default=REVERB_MODEL)
    s.add_argument('--preview', action='store_true', help='Only write cleaned clips for listening')
    s.set_defaults(func=cmd_refs)
    s = sub.add_parser('source', help='Remove music from a stretch of the source, before voice candidates')
    s.add_argument('media')
    s.add_argument('--id', required=True)
    s.add_argument('--from', dest='start_at')
    s.add_argument('--to', dest='end_at')
    s.add_argument('--music-model', default=MUSIC_MODEL)
    s.set_defaults(func=cmd_source)
    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
