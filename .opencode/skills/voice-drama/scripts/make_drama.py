#!/usr/bin/env python3
"""Voice drama scripts: one or two women talking to the listener, no narrator.

  scan SOURCE                   chapters and duplicate chapters
  init SOURCE --out DIR ...     write DIR/directed.txt (every line, plain, the source's scene breaks)
                                and DIR/drama.json
  make DIR                      directed.txt -> script.txt + enhance.txt + cast.json

directed.txt is the agent's working copy: "## Chương N" headings, one spoken line per line, a blank line
for a scene break (600 ms instead of 300 ms), Drama-3 tags added in place, and "{Name} " in front of a
line spoken by a second woman. `make` checks every line's words against the source and refuses to write
anything if one differs, so tags can never change the text.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from viettts.audiobook.build import spoken, untagged  # noqa: E402

HEADING = re.compile(r'^(?:#{1,3}\s*(.+)|(\d{1,3})|(?:chương|chapter|track|part|phần)\s*(\d{1,3})\b.*)$', re.I)
IMAGES = ('.jpg', '.jpeg', '.png', '.webp')


def parse_source(path, drop=()):
    """(doc_title, [(title, [line, ...], {index of a line that starts a new scene})]) from a source with
    optional "# Title", and "##", bare-number, or "Chương N" chapter lines. Lines of a scene are consecutive;
    a blank line starts a new scene. A chapter with a blank line after every line has no scene breaks."""
    text = Path(path).read_text(encoding='utf-8-sig')
    doc_title, chapters, blank = '', [], False
    for line in (raw.strip() for raw in text.splitlines()):
        if not line:
            blank = True
            continue
        if line.startswith('# ') and not line.startswith('## ') and not chapters and not doc_title:
            first = line[2:].strip()
            if not re.fullmatch(r'(?:chương|chapter|track|part|phần)?\s*\d{1,3}', first, re.I):
                doc_title = first
                blank = False
                continue
        m = HEADING.match(line)
        if m and (line.startswith('#') or len(line) < 120):
            chapters.append([m[1] or f'Chương {m[2] or m[3]}', [], set()])
        else:
            if not chapters:
                chapters.append(['Chương 1', [], set()])
            lines, breaks = chapters[-1][1], chapters[-1][2]
            if blank and lines:
                breaks.add(len(lines))
            lines.append(line)
        blank = False
    for chapter in chapters:
        if len(chapter[1]) > 2 and len(chapter[2]) == len(chapter[1]) - 1:
            chapter[2] = set()
    kept = [c for i, c in enumerate(chapters, 1) if i not in set(drop)]
    for n, chapter in enumerate(kept, 1):  # renumber after a dropped chapter
        chapter[0] = re.sub(r'^Chương \d+\b', f'Chương {n}', chapter[0])
    return doc_title, [tuple(c) for c in kept]


def read_scenes(path, drop=()):
    return parse_source(path, drop)[1]


def read_source(path, drop=()):
    """[(title, [line, ...])]"""
    return [(t, ls) for t, ls, _ in read_scenes(path, drop)]


def cmd_scan(args):
    doc_title, chapters = parse_source(args.source)
    if doc_title:
        print(f'Title: {doc_title}')
    seen = {}
    for n, (title, lines, breaks) in enumerate(chapters, 1):
        chars = sum(len(line) for line in lines)
        dup = seen.get(tuple(lines))
        print(f'{n:2d}. {title}: {len(lines)} lines, {len(breaks) + 1} scenes, {chars} chars'
              + (f'  <- identical to chapter {dup}' if dup else ''))
        seen.setdefault(tuple(lines), n)
    total = sum(len(line) for _, ls, _ in chapters for line in ls)
    print(f'{len(chapters)} chapters, {sum(len(ls) for _, ls, _ in chapters)} lines, {total} chars '
          f'(Drama-3: ~{max(1, round(total / 100000 * 40))} min plus retries)')


def cmd_init(args):
    out = args.out.resolve()
    directed = out / 'directed.txt'
    if directed.exists() and not args.force:
        raise SystemExit(f'{directed} exists (it holds your tags). Use --force to overwrite.')
    source = args.source.resolve()
    doc_title, chapters = parse_source(source, args.drop)
    cover = args.cover or next((p for p in sorted(source.parent.iterdir()) if p.suffix.lower() in IMAGES), None)
    settings = dict(
        source=str(source),
        title=args.title or doc_title or source.parent.name,
        author=args.author or '',
        cover=str(cover.resolve()) if cover else '',
        drop=args.drop,
        voices=dict(v.split('=', 1) if '=' in v else ('narrator', v) for v in args.voice),
    )
    out.mkdir(parents=True, exist_ok=True)
    parts = []
    for title, lines, breaks in chapters:
        parts.append(f'## {title}\n' + ''.join(('\n' if i in breaks else '') + f'{line}\n'
                                               for i, line in enumerate(lines)))
    directed.write_text('\n'.join(parts), encoding='utf-8')
    (out / 'drama.json').write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    scenes = sum(len(b) + 1 for _, _, b in chapters)
    print(f'{directed}: {len(chapters)} chapters, {sum(len(ls) for _, ls, _ in chapters)} lines, {scenes} scenes '
          f'(from the source\'s blank lines). Review the breaks, add tags, then: make {out}')


def cmd_make(args):
    out = args.dir.resolve()
    settings = json.loads((out / 'drama.json').read_text(encoding='utf-8'))
    voices = settings['voices']
    if 'narrator' not in voices:
        raise SystemExit('drama.json: voices needs the main voice ("narrator").')
    chapters = read_source(settings['source'], settings['drop'])
    directed, current = [], None
    for raw in (out / 'directed.txt').read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if line.startswith('## '):
            current = []
            directed.append((line[3:].strip(), current))
        elif line.startswith('#'):
            continue
        elif not line:
            if current and current[-1] is not None:
                current.append(None)
        elif current is None:
            raise SystemExit('directed.txt: text before the first "## " heading')
        else:
            current.append(line)
    if len(directed) != len(chapters):
        raise SystemExit(f'directed.txt has {len(directed)} chapters, the source {len(chapters)}')
    cover = settings.get('cover')
    if cover and Path(cover).suffix.lower() == '.webp':  # keep a JPEG copy: every player shows it
        jpg = out / 'cover.jpg'
        if not jpg.exists():
            import subprocess

            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', cover, str(jpg)], check=True)
        cover = str(jpg)
    lines_out = [f'@title {settings["title"]}', f'@source {settings["source"]}']
    if settings.get('author'):
        lines_out.append(f'@author {settings["author"]}')
    if cover:
        lines_out.append(f'@cover {cover}')
    lines_out.append('@speaker ta male narrator')
    others = sorted(k for k in voices if k not in ('narrator', 'mc', 'male', 'female'))
    lines_out += [f'@speaker {name} female' for name in others]
    enhance, errors, tagged_count = [], [], 0
    for (title, items), (_, source_lines) in zip(directed, chapters):
        n_directed = sum(item is not None for item in items)
        if n_directed != len(source_lines):
            errors.append(f'{title}: {n_directed} lines in directed.txt, {len(source_lines)} in the source')
        lines_out += ['', f'## {title}', '']
        k = 0
        for item in items:
            if item is None:
                if lines_out[-1] != '':
                    lines_out.append('')
                continue
            speaker = 'narrator'
            m = re.match(r'^\{([^{}]+)\}\s*(.*)$', item)
            if m:
                speaker, item = m[1].strip(), m[2]
                if speaker not in voices:
                    errors.append(f'{title} line {k + 1}: speaker "{speaker}" has no voice in drama.json')
            plain = source_lines[k] if k < len(source_lines) else ''
            if untagged(spoken(item)) != untagged(spoken(plain)):
                errors.append(f'{title} line {k + 1}: words differ\n    directed: {untagged(spoken(item))}'
                              f'\n    source:   {untagged(spoken(plain))}')
            lines_out.append(f'[{speaker}] {plain}')
            if item != plain:
                enhance.append((len(lines_out), item))
                tagged_count += 1
            k += 1
        while lines_out[-1] == '':
            lines_out.pop()
    if errors:
        print('\n'.join(errors[:30]))
        raise SystemExit(f'{len(errors)} problems; nothing written.')
    for name in ('script.txt', 'enhance.txt'):
        if (out / name).exists():
            shutil.copy(out / name, out / f'{name}.bak')
    (out / 'script.txt').write_text('\n'.join(lines_out) + '\n', encoding='utf-8')
    (out / 'enhance.txt').write_text(''.join(f'L{n}: {t}\n' for n, t in enhance), encoding='utf-8')
    cast = {'narrator': voices['narrator'], 'mc': voices['narrator'], 'male': 'Hải Đăng',
            'female': voices.get('female', voices['narrator'])}
    cast.update({name: voices[name] for name in others})
    (out / 'cast.json').write_text(json.dumps({'voices': cast}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    total = sum(len(ls) for _, ls in chapters)
    print(f'{out / "script.txt"}: {len(chapters)} chapters, {total} lines, {tagged_count} with tags; '
          f'cast: {", ".join(f"{k}={v}" for k, v in cast.items())}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(required=True)
    s = sub.add_parser('scan')
    s.add_argument('source', type=Path)
    s.set_defaults(func=cmd_scan)
    s = sub.add_parser('init')
    s.add_argument('source', type=Path)
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--voice', action='append', required=True,
                   help='main voice id, then Name=id for a second woman (repeatable)')
    s.add_argument('--title')
    s.add_argument('--author')
    s.add_argument('--cover', type=Path)
    s.add_argument('--drop', type=int, action='append', default=[], help='chapter number to leave out')
    s.add_argument('--force', action='store_true')
    s.set_defaults(func=cmd_init)
    s = sub.add_parser('make')
    s.add_argument('dir', type=Path)
    s.set_defaults(func=cmd_make)
    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
