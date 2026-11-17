"""Repository assets and subprocess environments, independent of the caller's cwd."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def uv_command(engine: str, *args: str) -> tuple[list[str], dict[str, str]]:
    """Run Python in one engine's locked environment with this package importable."""
    if engine not in ('vieneu', 'drama3'):
        raise ValueError(f'Unsupported engine: {engine}')
    env = os.environ.copy()
    env.setdefault('UV_CACHE_DIR', str(ROOT / '.uv' / 'cache'))
    env.setdefault('UV_PYTHON_INSTALL_DIR', str(ROOT / '.uv' / 'python'))
    env['PYTHONPATH'] = os.pathsep.join(filter(None, (str(ROOT), env.get('PYTHONPATH'))))
    command = ['uv', 'run', '--locked', '--project', str(ROOT / 'engines' / engine), 'python', *args]
    return command, env
