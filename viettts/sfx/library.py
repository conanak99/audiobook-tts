"""The SFX library: references/sfx/library.json plus levelled 44.1 kHz WAVs.

A sound is listed first (id, category, kind, seconds, prompt, takes) and rendered later by
viettts.sfx.generate. Each take is the same prompt with its own seed and its own length (take 1 is
`seconds` long, the others shorter or longer by LENGTH_FACTORS), so a sound heard several times in a book
never plays the same twice in a row: rendered holds one {file, seconds, seed, raw_peak_db, active, passed_gate}
per take, the first take as <category>/<id>.wav and the others as <category>/<id>-<n>.wav.
"""

import json
import re
from pathlib import Path
from typing import Any

from viettts.paths import ROOT

LIBRARY_DIR = ROOT / 'references' / 'sfx'
KINDS = ('loop', 'oneshot')  # loop: steady texture, cut or repeated to any length; oneshot: one event
MAX_SECONDS = 30.0
MAX_TAKES = 8
DEFAULT_TAKES = 3  # the take as listed plus two variants
LENGTH_FACTORS = (1.0, 0.6, 1.5, 0.8, 1.25, 0.7, 1.35, 0.9)  # take n is seconds * LENGTH_FACTORS[n - 1] long
MIN_TAKE_SECONDS = 2.0  # MOSS mostly renders silence for shorter lengths
SAMPLE_RATE = 44100  # Drama-3's rate, so a mix under Drama-3 voices needs no resampling
LEVEL_DBFS = -20.0  # RMS of the audible part of every sound

ID_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def library_path(root: Path = LIBRARY_DIR) -> Path:
    return root / 'library.json'


def load(root: Path = LIBRARY_DIR) -> dict[str, Any]:
    path = library_path(root)
    if not path.is_file():
        return dict(sample_rate=SAMPLE_RATE, level_dbfs=LEVEL_DBFS, sounds=[])
    return json.loads(path.read_text(encoding='utf-8'))


def save(library: dict[str, Any], root: Path = LIBRARY_DIR) -> None:
    root.mkdir(parents=True, exist_ok=True)
    library['sounds'].sort(key=lambda s: (s['category'], s['id']))
    text = json.dumps(library, ensure_ascii=False, indent=1) + '\n'
    library_path(root).write_text(text, encoding='utf-8')


def sounds(library: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s['id']: s for s in library['sounds']}


def takes_wanted(sound: dict[str, Any]) -> int:
    return int(sound.get('takes', DEFAULT_TAKES))


def take_seconds(sound: dict[str, Any], n: int) -> float:
    """How long take n (1-based) is rendered."""
    seconds = float(sound['seconds']) * LENGTH_FACTORS[(n - 1) % len(LENGTH_FACTORS)]
    return round(min(MAX_SECONDS, max(MIN_TAKE_SECONDS, seconds)), 1)


def take_file(sound: dict[str, Any], n: int) -> str:
    """Where take n (1-based) of a sound lives, relative to the library."""
    return f'{sound["category"]}/{sound["id"]}{"" if n == 1 else f"-{n}"}.wav'


def entry_problems(entry: dict[str, Any], existing: dict[str, dict[str, Any]]) -> list[str]:
    problems = []
    if not ID_RE.match(entry.get('id', '')):
        problems.append(f'id "{entry.get("id")}" must be lowercase words joined by "-"')
    elif entry['id'] in existing:
        problems.append(f'id "{entry["id"]}" already exists ({existing[entry["id"]]["category"]})')
    if not ID_RE.match(entry.get('category', '')):
        problems.append('category must be lowercase words joined by "-" (bed, undress, body, props, scene, ...)')
    if entry.get('kind') not in KINDS:
        problems.append(f'kind must be one of {", ".join(KINDS)}')
    seconds = entry.get('seconds')
    if not isinstance(seconds, int | float) or not 0.5 <= seconds <= MAX_SECONDS:
        problems.append(f'seconds must be between 0.5 and {MAX_SECONDS:g}')
    if len(entry.get('prompt', '').strip()) < 10:
        problems.append('prompt must describe the sound in a full English sentence')
    takes = entry.get('takes', DEFAULT_TAKES)
    if not isinstance(takes, int) or not 1 <= takes <= MAX_TAKES:
        problems.append(f'takes must be a whole number from 1 to {MAX_TAKES}')
    return problems


def add(entry: dict[str, Any], root: Path = LIBRARY_DIR) -> dict[str, Any]:
    library = load(root)
    problems = entry_problems(entry, sounds(library))
    if problems:
        raise ValueError('; '.join(problems))
    keep = ('id', 'category', 'kind', 'seconds', 'prompt', 'takes')
    library['sounds'].append({k: entry[k] for k in keep if k in entry})
    save(library, root)
    return library


def set_takes(sound_id: str, takes: int, root: Path = LIBRARY_DIR) -> dict[str, Any]:
    """Ask for more (or fewer) takes of a sound. Fewer drops the last takes from the listing (their files
    are deleted); more are rendered by the next generate."""
    if not 1 <= takes <= MAX_TAKES:
        raise ValueError(f'takes must be from 1 to {MAX_TAKES}')
    library = load(root)
    sound = sounds(library).get(sound_id)
    if not sound:
        raise ValueError(f'"{sound_id}" is not in the library')
    sound['takes'] = takes
    for dropped in sound.get('rendered', [])[takes:]:
        (root / dropped['file']).unlink(missing_ok=True)
    sound['rendered'] = sound.get('rendered', [])[:takes]
    save(library, root)
    return sound


def take_ok(sound: dict[str, Any], n: int, root: Path = LIBRARY_DIR) -> bool:
    """Take n is rendered and on disk. Its length doesn't matter: take_seconds() only sets the length of a
    take rendered from now on, so changing a sound's seconds never throws good takes away (use
    generate --force to redo them)."""
    rendered = sound.get('rendered', [])
    return n <= len(rendered) and (root / rendered[n - 1]['file']).is_file()


def stale_takes(sound: dict[str, Any], root: Path = LIBRARY_DIR) -> list[int]:
    """The takes (1-based) generate has to render: the ones not on disk yet."""
    return [n for n in range(1, takes_wanted(sound) + 1) if not take_ok(sound, n, root)]


def missing_takes(sound: dict[str, Any], root: Path = LIBRARY_DIR) -> int:
    return len(stale_takes(sound, root))


def remove(sound_id: str, root: Path = LIBRARY_DIR) -> dict[str, Any]:
    """Drop a sound from the library with all its take files."""
    library = load(root)
    sound = sounds(library).get(sound_id)
    if not sound:
        raise ValueError(f'"{sound_id}" is not in the library')
    for take in sound.get('rendered', []):
        (root / take['file']).unlink(missing_ok=True)
    library['sounds'].remove(sound)
    save(library, root)
    return sound


def sound_files(sound: dict[str, Any], root: Path = LIBRARY_DIR) -> list[Path]:
    """The usable takes in take order ([] while the sound is only listed)."""
    wanted = takes_wanted(sound)
    return [root / t['file'] for n, t in enumerate(sound.get('rendered', [])[:wanted], 1) if take_ok(sound, n, root)]


def weak_takes(sound: dict[str, Any]) -> list[int]:
    """1-based takes that failed the level/activity gate on every seed tried (kept, but worth a listen)."""
    return [n for n, t in enumerate(sound.get('rendered', []), 1) if not t.get('passed_gate', True)]
