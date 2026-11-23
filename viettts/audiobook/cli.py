"""python3 -m viettts audiobook: story -> reviewed script -> multi-voice M4B audiobook with chapters."""

import argparse
from pathlib import Path

from .audio import MAX_SILENCE_S
from .build import cmd_build
from .maintenance import cmd_make_ref, cmd_repair, cmd_scan
from .verify import cmd_verify


def main(argv=None):
    from viettts.engines.worker import cmd_worker

    from .review import (
        cmd_apply_review,
        cmd_check,
        cmd_export_review,
        cmd_parse,
        cmd_review,
        cmd_status,
    )

    p = argparse.ArgumentParser(prog='python3 -m viettts audiobook', description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('parse', help='Story Markdown -> script.txt + review.md')
    s.add_argument('story', type=Path, help='Full path to story_vn.md')
    s.add_argument('--output', type=Path, help='Output directory (default outputs/audiobooks/<title>)')
    s.add_argument('--narrator', choices=['ta', 'tôi'], help='Narrator pronoun (default: detected)')
    s.add_argument('--narrator-gender', choices=['male', 'female'], default='male')
    s.add_argument('--no-cover', action='store_true')
    s.add_argument('--force', action='store_true', help='Overwrite an existing script.txt')
    s.set_defaults(func=cmd_parse)
    s = sub.add_parser('export-review', help='Write review.md for the lines still marked "?"')
    s.add_argument('script', type=Path)
    s.add_argument('--output', type=Path)
    s.set_defaults(func=cmd_export_review)
    s = sub.add_parser('review', help='Print the next batch of open review items (agent loop)')
    s.add_argument('script', type=Path)
    s.add_argument('--batch', type=int, default=40, help='About this many items per batch')
    s.set_defaults(func=cmd_review)
    s = sub.add_parser('check', help='Heuristic warnings on confident lines; exit 1 if not buildable')
    s.add_argument('script', type=Path)
    s.add_argument('--cast', type=Path, help='Cast JSON to validate (default: cast.json beside the script, if present)')
    s.set_defaults(func=cmd_check)
    s = sub.add_parser('status', help='Script, cache and build progress at a glance')
    s.add_argument('script', type=Path)
    s.add_argument('--lines', type=int, default=4, help='build.log lines to show')
    s.set_defaults(func=cmd_status)
    s = sub.add_parser('verify', help='Check the newest .m4b against the script')
    s.add_argument('script', type=Path)
    s.add_argument('--m4b', type=Path)
    s.add_argument('--partial', action='store_true', help='The build used --chapters N or --only SPEC')
    s.set_defaults(func=cmd_verify)
    s = sub.add_parser('apply-review', help='Merge review answers (review.md or "L123: speaker" lines)')
    s.add_argument('script', type=Path)
    s.add_argument('review', type=Path)
    s.set_defaults(func=cmd_apply_review)
    s = sub.add_parser('build', help='script.txt -> <Title>.m4b')
    s.add_argument('script', type=Path)
    s.add_argument(
        '--cast',
        type=Path,
        help='All voice choices, JSON: {"voices": {"narrator"|"mc"|"male"|"female"|<speaker>: voice}}. '
        'A VieNeu name runs on VieNeu, an onboarded id on Drama-3; roles left out use casts/mixed.json',
    )
    s.add_argument(
        '--unknown',
        choices=['fail', 'narrator'],
        default='fail',
        help='What to do with [?] lines and speakers of unknown gender',
    )
    s.add_argument('--author')
    s.add_argument('--series', help='Album tag; volumes of a series share it')
    s.add_argument(
        '--volume',
        help='Volume number (track tag, and "<Series> vN - <Subtitle>" in title and file name); '
        'default: from the story folder name, e.g. meimei_v2',
    )
    s.add_argument('--cover', type=Path)
    s.add_argument('--no-cover', action='store_true')
    s.add_argument('--bitrate', default='64k')
    s.add_argument('--threads', type=int, default=2, help='Threads per worker (VieNeu: more barely helps)')
    s.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Parallel VieNeu processes (4: ~3.4x faster than ONNX on GGUF, ~2x faster than 1 worker on ONNX)',
    )
    s.add_argument(
        '--vieneu-backend',
        choices=['gguf', 'onnx'],
        default='gguf',
        help='VieNeu runtime: gguf (audio.cpp on Metal, default; ONNX for any chunk it fails on) or onnx (CPU)',
    )
    s.add_argument('--chapters', type=int, help='Only build the first N chapters (for a quick test)')
    s.add_argument(
        '--only',
        metavar='SPEC',
        help='Only build these chapters, 1-based: "6", "6-8" or "1,6-7" (a pilot of a later scene)',
    )
    s.set_defaults(func=cmd_build)
    s = sub.add_parser('repair', help='Delete cached chunks with long silences (then rebuild)')
    s.add_argument('script', type=Path)
    s.add_argument('--engine', choices=['vieneu', 'drama3'], default='drama3')
    s.add_argument('--max-silence', type=float, default=MAX_SILENCE_S)
    s.add_argument('--dry-run', action='store_true', help='Only list the chunks')
    s.add_argument(
        '--fallbacks',
        action='store_true',
        help='Instead: delete tagged chunks that were read without their tags, to retry them',
    )
    s.set_defaults(func=cmd_repair)
    s = sub.add_parser('scan', help=argparse.SUPPRESS)
    s.add_argument('cache', type=Path)
    s.add_argument('--max-silence', type=float, default=MAX_SILENCE_S)
    s.add_argument('--delete', action='store_true')
    s.set_defaults(func=cmd_scan)
    s = sub.add_parser('make-ref', help='Create a Drama-3 reference clip from a VieNeu voice')
    s.add_argument('--voice', required=True)
    s.add_argument('--text')
    s.set_defaults(func=cmd_make_ref)
    s = sub.add_parser('worker', help=argparse.SUPPRESS)
    s.add_argument('engine', choices=['vieneu', 'drama3'])
    s.add_argument('jobs', type=Path)
    s.add_argument('out', type=Path)
    s.add_argument('--threads', type=int, default=4)
    s.add_argument('--backend', choices=['gguf', 'onnx'], default='gguf', help='VieNeu runtime; ONNX is the fallback')
    s.add_argument('--skip-failed', action='store_true', help='Report a failed chunk and continue (auditions)')
    s.set_defaults(func=cmd_worker)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main()
