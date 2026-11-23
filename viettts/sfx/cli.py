"""python3 -m viettts sfx: the sound-effect library and mixing it under built audiobooks and voice dramas."""

import argparse
import json
import re
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

from viettts.audiobook.assembly import Assembler
from viettts.audiobook.cast import load_cast
from viettts.audiobook.enhance import check_enhance
from viettts.audiobook.layout import plan_layout, plan_units
from viettts.audiobook.m4b import M4bEncoder, ffmeta_escape, write_listing
from viettts.audiobook.script import read_script
from viettts.paths import uv_command

from . import cues as cue_file
from . import library as lib


def cmd_list(args):
    library = lib.load()
    rows = [s for s in library['sounds'] if not args.category or s['category'] == args.category]
    for s in rows:
        have, want, weak = len(lib.sound_files(s)), lib.takes_wanted(s), lib.weak_takes(s)
        state = f'{have}/{want} takes' + (f', weak {",".join(map(str, weak))}' if weak else '')
        print(f'{s["category"]:<8} {s["id"]:<26} {s["kind"]:<7} {s["seconds"]:>4g}s  {state:<18}  {s["prompt"]}')
    missing = sum(lib.missing_takes(s) for s in rows)
    print(
        f'{len(rows)} sounds; {missing} takes not rendered'
        + ('; run: python3 -m viettts sfx generate' if missing else '')
    )


def cmd_add(args):
    entry = dict(
        id=args.id, category=args.category, kind=args.kind, seconds=args.seconds, prompt=args.prompt, takes=args.takes
    )
    try:
        lib.add(entry)
    except ValueError as e:
        raise SystemExit(f'Not added: {e}') from None
    print(f'Added {args.category}/{args.id}; render it with: python3 -m viettts sfx generate {args.id}')


def cmd_takes(args):
    try:
        sound = lib.set_takes(args.id, args.takes)
    except ValueError as e:
        raise SystemExit(str(e)) from None
    missing = lib.missing_takes(sound)
    print(
        f'{args.id}: {args.takes} takes'
        + (f'; render the {missing} new ones with: python3 -m viettts sfx generate {args.id}' if missing else '')
    )


def cmd_remove(args):
    for sound_id in args.ids:
        try:
            sound = lib.remove(sound_id)
        except ValueError as e:
            raise SystemExit(str(e)) from None
        print(f'Removed {sound["category"]}/{sound_id} ({len(sound.get("rendered", []))} takes)')


def cmd_generate(args):
    extra = [*args.ids, *(['--force'] if args.force else []), '--seeds', args.seeds]
    if args.steps is not None:
        extra += ['--steps', str(args.steps)]
    command, env = uv_command('sfx', '-m', 'viettts.sfx.generate', *extra)
    sys.exit(subprocess.run(command, env=env).returncode)


def book_timeline(script_path: Path, cast: Path | None, unknown: str) -> dict[str, Any]:
    """Replay the build's assembly (every chunk must be cached) and check it against chapters/NN.wav, so the
    line times are those of the book as built. Writes and returns timeline.json."""
    out = script_path.parent
    script = read_script(script_path.read_text(encoding='utf-8'))
    if cast is None and (out / 'cast.json').is_file():
        cast = out / 'cast.json'
    _, voices = load_cast(cast)
    enhanced, problems = check_enhance(script_path, script)
    if problems:
        raise SystemExit('enhance.txt has problems; run: python3 -m viettts audiobook check ' + str(script_path))
    layout, jobs = plan_layout(out, plan_units(script, voices, unknown, enhanced=enhanced), voices)
    if jobs:
        missing = sum(len(j) for j in jobs.values())
        raise SystemExit(f'{missing} chunks are not built yet; build the book (same cast) before adding sound effects.')
    assembly = Assembler(out).run(layout)
    rate = assembly.rate
    for n, (title, frames) in enumerate(assembly.chapters, 1):
        path = out / 'chapters' / f'{n:02d}.wav'
        if not path.is_file():
            raise SystemExit(f'{path} is missing; rebuild the book (a full build, not --chapters/--only).')
        with wave.open(str(path), 'rb') as w:
            if (w.getnframes(), w.getframerate()) != (frames, rate):
                raise SystemExit(
                    f'chapters/{n:02d}.wav ({w.getnframes()} frames) does not match the script ({frames}): '
                    'the script, enhance.txt or cast changed since the build. Rebuild, then add sound effects.'
                )
    return assembly.write_timeline(out, script, enhanced)


def clock(seconds: float) -> str:
    return f'{int(seconds // 60)}:{seconds % 60:04.1f}'


