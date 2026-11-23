"""From script lines to cached chunks: the units each chapter reads, their pauses, and chunk cache keys."""

import hashlib
import json
import re
from typing import Any

from viettts.engines.drama3 import REVISION as DRAMA3_REVISION
from viettts.text import join_kind, split_chunks

from .cast import voice_for
from .script import UNKNOWN
from .tags import TaggedText, split_tagged, spoken, untagged

# Longer sentences are cut at commas (viettts.text.split_chunks). Drama-3 stays under mlx-audio's own 300-byte
# generation unit (fish_drama3/chunking.py CHUNK_BYTES), so the runtime never re-splits a chunk itself.
MAX_CHARS = {'vieneu': 225, 'drama3': 200}


MAX_BYTES = {'vieneu': None, 'drama3': 300}


# Every chunk is trimmed to EDGE_MS of silence at each end when assembled, so a join is EDGE_MS * 2 plus:
PAUSES_MS = {'segment': 300, 'paragraph': 600, 'title': 1200, 'chapter_end': 1700}  # after a script line


JOIN_MS = {'sentence': 250, 'clause': 100, 'word': 0}  # between chunks of a line


def plan_units(script, voices, unknown, title_text=True, enhanced=None):
    """Chapters as lists of (voice_key, text, pause_after_ms, script line number or None for titles).

    enhanced: {line number: tagged text}, used for lines whose voice runs on Drama-3 (voices[key] is an
    (engine, voice) pair); their text is a TaggedText. Other engines would read the tags aloud.
    """
    enhanced = enhanced or {}
    chapters = []
    for index, (title, paras) in enumerate(script.chapters):
        units = []
        if index == 0 and title_text and script.meta.get('title'):
            units.append(('narrator', script.meta['title'], PAUSES_MS['title'], None))
        units.append(('narrator', title, PAUSES_MS['title'], None))
        for para in paras:
            for i, line in enumerate(para):
                if line.label == UNKNOWN and unknown != 'narrator':
                    raise SystemExit(
                        f'Script line {line.number} has no speaker ([?]). Fix it, or pass --unknown narrator.'
                    )
                text = spoken(line.text)
                if not re.search(r'\w', text):  # nothing to read: a progress bar ▰▰▱, a lone dash or emoji
                    continue
                key = voice_for(line.speaker, script.speakers, voices, unknown, script.narrator)
                tagged = spoken(enhanced.get(line.number, ''))
                if tagged and tagged != text and isinstance(voices[key], tuple) and voices[key][0] == 'drama3':
                    text = TaggedText(tagged)
                pause = PAUSES_MS['paragraph'] if i == len(para) - 1 else PAUSES_MS['segment']
                units.append((key, text, pause, line.number))
        if units:
            key, text, _, number = units[-1]
            units[-1] = (key, text, PAUSES_MS['chapter_end'], number)
        chapters.append((title, units))
    return chapters


def cache_key(engine, voice, text):
    parts = [engine, voice, text, 2]  # 2: leveled audio
    if engine == 'drama3':  # new Drama-3 weights must not reuse chunks from older ones
        parts.append(DRAMA3_REVISION)
    blob = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode('utf-8')).hexdigest()


def plan_layout(out, chapters, voices):
    """Planned chapters -> (layout, jobs). layout: [(title, [(refs, pause_ms, line number)])], each ref an
    (engine, chunk id, join_ms after it) cached as out/cache/<engine>/<id>.wav; jobs: the chunks still missing,
    {engine: {chunk id: worker job}}."""

    jobs: dict[str, dict[str, dict[str, Any]]] = {}
    layout = []
    for title, units in chapters:
        parts = []
        for key, text, pause, number in units:
            engine, voice = voices[key]
            cache = out / 'cache' / engine
            refs = []
            split = split_tagged if isinstance(text, TaggedText) else split_chunks
            chunks = split(text, MAX_CHARS[engine], max_bytes=MAX_BYTES[engine])
            for i, chunk in enumerate(chunks):
                cid = cache_key(engine, voice, chunk)
                words = untagged(chunk) if isinstance(text, TaggedText) else chunk
                refs.append((engine, cid, JOIN_MS[join_kind(words)] if i < len(chunks) - 1 else 0))
                if not (cache / f'{cid}.wav').is_file():
                    job = dict(id=cid, text=chunk, voice=voice)
                    if words != chunk:  # tagged: the worker falls back to the words alone
                        job['plain'] = words
                    jobs.setdefault(engine, {})[cid] = job
            parts.append((refs, pause, number))
        layout.append((title, parts))
    return layout, jobs
