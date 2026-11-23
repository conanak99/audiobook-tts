"""audiobook verify: check a finished .m4b against its script."""

import json
import re
import subprocess

from .script import read_script


def cmd_verify(args):
    script_path = args.script.resolve()
    script = read_script(script_path.read_text(encoding='utf-8'))
    m4bs = [args.m4b] if args.m4b else sorted(script_path.parent.glob('*.m4b'), key=lambda p: p.stat().st_mtime)
    if not m4bs:
        raise SystemExit('No .m4b next to the script.')
    m4b = m4bs[-1]
    probe = json.loads(
        subprocess.run(
            [
                'ffprobe',
                '-v',
                'error',
                '-print_format',
                'json',
                '-show_format',
                '-show_streams',
                '-show_chapters',
                str(m4b),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    titles = [c.get('tags', {}).get('title') for c in probe.get('chapters', [])]
    expected = [t for t, _ in script.chapters]
    if args.partial:  # --chapters N or --only SPEC: the chapters in script order
        remaining = iter(expected)
        expected = titles if titles and all(t in remaining for t in titles) else expected[: len(titles)]
    audio = [s for s in probe['streams'] if s['codec_type'] == 'audio']
    tags = {k.lower(): v for k, v in probe['format'].get('tags', {}).items()}
    checks = [
        ('audio is AAC', bool(audio) and audio[0]['codec_name'] == 'aac'),
        (f'{len(titles)} chapters match the script ({len(expected)})', titles == expected),
        (
            'chapters are contiguous and increasing',
            all(
                float(a['end_time']) <= float(b['start_time']) + 0.01
                for a, b in zip(probe['chapters'], probe['chapters'][1:])
            ),
        ),
        ('title tag set', bool(tags.get('title'))),
        ('marked as audiobook (media_type=2)', tags.get('media_type') == '2'),
        (
            'cover attached',
            any(s.get('disposition', {}).get('attached_pic') for s in probe['streams']) or not script.meta.get('cover'),
        ),
        ('duration > 0', float(probe['format'].get('duration', 0)) > 0),
    ]
    detect = subprocess.run(
        [
            'ffmpeg',
            '-hide_banner',
            '-nostats',
            '-i',
            str(m4b),
            '-map',
            '0:a',
            '-af',
            'silencedetect=noise=-50dB:d=2.5',
            '-f',
            'null',
            '-',
        ],
        capture_output=True,
        text=True,
        errors='replace',
    ).stderr
    gaps = re.findall(r'silence_end: ([\d.]+) \| silence_duration: ([\d.]+)', detect)
    checks.append(
        (
            f'no silence over 2.5 s ({len(gaps)} found'
            + (': ' + ', '.join(f'{float(e) / 60:.1f}min' for e, _ in gaps[:5]) if gaps else '')
            + (')' if not gaps else '; run repair, then build again)'),
            not gaps,
        )
    )
    print(f'{m4b.name}: {float(probe["format"]["duration"]) / 60:.1f} min, {int(probe["format"]["size"]) / 1e6:.1f} MB')
    for name, ok in checks:
        print(f'  {"OK  " if ok else "FAIL"} {name}')
    if not all(ok for _, ok in checks):
        raise SystemExit(1)
