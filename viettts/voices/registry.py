"""On-disk voice metadata and ordered reference clips (no engine dependencies)."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from viettts.paths import ROOT

VOICES = ROOT / 'references' / 'voices'

# Metadata includes provider evidence and user-defined descriptive fields.
VoiceMetadata = dict[str, Any]


class VoiceReferences(TypedDict):
    ref_audio: list[str]
    ref_text: list[str]


def all_voices(directory: Path = VOICES) -> list[VoiceMetadata]:
    return [json.loads(path.read_text(encoding='utf-8')) for path in sorted(directory.glob('*/voice.json'))]


def load(vid: str, directory: Path = VOICES) -> VoiceMetadata:
    path = directory / vid / 'voice.json'
    if not path.is_file():
        known = ', '.join(sorted(p.name for p in directory.glob('*') if p.is_dir()))
        raise SystemExit(f'No voice "{vid}". Known: {known}')
    return json.loads(path.read_text(encoding='utf-8'))


def save(meta: VoiceMetadata, directory: Path = VOICES) -> None:
    meta['updated'] = datetime.now().isoformat(timespec='seconds')
    folder = directory / meta['id']
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'voice.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def refs_of(vid: str, directory: Path = VOICES) -> list[tuple[int, Path, Path]]:
    """[(n, wav, txt)] for reference-N.wav files, in numerical order."""
    folder = directory / vid
    out = []

    def reference_number(path: Path) -> int:
        match = re.search(r'(\d+)', path.stem)
        assert match is not None  # Only reference-N.wav names are supported.
        return int(match[1])

    for wav in sorted(folder.glob('reference-*.wav'), key=reference_number):
        n = reference_number(wav)
        out.append((n, wav, folder / f'reference-{n}.txt'))
    return out


def voice_refs(vid: str, directory: Path = VOICES) -> VoiceReferences:
    refs = refs_of(vid, directory)
    missing = [n for n, _, txt in refs if not txt.is_file()]
    if not refs or missing:
        raise SystemExit(f'{vid}: reference(s) {missing or "?"} have no reviewed transcript (set-transcript).')
    return dict(
        ref_audio=[str(wav) for _, wav, _ in refs],
        ref_text=[txt.read_text(encoding='utf-8').strip() for _, _, txt in refs],
    )
