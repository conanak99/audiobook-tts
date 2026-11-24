"""Command-line entry point; parsing and review need only the standard library."""

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='python3 -m viettts', description=__doc__)
    parser.add_argument(
        'command',
        choices=['audiobook', 'voice', 'sfx', 'subs', 'speak'],
        help='Build audiobooks, onboard voices, add sound effects, transcribe Japanese subtitles, or synthesize speech',
    )
    # Leave each command's options/help to its own parser.
    if not argv or argv[0] in ('-h', '--help'):
        parser.parse_args(argv)
        return
    command = parser.parse_args(argv[:1]).command
    if command == 'audiobook':
        from .audiobook.cli import main as run

        return run(argv[1:])
    if command == 'voice':
        from .voices.onboarding import main as run

        return run(argv[1:])
    if command == 'sfx':
        from .sfx.cli import main as run

        return run(argv[1:])
    if command == 'subs':
        from .subs.cli import main as run

        return run(argv[1:])
    engine_parser = argparse.ArgumentParser(
        prog='python3 -m viettts speak',
        add_help=False,
        description='Select an engine; add --help after --engine for its options.',
    )
    engine_parser.add_argument('--engine', choices=['vieneu', 'drama3'], required=True)
    if argv[1:] in (['-h'], ['--help']):
        engine_parser.print_help()
        return
    args, remaining = engine_parser.parse_known_args(argv[1:])
    if args.engine == 'vieneu':
        from .engines.vieneu import main as run
    else:
        from .engines.drama3 import main as run
    return run(remaining)
