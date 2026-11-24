"""python3 -m viettts subs: Japanese or Chinese subtitles (WebVTT) from voice-drama audio, for the translate skill."""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from viettts.paths import ROOT, uv_command
from viettts.text import slugify

from . import cues as plan

LANGUAGES = {'ja': 'Japanese (anime-whisper)', 'zh': "Chinese (MOSS's text)"}
AUDIO = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.mp4', '.m4b'}


def natural_key(path: Path):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', path.name)]


def find_tracks(inputs: list[Path]) -> list[Path]:
    tracks: list[Path] = []
    for path in inputs:
        if path.is_dir():
            tracks += sorted((p for p in path.iterdir() if p.suffix.lower() in AUDIO), key=natural_key)
        elif path.is_file():
            tracks.append(path)
        else:
            raise SystemExit(f'not found: {path}')
    if not tracks:
        raise SystemExit('no audio files found')
    return tracks


def default_out(inputs: list[Path]) -> Path:
    first = inputs[0]
    name = first.name if first.is_dir() else first.stem
    if re.search(r'[A-Za-z]{2}', name):
        slug = slugify(name)
    else:  # slugify turns a Japanese-only name into digits or 'audiobook': keep the name itself
        slug = re.sub(r'[\s/\\:]+', '-', name).strip('-.') or 'subtitles'
    return ROOT / 'outputs' / 'subtitles' / slug


def to_wav(src: Path, dst: Path) -> None:
    command = ['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-i', str(src), '-vn', '-ac', '1', '-ar', '16000']
    result = subprocess.run([*command, str(dst)], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f'ffmpeg failed on {src}:\n{result.stderr[-2000:]}')


def cmd_transcribe(args):
    tracks = find_tracks(args.inputs)
    out = args.out or default_out(args.inputs)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        request = {'speakers': args.speakers, 'language': args.lang, 'tracks': []}
        for i, track in enumerate(tracks):
            wav = Path(tmp) / f'{i:03}.wav'
            to_wav(track, wav)
            request['tracks'].append({'wav': str(wav), 'out': str(Path(tmp) / f'{i:03}.json')})
        (Path(tmp) / 'request.json').write_text(json.dumps(request), encoding='utf-8')
        print(f'transcribing {len(tracks)} track(s), {"2 speakers" if args.speakers == 2 else "1 speaker"} ...', flush=True)
        command, env = uv_command('drama3', '-m', 'viettts.subs.worker', str(Path(tmp) / 'request.json'))
        worker = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, text=True)
        assert worker.stdout is not None
        done, languages = 0, set()
        for line in worker.stdout:
            row = json.loads(line)
            languages.add(row['language'])
            print(
                f'  [{done + 1}/{len(tracks)}] {tracks[done].name}: {row["cues"]} cues, '
                f'{LANGUAGES[row["language"]]}, in {row["seconds"]}s',
                flush=True,
            )
            done += 1
        if worker.wait():
            raise SystemExit(f'transcription failed (exit {worker.returncode})')
        if len(languages) > 1:
            print('WARNING: the tracks were heard as different languages; rerun with --lang ja or --lang zh')
        results = [json.loads(Path(t['out']).read_text(encoding='utf-8')) for t in request['tracks']]

    for track, cues in zip(tracks, results):
        (out / f'{track.stem}.vtt').write_text(plan.vtt(cues), encoding='utf-8')
    source = out / 'source.md'
    source.write_text(
        plan.source_md([(plan.chapter_title(t.stem), c) for t, c in zip(tracks, results)]), encoding='utf-8'
    )
    print(f'wrote {source} ({len(tracks)} chapter(s), one per file) and one .vtt per file')


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='python3 -m viettts subs', description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser(
        'transcribe',
        help='Write one .vtt per track and a combined source.md',
        description='Transcribe Japanese or Chinese voice-drama tracks (files or folders, in natural name order) '
        'in the drama3 environment. MOSS-Transcribe-Diarize finds the lines; Japanese lines are re-transcribed by '
        'anime-whisper, Chinese ones keep MOSS text. --speakers 2 labels each cue <v S1>/<v S2>.',
    )
    p.add_argument('inputs', nargs='+', type=Path, help='audio files and/or folders of tracks')
    p.add_argument('--speakers', type=int, choices=[1, 2], default=1, help='voices in the drama (default: 1)')
    p.add_argument(
        '--lang', choices=['auto', 'ja', 'zh'], default='auto', help='spoken language (default: read from each track)'
    )
    p.add_argument('--out', type=Path, help='output folder (default: outputs/subtitles/<name>)')
    p.set_defaults(func=cmd_transcribe)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main(sys.argv[1:])