def cmd_timeline(args):
    script_path = args.script.resolve()
    timeline = book_timeline(script_path, args.cast, args.unknown)
    print(
        f'{script_path.parent / "timeline.json"}: {len(timeline["lines"])} lines in '
        f'{len(timeline["chapters"])} chapters, matching chapters/*.wav exactly'
    )
    if not args.show:
        return
    picked = set(args.chapter or [c['chapter'] for c in timeline['chapters']])
    for chapter in timeline['chapters']:
        if chapter['chapter'] not in picked:
            continue
        print(f'\n## {chapter["chapter"]}: {chapter["title"]}  ({clock(chapter["duration_ms"] / 1000)})')
        for item in (i for i in timeline['lines'] if i['chapter'] == chapter['chapter']):
            seconds = (item['end_ms'] - item['start_ms']) / 1000
            print(
                f'L{item["line"]:<5} {clock(item["start_ms"] / 1000):>7} {seconds:4.1f}s  {item.get("tagged") or item["text"]}'
            )
            if item['pause_ms'] >= 600:  # a paragraph (scene) break or the chapter's end
                print()


def check_cues(script_path: Path, timeline: dict[str, Any]) -> list[dict[str, Any]]:
    path = cue_file.cues_path(script_path)
    if not path.is_file():
        raise SystemExit(f'{path} does not exist; write the cues first (see the sfx skill).')
    cues, problems = cue_file.read_cues(path.read_text(encoding='utf-8'))
    placed, more = cue_file.place(cues, timeline, lib.load())
    problems = sorted(problems + more)
    for row, message in problems:
        print(f'  sfx.txt:{row}: {message}')
    if problems:
        raise SystemExit(f'{len(problems)} problems in sfx.txt; nothing mixed.')
    return placed


def cmd_check(args):
    script_path = args.script.resolve()
    placed = check_cues(script_path, book_timeline(script_path, args.cast, args.unknown))
    by_sound: dict[str, int] = {}
    for p in placed:
        by_sound[p['sound']] = by_sound.get(p['sound'], 0) + 1
    seconds = sum(p['seconds'] for p in placed)
    clear = [p for p in placed if p['insert']]
    print(
        f'{len(placed)} cues, 0 problems; {seconds / 60:.1f} min of sound effects; '
        + (f'{len(clear)} clear cues add {sum(p["insert"][1] for p in clear):.1f} s; ' if clear else '')
        + ', '.join(f'{k} x{v}' for k, v in sorted(by_sound.items(), key=lambda kv: -kv[1]))
    )


def voice_only_m4b(out: Path) -> Path:
    summary = out / 'summary.json'
    if summary.is_file():
        built = out / Path(json.loads(summary.read_text(encoding='utf-8'))['output']).name
        if built.is_file():
            return built
    books = [p for p in out.glob('*.m4b') if not re.search(r'\((thử|SFX)', p.stem)]
    if not books:
        raise SystemExit(f'No voice-only .m4b in {out}; build the book first.')
    return max(books, key=lambda p: p.stat().st_mtime)


def cmd_mix(args):
    script_path = args.script.resolve()
    out = script_path.parent
    timeline = book_timeline(script_path, args.cast, args.unknown)
    placed = check_cues(script_path, timeline)
    voice_m4b = voice_only_m4b(out)
    numbers = [c['chapter'] for c in timeline['chapters']]
    picked = args.only or numbers
    mixed_dir = out / 'chapters-sfx'
    mixed_dir.mkdir(exist_ok=True)
    plan = dict(
        chapters=[
            dict(
                voice=str(out / 'chapters' / f'{n:02d}.wav'),
                out=str(mixed_dir / f'{n:02d}.wav'),
                inserts=[p['insert'] for p in placed if p['chapter'] == n and p['insert']],
                cues=[p for p in placed if p['chapter'] == n],
            )
            for n in picked
        ]
    )
    plan_path = out / 'sfx-plan.json'
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Mixing {len(placed)} cues into {len(picked)} chapters ...', flush=True)
    command, env = uv_command('sfx', '-m', 'viettts.sfx.mix', str(plan_path))
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f'mixing failed:\n{result.stderr[-3000:]}')
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    for row in rows:
        name = Path(row['out']).name
        note = f', {row["limited_samples"]} samples softly limited' if row['limited_samples'] else ''
        print(f'  {name}: {row["cues"]} cues, peak {row["peak_dbfs"]} dBFS{note}')
    encoder = M4bEncoder(args.bitrate)
    listing = out / 'chapters-sfx.list'
    if args.only:
        previews = []
        for n in picked:
            preview = out / f'{voice_m4b.stem} (SFX chương {n}).m4a'
            encoder.encode(write_listing(listing, [mixed_dir / f'{n:02d}.wav']), preview)
            previews.append(preview)
        listing.unlink()
        print('Preview: ' + ', '.join(str(p) for p in previews))
        return
    m4b = out / f'{voice_m4b.stem} (SFX).m4b'
    ffmeta = write_sfx_timing(out, timeline, placed, [row['frames'] / row['rate'] for row in rows])
    chapters = write_listing(listing, [mixed_dir / f'{n:02d}.wav' for n in numbers])
    encoder.encode(chapters, m4b, ffmeta, voice_m4b)
    listing.unlink()
    print(f'Done: {m4b} ({m4b.stat().st_size / 1e6:.1f} MB); the voice-only book is unchanged: {voice_m4b.name}')


