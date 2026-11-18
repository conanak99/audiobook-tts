"""Parse stories and review attributed scripts without loading a TTS engine."""

from datetime import datetime

from viettts.paths import ROOT
from viettts.text import slugify

from .script import UNKNOWN, apply_review, build_book, check_script, export_review, read_script, write_script

OUTPUTS = ROOT / 'outputs' / 'audiobooks'


def first_cover(story, images):
    for image in images:
        path = (story.parent / image).resolve()
        if path.is_file() and path.suffix.lower() in ('.jpg', '.jpeg', '.png'):
            return path
    return None


def cmd_parse(args):
    story = args.story.expanduser().resolve()
    book = build_book(
        story.read_text(encoding='utf-8-sig'), narrator=args.narrator, narrator_gender=args.narrator_gender
    )
    cover = None if args.no_cover else first_cover(story, book.images)
    out = (args.output or OUTPUTS / slugify(book.title or story.parent.name)).resolve()
    out.mkdir(parents=True, exist_ok=True)
    script_path = out / 'script.txt'
    if script_path.exists() and not args.force:
        raise SystemExit(f'{script_path} exists (it may hold your edits). Use --force to overwrite.')
    text = write_script(book, cover)
    text = text.replace('\n@speaker', f'\n@source {story}\n@speaker', 1)
    script_path.write_text(text, encoding='utf-8')
    review, _, items = export_review(text)
    (out / 'review.md').write_text(review, encoding='utf-8')
    quotes = [s for c in book.chapters for p in c.paragraphs for s in p.quotes]
    unknown = sum(1 for q in quotes if q.speaker == UNKNOWN)
    print(f'Script: {script_path}')
    print(
        f'  {len(book.chapters)} chapters, {len(quotes)} quotes, narrator "{book.narrator}", cover: {cover or "none"}'
    )
    print('  speakers: ' + ', '.join(f'{k} ({v})' for k, v in book.speakers.items()))
    print(f'  {unknown} unknown lines, {items} open review items (full file: {out / "review.md"})')
    print(f'Next: python3 -m viettts audiobook review {script_path} --batch 40   # then apply-review, check, build')


def cmd_export_review(args):
    review, _, total = export_review(args.script.read_text(encoding='utf-8'))
    target = args.output or args.script.with_name('review.md')
    target.write_text(review, encoding='utf-8')
    print(f'{total} open review items -> {target}')


def cmd_review(args):
    review, written, total = export_review(args.script.read_text(encoding='utf-8'), limit=args.batch)
    if not total:
        print('No open review items.')
        return
    print(review, end='')
    print(
        f'\n# {written} of {total} open items shown. Answer with lines like "L123: speaker", '
        f'"L124: new: Name | female", "SPEAKER Name: male" in a file, then run apply-review.'
    )


def cmd_apply_review(args):
    script_text = args.script.read_text(encoding='utf-8')
    updated, changes = apply_review(script_text, args.review.read_text(encoding='utf-8'))
    backup = args.script.with_name(f'script.{datetime.now():%Y%m%d-%H%M%S-%f}.bak.txt')
    backup.write_text(script_text, encoding='utf-8')
    args.script.write_text(updated, encoding='utf-8')
    _, _, left = export_review(updated, limit=0)
    print(f'Applied {changes} answers (backup: {backup.name}); {left} review items still open.')


def cmd_check(args):
    from .build import check_enhance, enhance_path, validate_cast, voice_label

    script_path = args.script.resolve()
    text = script_path.read_text(encoding='utf-8')
    script = read_script(text)
    findings = check_script(text)
    enhanced, enhance_findings = check_enhance(script_path, script)
    findings = sorted(findings + enhance_findings)
    cast_path = getattr(args, 'cast', None)
    if cast_path is not None:
        cast_path = cast_path.expanduser().resolve()
    else:
        adjacent = script_path.with_name('cast.json')
        cast_path = adjacent if adjacent.is_file() else None
    cast_findings = []
    if cast_path is not None:
        preset, voices, cast_findings = validate_cast(script, cast_path, script_path.name)
        if cast_findings:
            print(f'{cast_path.name}: {len(cast_findings)} cast error(s)')
        else:
            labels = ', '.join(f'{key}={voice_label(*voice)}' for key, voice in voices.items())
            print(f'{cast_path.name}: valid {preset} cast; {labels}')
    _, _, open_items = export_review(text, limit=0)
    unknown = text.count('\n[?] ')
    for number, message in findings:
        print(f'{"L" + str(number) if number else "--"}: {message}')
    for message in cast_findings:
        print(f'--: cast: {message}')
    print(
        f'{len(findings)} findings, {open_items} open review items, {unknown} [?] lines'
        + (
            f', {len(enhanced)} enhance.txt entries ({len(enhance_findings)} with problems).'
            if enhance_path(args.script.resolve()).is_file()
            else '.'
        )
    )
    if unknown or any(m.endswith('unknown gender') for _, m in findings):
        print('Not buildable yet: answer the [?] lines and unknown genders (or build with --unknown narrator).')
        raise SystemExit(1)
    if enhance_findings:
        print('Not buildable yet: fix the enhance.txt lines above.')
        raise SystemExit(1)
    if cast_findings:
        print('Not buildable yet: fix the cast errors above.')
        raise SystemExit(1)


def cmd_status(args):
    script_path = args.script.resolve()
    out = script_path.parent
    text = script_path.read_text(encoding='utf-8')
    script = read_script(text)
    lines = [line for _, paras in script.chapters for p in paras for line in p]
    _, _, open_items = export_review(text, limit=0)
    print(f'Script: {script_path}')
    print(
        f'  {len(script.chapters)} chapters, {len(lines)} lines, {open_items} open review items, '
        f'{sum(line.label == UNKNOWN for line in lines)} [?] lines'
    )
    for cache in sorted((out / 'cache').glob('*')) if (out / 'cache').is_dir() else []:
        print(f'  cache {cache.name}: {len(list(cache.glob("*.wav")))} chunks')
    log = out / 'build.log'
    if log.is_file():
        tail = [line for line in log.read_text(encoding='utf-8').splitlines() if line.strip()][-args.lines :]
        print('  build.log:')
        for line in tail:
            print(f'    {line}')
    for m4b in sorted(out.glob('*.m4b')):
        print(
            f'  output: {m4b.name} ({m4b.stat().st_size / 1e6:.1f} MB, {datetime.fromtimestamp(m4b.stat().st_mtime):%Y-%m-%d %H:%M})'
        )