def write_sfx_timing(out: Path, timeline, placed, seconds: list[float]) -> Path:
    """chapters-sfx.ffmeta (the book's tags, chapter marks of the longer SFX chapters) and timeline-sfx.json
    (every line where it is heard in the SFX book). Without clear cues both match the voice-only book."""
    header = (out / 'chapters.ffmeta').read_text(encoding='utf-8').split('[CHAPTER]')[0].rstrip('\n')
    marks, position = [], 0.0
    for chapter, length in zip(timeline['chapters'], seconds):
        marks.append((chapter['title'], round(position * 1000), round((position + length) * 1000)))
        position += length
    chapters = ''.join(
        f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={a}\nEND={b}\ntitle={ffmeta_escape(t)}\n' for t, a, b in marks
    )
    path = out / 'chapters-sfx.ffmeta'
    path.write_text(f'{header}\n{chapters}', encoding='utf-8')
    starts = {chapter['chapter']: start for chapter, (_, start, _) in zip(timeline['chapters'], marks)}

    def moved(item, key):
        return round(cue_file.shift_time(placed, item['chapter'], item[key] / 1000) * 1000)

    shifted = dict(
        timeline,
        chapters=[
            dict(c, start_ms=starts[c['chapter']], duration_ms=round(length * 1000))
            for c, length in zip(timeline['chapters'], seconds)
        ],
        lines=[
            dict(
                i,
                start_ms=moved(i, 'start_ms'),
                end_ms=moved(i, 'end_ms'),
                book_start_ms=starts[i['chapter']] + moved(i, 'start_ms'),
            )
            for i in timeline['lines']
        ],
    )
    (out / 'timeline-sfx.json').write_text(json.dumps(shifted, ensure_ascii=False, indent=1), encoding='utf-8')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python3 -m viettts sfx', description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('list', help='The library: id, kind, length, render state, prompt')
    s.add_argument('--category')
    s.set_defaults(func=cmd_list)
    s = sub.add_parser('add', help='List a new sound (render it with generate)')
    s.add_argument('id', help='lowercase-with-dashes, e.g. zipper-hoodie')
    s.add_argument('--category', required=True, help='bed, undress, body, props, scene, ... (or a new one)')
    s.add_argument('--kind', required=True, choices=lib.KINDS)
    s.add_argument('--seconds', type=float, required=True, help='2 for one-shots, 3 or 5 for loops')
    s.add_argument('--prompt', required=True, help='English description ending in "no voice, no music."')
    s.add_argument('--takes', type=int, default=1, help='Variants (seeds) to render, for a sound heard often (3-4)')
    s.set_defaults(func=cmd_add)
    s = sub.add_parser('remove', help='Drop sounds from the library, with their files')
    s.add_argument('ids', nargs='+')
    s.set_defaults(func=cmd_remove)
    s = sub.add_parser('takes', help='Set how many variants a sound has (generate renders new ones)')
    s.add_argument('id')
    s.add_argument('takes', type=int)
    s.set_defaults(func=cmd_takes)
    s = sub.add_parser('generate', help='Render listed sounds with MOSS-SoundEffect v2 (engines/sfx)')
    s.add_argument('ids', nargs='*', help='Default: every sound missing takes')
    s.add_argument('--force', action='store_true', help='Render every take of the given ids again')
    s.add_argument('--seeds', default='0,1,2', help='Seeds to try in order, e.g. 3,4,5 for a fresh take')
    s.add_argument('--steps', type=int, help='Denoising steps (default: viettts.sfx.generate.STEPS)')
    s.set_defaults(func=cmd_generate)
    for name, func, text in (
        ('timeline', cmd_timeline, 'Write timeline.json (line start/end times) for a built book'),
        ('check', cmd_check, 'Validate sfx.txt against the timeline and the library'),
        ('mix', cmd_mix, 'Mix sfx.txt under the voice: chapters-sfx/ and "<Title> (SFX).m4b"'),
    ):
        s = sub.add_parser(name, help=text)
        s.add_argument('script', type=Path, help='script.txt of the built book')
        s.add_argument('--cast', type=Path, help='The cast the book was built with (default: cast.json beside it)')
        s.add_argument('--unknown', choices=['fail', 'narrator'], default='fail', help='As given to build')
        if name == 'timeline':
            s.add_argument('--show', action='store_true', help='Print every line with its time and tags')
            s.add_argument('--chapter', type=int, action='append', help='With --show: only this chapter')
        if name == 'mix':
            s.add_argument('--only', type=int, action='append', help='Mix just chapter N into a preview .m4a')
            s.add_argument('--bitrate', default='64k')
        s.set_defaults(func=func)
    args = parser.parse_args(argv)
    args.func(args)
