#!/usr/bin/env python3
"""Markdown story -> speaker-attributed script -> multi-voice M4B audiobook with chapters."""

import argparse
import hashlib
import json
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from array import array
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from viettts.engines.drama3 import REVISION as DRAMA3_REVISION
from viettts.paths import ROOT
from viettts.paths import uv_command as python_command
from viettts.text import slugify
from viettts.voices import registry

from .script import NARRATION, UNKNOWN, read_script

# The cast picks every voice, and each voice picks its engine: a VieNeu voice name runs on VieNeu; an onboarded
# voice id (references/voices/<id>/, see viettts.voices.onboarding) runs on Drama-3. Roles a cast leaves out get
# these defaults (casts/mixed.json): fast VieNeu narration and men, a Drama-3 cloned heroine, and the MC's
# dialogue on DEFAULT_MC, the Drama-3 clone of the narrator voice, so it takes enhance.txt tags. The MC default
# applies only with the default narrator; a cast with another narrator keeps the MC on that narrator's voice
# unless it sets "mc" itself. A cast may also give any speaker a voice.
VOICES_DIR = ROOT / 'references' / 'voices'
DEFAULT_FEMALE = 'shirone-mika'
DEFAULT_VOICES = {'narrator': 'Thiện Minh', 'male': 'Hải Đăng', 'female': DEFAULT_FEMALE}
DEFAULT_MC = 'thien-minh-drama'
# Manual picked
VIENEU_VOICES = [
    # male voices
    'Adam bựa',
    'Thiện Minh',
    'Hải Đăng',
    'Đức Trí',
    'Thái Sơn',
    # female voices
    'Thùy Dung',
    'Ngọc Huyền',
    'Kim Thanh',
    'Mỹ Duyên',
    'Thục Đoan',
]

# Longer sentences are cut at commas (viettts.text.split_chunks). Drama-3 stays under mlx-audio's own 300-byte
# generation unit (fish_drama3/chunking.py CHUNK_BYTES), so the runtime never re-splits a chunk itself.
MAX_CHARS = {'vieneu': 225, 'drama3': 200}
MAX_BYTES = {'vieneu': None, 'drama3': 300}
MAX_SILENCE_S = 1.5  # a generated chunk with a longer internal pause is regenerated (Drama-3) or squeezed
# Every chunk is trimmed to EDGE_MS of silence at each end when assembled, so a join is EDGE_MS * 2 plus:
PAUSES_MS = {'segment': 300, 'paragraph': 600, 'title': 1200, 'chapter_end': 1700}  # after a script line
JOIN_MS = {'sentence': 250, 'clause': 100, 'word': 0}  # between chunks of a line
EDGE_MS = 30
REF_SENTENCE = (
    'Xin chào, tôi là người đọc truyện hôm nay. Mời bạn cùng lắng nghe câu chuyện chậm rãi và rõ ràng này nhé.'
)


def spoken(text):
    """Text as sent to TTS: drop quote marks and decorations the engines would read or choke on."""
    text = re.sub(r'["«»“”~*_]', '', text)
    return ' '.join(text.split())


# --- enhance: Drama-3 performance tags (.opencode/skills/audiobook/references/enhance.md) --------
# enhance.txt next to script.txt holds "L<n>: <line with tags>" for Drama-3 lines; script.txt stays plain.
SCOPE_TAGS = ('whisper', 'emphasis', 'soft', 'fast', 'slow', 'stress', 'forceful')
TAG = re.compile(r'\[[^\[\]]*\]|</?(?:' + '|'.join(SCOPE_TAGS) + r')>')
MAX_DIRECTION = 60  # characters; long, abstract directions made Drama-3 run into its frame cap


class TaggedText(str):
    """A unit's text that carries enhance tags (split with split_tagged, Drama-3 only)."""


def untagged(text):
    """The words of a tagged line: directions and sounds become spaces, paired tags vanish."""
    text = re.sub(r'\[[^\[\]]*\]', ' ', text)
    text = re.sub(r'</?[A-Za-z]+>', '', text)
    return ' '.join(text.split())


def tag_problems(tagged, plain):
    """Why a tagged line can't stand in for its plain script line ([] if it can)."""
    problems: list[str] = []
    stack: list[str] = []
    for direction in re.findall(r'\[([^\[\]]*)\]', tagged):
        if not direction.strip():
            problems.append('empty [ ]')
        elif len(direction) > MAX_DIRECTION:
            problems.append(f'direction over {MAX_DIRECTION} characters: [{direction[:30]}…]')
        elif re.search(r'[<>]', direction):
            problems.append(f'tag inside a direction: [{direction}]')
    if re.search(r'[\[\]]', re.sub(r'\[[^\[\]]*\]', '', tagged)):
        problems.append('unbalanced [ ]')
    for close, name in re.findall(r'<(/?)([^<>]*)>', tagged):
        if name not in SCOPE_TAGS:
            problems.append(f'unsupported tag <{close}{name}> (use {", ".join(SCOPE_TAGS)})')
        elif not close:
            if stack:
                problems.append(f'<{name}> inside <{stack[-1]}>: nesting is not supported')
            stack.append(name)
        elif not stack or stack.pop() != name:
            problems.append(f'unmatched </{name}>')
    if stack:
        problems.append(f'<{stack[-1]}> is not closed on this line')
    if re.search(r'<([a-z]+)>\s*(?:\[[^\[\]]*\]\s*)*</\1>', tagged):
        problems.append('a paired tag wraps no words')
    if untagged(spoken(tagged)) != untagged(spoken(plain)):
        problems.append('the words differ from the script line (only add tags)')
    return problems


def split_tagged(text, max_chars, max_bytes=None):
    """split_chunks for a tagged line. Never cuts inside a tag, keeps a tag-only piece with its words, closes
    and reopens a paired tag across a cut, and repeats the line's leading direction on every later chunk,
    because Drama-3 voices each chunk on its own."""
    from viettts.text import split_chunks

    tags = TAG.findall(text)

    # Mask each tag as one unbreakable word at least as long, in characters and bytes, as the tag itself.
    def width(tag):
        return max(len(tag), len(tag.encode('utf-8')))

    masked = TAG.sub(lambda m: '\x01' + '\x00' * (width(m[0]) - 2) + '\x02', text)
    # Room for what a cut adds to a chunk: a repeated direction and a reopened and closed paired tag.
    reserve = max((width(t) + 1 for t in tags if t.startswith('[')), default=0) + (
        len('<forceful></forceful>') if any(t.startswith('<') for t in tags) else 0
    )
    floor = max(width(t) for t in tags) + 40 if tags else 0  # a masked tag must always fit whole
    restore = iter(tags)
    pieces = [
        re.sub(r'\x01\x00*\x02', lambda _: next(restore), c)
        for c in split_chunks(
            masked, max(floor, max_chars - reserve), max_bytes=max(floor, max_bytes - reserve) if max_bytes else None
        )
    ]
    merged: list[str] = []
    for piece in pieces:
        if merged and (not untagged(piece) or not untagged(merged[-1])):
            merged[-1] += ' ' + piece
        else:
            merged.append(piece)
    chunks, scope, current = [], None, None
    for chunk in merged:
        opening, carried = directions(chunk), current
        if opening:
            current = opening[-1][1]
        if scope:
            chunk = f'<{scope}>{chunk}'
        for close, name in re.findall(r'<(/?)([a-z]+)>', chunk):
            scope = None if close else name
        if scope:
            chunk += f'</{scope}>'
        if carried and not (opening and opening[0][0] == 0):
            chunk = f'{carried} {chunk}'
        chunks.append(chunk)
    return chunks


SOUND = re.compile(
    r'(?i)sigh|laugh|giggl|chuckl|gasp|breath|inhal|exhal|sniff|sob|cough|pause|yawn|groan|'
    r'scoff|snort|\bhums?\b|kiss|smooch|moan|whimper|whine|gulp|hiccup|throat|silence|\bbeat\b|'
    r'pant|purr|squeal|yelp|hiss|shudder|shiver|mmm|hmm'
)


def is_sound(bracket):
    """[sighs], [small laugh], [soft moan]: a short event, not a delivery. A list ([breathless, intimate]) or
    an -ing form ([laughing], [breathing heavily]) is a direction."""
    inner = bracket[1:-1]
    return (
        bool(SOUND.search(inner))
        and ',' not in inner
        and len(inner.split()) <= 3
        and not re.search(r'(?i)ing\b', inner)
    )


def directions(chunk):
    """[(position, bracket)] for the directions that open a sentence (not sounds): these set the delivery
    that split_tagged repeats on the next chunks."""
    return [
        (m.start(), m[0])
        for m in re.finditer(r'\[[^\[\]]*\]', chunk)
        if not is_sound(m[0]) and re.fullmatch(r'|.*[.!?…]["”’\')]*\s+', chunk[: m.start()])
    ]


def enhance_path(script_path):
    return script_path.with_name('enhance.txt')


def read_enhance(text):
    """{line number: tagged text} from "L<n>: text" lines (an optional "=> " prefix; other lines ignored)."""
    entries = {}
    for raw in text.splitlines():
        m = re.match(r'^(?:=>\s*)?L(\d+)\s*:\s*(.+)$', raw.strip())
        if m:
            entries[int(m[1])] = m[2].strip()
    return entries


def match_enhance(script, entries):
    """Resolve enhance entries to script lines. Returns ({line number: tagged}, [stale entries]).

    An entry whose line moved (apply-review inserts @speaker lines) goes to the nearest line with the same
    words; an entry whose words are found nowhere (the line was edited) is stale.
    """
    lines = {line.number: line for _, paras in script.chapters for p in paras for line in p}
    by_words = defaultdict(list)
    for line in lines.values():
        by_words[untagged(spoken(line.text))].append(line.number)
    matched, moved, stale = {}, [], []
    for n, tagged in sorted(entries.items()):
        words = untagged(spoken(tagged))
        if n in lines and untagged(spoken(lines[n].text)) == words:
            matched[n] = tagged
        else:
            moved.append((n, tagged, words))
    for n, tagged, words in moved:
        free = [k for k in by_words.get(words, []) if k not in matched]
        if free:
            matched[min(free, key=lambda k: abs(k - n))] = tagged
        else:
            stale.append((n, tagged))
    return matched, stale


def check_enhance(script_path, script):
    """Read enhance.txt (written by the agent). Returns ({line number: tagged}, [(line, message)])."""
    path = enhance_path(script_path)
    if not path.is_file():
        return {}, []
    matched, stale = match_enhance(script, read_enhance(path.read_text(encoding='utf-8')))
    byte_limit = MAX_BYTES['drama3']
    assert byte_limit is not None
    lines = {line.number: line for _, paras in script.chapters for p in paras for line in p}
    findings = [(n, f'enhance: no script line has these words any more (edited?): {t[:60]}') for n, t in stale]
    for n, tagged in matched.items():
        findings += [(n, f'enhance: {problem}') for problem in tag_problems(tagged, lines[n].text)]
    for n, tagged in matched.items():
        for chunk in split_tagged(spoken(tagged), MAX_CHARS['drama3'], byte_limit):
            if len(chunk.encode('utf-8')) > byte_limit:
                findings.append(
                    (
                        n,
                        f'enhance: a chunk is over {MAX_BYTES["drama3"]} bytes with its tags; '
                        f'use fewer or shorter tags',
                    )
                )
    return matched, sorted(findings)


def uv_command(engine, *args):
    return python_command(engine, '-m', 'viettts', 'audiobook', *args)


def source_volume(source):
    """The volume number in the story's folder name: meimei_v2/story_vn.md -> 2 ('vol2', 'v-3' too)."""
    m = re.search(r'(?:^|[_\-\s.])v(?:ol)?[_\-]?(\d+)$', Path(source).parent.name, re.I) if source else None
    return int(m[1]) if m else None


def volume_title(title, volume):
    """('Mị Mị — Khi Ngọn Núi', 2) -> ('Mị Mị', 'Mị Mị v2 - Khi Ngọn Núi'): the series is the part before the
    first dash. Without a dash the volume goes at the end; without a volume the title is kept."""
    if not volume:
        return '', title
    m = re.match(r'(.+?)\s+[—–-]\s+(.+)', title)
    series, rest = (m[1], m[2]) if m else (title, '')
    if re.search(rf'\bv{volume}$', series):  # already numbered
        series = series[: series.rindex(' v')] if ' v' in series else series
    numbered = f'{series} v{volume}'
    return series, f'{numbered} - {rest}' if rest else numbered


def parse_chapter_spec(spec, count):
    """'6', '6-8' or '1,6-7' -> sorted unique 1-based chapter numbers within 1..count."""
    picked: set[int] = set()
    for part in spec.replace(' ', '').split(','):
        m = re.fullmatch(r'(\d+)(?:-(\d+))?', part)
        if not m:
            raise SystemExit(f'--only: cannot read "{part}"; use e.g. 6, 6-8 or 1,6-7')
        a, b = int(m[1]), int(m[2] or m[1])
        if not 1 <= a <= b <= count:
            raise SystemExit(f'--only: "{part}" is outside chapters 1-{count}')
        picked.update(range(a, b + 1))
    return sorted(picked)


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


# --- build -------------------------------------------------------------------------------------------
def load_cast(args):
    """Returns (mix, {role or speaker: (engine, voice)}) from --cast, the only place voices are chosen.

    Roles: narrator, mc, male, female; any other key is a speaker id from the script. A voice is a VieNeu
    name or an onboarded Drama-3 voice id, and that alone decides its engine. mix is "vieneu" or "drama3"
    when every voice runs on that engine, else "mixed"."""
    cast = json.loads(args.cast.read_text(encoding='utf-8')) if args.cast else {}
    if 'engine' in cast:
        raise SystemExit(
            f'{args.cast}: remove "engine"; each voice picks its own engine '
            '(a VieNeu name runs on VieNeu, an onboarded voice id on Drama-3).'
        )
    specs = {**DEFAULT_VOICES, **cast.get('voices', {})}
    if 'mc' not in specs and specs['narrator'] == DEFAULT_VOICES['narrator']:
        specs['mc'] = DEFAULT_MC
    voices = {key: resolve_voice(spec) for key, spec in specs.items()}
    return cast_mix(voices), voices


def cast_mix(voices):
    engines = {engine for engine, _ in voices.values()}
    return engines.pop() if len(engines) == 1 else 'mixed'


ROLES = ('narrator', 'mc', 'male', 'female')


def unmatched_cast_keys(voices, script):
    """Cast keys that are neither a role nor a speaker id in the script (a typo keeps the default voice)."""
    return [key for key in voices if key not in ROLES and key not in script.speakers]


def validate_cast(script, cast_path, script_name='script.txt'):
    """Resolve and plan a cast exactly as a build would, without loading a TTS engine."""
    try:
        mix, voices = load_cast(argparse.Namespace(cast=cast_path))
    except (OSError, json.JSONDecodeError, SystemExit) as error:
        return None, {}, [str(error)]
    findings = [
        f'key "{key}" is not a role or a speaker in {script_name}' for key in unmatched_cast_keys(voices, script)
    ]
    try:
        plan_units(script, voices, 'fail')
    except SystemExit as error:
        findings.append(str(error))
    return mix, voices, findings


def onboarded_voices():
    return {info['id']: info for info in registry.all_voices(VOICES_DIR)}


def resolve_voice(spec):
    """'Thiện Minh' -> VieNeu; an onboarded voice id ('lynasa') -> Drama-3 with its reviewed reference.

    Raw audio files are refused: onboard them first (python3 -m viettts voice), so every Drama-3 voice has a clean
    cut, a reviewed transcript and auditioned samples. The VieNeu-made male references
    (references/vieneu-*.wav, from make-ref) are the only files accepted directly.
    """
    if isinstance(spec, dict) and spec.get('engine') == 'vieneu':
        return 'vieneu', spec['voice']
    onboarded = onboarded_voices()
    key = slugify(str(spec)) if isinstance(spec, str) else None
    if key is not None and key in onboarded:
        info = onboarded[key]
        if info.get('status') != 'onboarded':
            raise SystemExit(
                f'Voice "{key}" is still a draft; finish onboarding it (python3 -m viettts voice approve).'
            )
        if info.get('samples') and info.get('samples_model') != DRAMA3_REVISION:
            print(
                f'warning: the samples of "{key}" were made with older Drama-3 weights; '
                f'regenerate them (python3 -m viettts voice samples {key}) and listen again',
                file=sys.stderr,
            )
        return 'drama3', registry.voice_refs(key, VOICES_DIR)
    if isinstance(spec, dict) or str(spec).lower().endswith('.wav'):
        path = Path(spec['ref_audio'] if isinstance(spec, dict) else spec)
        path = path if path.is_absolute() else ROOT / path
        if path.parent == ROOT / 'references' and path.name.startswith('vieneu-'):
            return 'drama3', drama3_voice(spec)
        raise SystemExit(
            f'{spec}: not an onboarded voice. Onboard it first (voice-onboarding skill / '
            f'python3 -m viettts voice), then use its id. Onboarded: {", ".join(onboarded) or "none"}.'
        )
    if spec in VIENEU_VOICES:
        return 'vieneu', spec
    raise SystemExit(
        f'Unknown voice "{spec}". Use an onboarded id ({", ".join(onboarded) or "none"}) or a VieNeu '
        f'voice ({", ".join(VIENEU_VOICES)}).'
    )


def voice_label(engine, voice):
    if isinstance(voice, str):
        return f'{voice} ({engine})'
    refs = voice['ref_audio'] if isinstance(voice['ref_audio'], list) else [voice['ref_audio']]
    return (
        f'{Path(refs[0]).parent.name if len(refs) > 1 or "voices" in refs[0] else Path(refs[0]).name}'
        f' ({engine}, {len(refs)} ref{"s" if len(refs) > 1 else ""})'
    )


def drama3_voice(spec):
    """A Drama-3 voice is a reference WAV plus its exact transcript."""
    if isinstance(spec, dict):
        audio, text = Path(spec['ref_audio']), spec.get('ref_text')
    else:
        audio, text = Path(spec), None
    audio = audio if audio.is_absolute() else ROOT / audio
    if not text and audio.with_suffix('.txt').is_file():
        text = audio.with_suffix('.txt').read_text(encoding='utf-8').strip()
    if not audio.is_file() or not text:
        raise SystemExit(f'Drama-3 voice needs a reference WAV and its transcript: {audio}')
    return {'ref_audio': str(audio), 'ref_text': text}


def voice_for(label, speakers, voices, unknown, narrator=None):
    """Voice key for a script label. The first-person MC (the narrator's own id) speaks with the cast's
    "mc" voice (or a voice mapped to the MC's id), else with the narrator voice: usually one person."""
    if label == NARRATION:
        return 'narrator'
    if label in voices:
        return label
    if label == narrator:
        return 'mc' if 'mc' in voices else 'narrator'
    gender = speakers.get(label, 'male' if label == 'male' else 'female' if label == 'female' else '?')
    if gender in ('male', 'female'):
        return gender
    if unknown == 'narrator':
        return 'narrator'
    raise SystemExit(
        f'Speaker "{label}" has no voice: set "@speaker {label} male|female" in the script, '
        f'map it in --cast, or pass --unknown narrator.'
    )


def plan_units(script, voices, unknown, title_text=True, enhanced=None):
    """Chapters as lists of (voice_key, text, pause_after_ms).

    enhanced: {line number: tagged text}, used for lines whose voice runs on Drama-3 (voices[key] is an
    (engine, voice) pair); their text is a TaggedText. Other engines would read the tags aloud.
    """
    enhanced = enhanced or {}
    chapters = []
    for index, (title, paras) in enumerate(script.chapters):
        units = []
        if index == 0 and title_text and script.meta.get('title'):
            units.append(('narrator', script.meta['title'], PAUSES_MS['title']))
        units.append(('narrator', title, PAUSES_MS['title']))
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
                units.append((key, text, PAUSES_MS['paragraph'] if i == len(para) - 1 else PAUSES_MS['segment']))
        if units:
            units[-1] = (*units[-1][:2], PAUSES_MS['chapter_end'])
        chapters.append((title, units))
    return chapters


def cache_key(engine, voice, text):
    parts = [engine, voice, text, 2]  # 2: leveled audio
    if engine == 'drama3':  # new Drama-3 weights must not reuse chunks from older ones
        parts.append(DRAMA3_REVISION)
    blob = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode('utf-8')).hexdigest()


def trim_edges(pcm, rate, channels, width, threshold_db=-40, margin_ms=EDGE_MS):
    """Cut a chunk's leading and trailing silence (10 ms windows peaking under threshold_db) to margin_ms,
    so the pauses between chunks are exactly the planned ones. Silent or non-16-bit-mono audio is kept."""
    if (channels, width) != (1, 2):
        return pcm
    a = array('h')
    a.frombytes(pcm)
    if sys.byteorder != 'little':
        a.byteswap()
    win, level = max(1, rate // 100), round(32768 * 10 ** (threshold_db / 20))

    def loud(i):
        return max(max(a[i : i + win]), -min(a[i : i + win])) > level

    start = 0
    while start < len(a) and not loud(start):
        start += win
    if start >= len(a):
        return pcm
    end = len(a)
    while end - win > start and not loud(end - win):
        end -= win
    margin = rate * margin_ms // 1000
    return pcm[max(0, start - margin) * 2 : min(len(a), end + margin) * 2]


def read_pcm(path):
    with wave.open(str(path), 'rb') as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.readframes(w.getnframes())


def ffmeta_escape(text):
    return re.sub(r'([=;#\\\n])', r'\\\1', text)


def ffmetadata(tags, chapters_ms):
    lines = [';FFMETADATA1'] + [f'{k}={ffmeta_escape(str(v))}' for k, v in tags.items() if v]
    for title, start, end in chapters_ms:
        lines += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={start}', f'END={end}', f'title={ffmeta_escape(title)}']
    return '\n'.join(lines) + '\n'


def clock(seconds):
    seconds = int(seconds)
    return (
        f'{seconds // 3600}h{seconds % 3600 // 60:02d}m' if seconds >= 3600 else f'{seconds // 60}m{seconds % 60:02d}s'
    )


class Log:
    """Print with elapsed time and append the same lines to build.log."""

    def __init__(self, path):
        self.start = time.perf_counter()
        self.file = path.open('a', encoding='utf-8')
        self.file.write(f'\n=== build {datetime.now():%Y-%m-%d %H:%M:%S} ===\n')

    def __call__(self, message, stamp=True):
        line = f'[{clock(time.perf_counter() - self.start)}] {message}' if stamp else message
        print(line, flush=True)
        self.file.write(line + '\n')
        self.file.flush()


def shard(jobs: list[dict[str, Any]], n: int) -> list[list[dict[str, Any]]]:
    """Split jobs into at most n lists of about equal characters (longest first, to the lightest list)."""
    parts: list[list[dict[str, Any]]] = [[] for _ in range(n)]
    sizes = [0] * n
    for job in sorted(jobs, key=lambda j: -len(j['text'])):
        k = sizes.index(min(sizes))
        parts[k].append(job)
        sizes[k] += len(job['text'])
    return [p for p in parts if p]


def run_workers(engine, jobs, cache, threads, workers, log, backend='gguf'):
    """Synthesize jobs into cache with `workers` processes; True if all succeeded. backend: VieNeu's gguf|onnx.

    With several workers, their per-chunk progress lines are merged into one combined line (at most every
    5 s); other lines are passed through tagged with the worker number. The first worker loads (and on a
    fresh machine downloads) the model before the others start, so they never download at the same time.
    """

    def lines(js):
        return ''.join(json.dumps(j, ensure_ascii=False) + '\n' for j in js)

    def worker_command(path):
        extra = ['--backend', backend] if engine == 'vieneu' else []
        return uv_command(engine, 'worker', engine, str(path), str(cache), '--threads', str(threads), *extra)

    (cache / 'jobs.jsonl').write_text(lines(jobs), encoding='utf-8')  # every job: scan/repair read it
    for old in cache.glob('jobs-*.jsonl'):
        old.unlink()
    shards = shard(jobs, max(1, workers)) if workers > 1 else [jobs]
    if len(shards) == 1:
        command, env = worker_command(cache / 'jobs.jsonl')
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        assert process.stdout is not None  # stdout=PIPE guarantees a readable stream.
        for line in process.stdout:
            log(line.rstrip('\n'), stamp=False)
        return process.wait() == 0
    log(f'      {len(shards)} {engine} workers × {threads} threads')
    sizes = [[len(j['text']) for j in part] for part in shards]
    total = sum(map(sum, sizes))
    lines_q: queue.Queue[tuple[int, str | None]] = queue.Queue()
    procs = []

    def start(k):
        path = cache / f'jobs-{k + 1}.jsonl'
        path.write_text(lines(shards[k]), encoding='utf-8')
        command, env = worker_command(path)
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )
        procs.append(process)

        def pump():
            assert process.stdout is not None
            for line in process.stdout:
                lines_q.put((k, line.rstrip('\n')))
            lines_q.put((k, None))

        threading.Thread(target=pump, daemon=True).start()

    start(0)
    progress = re.compile(rf'\[{engine}\] (\d+)/\d+ \(')
    done, running, started, shown = [0] * len(shards), 1, time.perf_counter(), 0.0
    while running:
        k, worker_line = lines_q.get()
        if worker_line is None:
            running -= 1
            if k == 0 and len(procs) == 1:  # the first worker died before loading: start no others
                break
            continue
        line = worker_line
        if k == 0 and len(procs) == 1 and 'model loaded' in line:
            for other in range(1, len(shards)):
                start(other)
            running += len(shards) - 1
        m = progress.match(line)
        if not m:
            log(re.sub(rf'^\[{engine}\]', f'[{engine} w{k + 1}]', line), stamp=False)
            continue
        done[k] = int(m[1])
        now = time.perf_counter()
        chars = sum(sum(sz[:d]) for sz, d in zip(sizes, done))
        if now - shown >= 5 or chars == total:
            elapsed = now - started
            log(
                f'[{engine}] {sum(done)}/{len(jobs)} ({100 * chars / total:5.1f}%) · {len(procs)} workers · '
                f'elapsed {clock(elapsed)} · ETA {clock(elapsed / chars * (total - chars))}',
                stamp=False,
            )
            shown = now
    return all(p.wait() == 0 for p in procs)


def cmd_build(args):
    from viettts.text import join_kind, split_chunks

    script_path = args.script.resolve()
    script = read_script(script_path.read_text(encoding='utf-8'))
    mix, voices = load_cast(args)
    out = script_path.parent
    log = Log(out / 'build.log')
    mc = voice_for(script.narrator, script.speakers, voices, 'narrator', script.narrator)
    log(
        f'[1/4] Planning {script_path.name} ({mix}{", cast " + args.cast.name if args.cast else ""}); '
        f'MC "{script.narrator}" uses the {mc} voice: ' + ', '.join(f'{k}={voice_label(*v)}' for k, v in voices.items())
    )
    for key in unmatched_cast_keys(voices, script):
        log(
            f'      warning: cast key "{key}" is not a role ({", ".join(ROLES)}) or a speaker in '
            f'{script_path.name}, so it is unused; speakers: {", ".join(script.speakers)}'
        )
    enhanced, problems = check_enhance(script_path, script)
    if problems:
        raise SystemExit(
            'enhance.txt has problems; fix them (run check):\n' + '\n'.join(f'  L{n}: {m}' for n, m in problems)
        )
    chapters = plan_units(script, voices, args.unknown, enhanced=enhanced)
    if args.chapters and args.only:
        raise SystemExit('Use either --chapters N or --only SPEC, not both.')
    if args.chapters:
        chapters = chapters[: args.chapters]
    if args.only:
        picked = parse_chapter_spec(args.only, len(chapters))
        chapters = [chapters[i - 1] for i in picked]
    # Every unit becomes one or more cached chunks (cache/<engine>/<key>.wav); synthesize the missing
    # ones with one worker run per engine.
    jobs: dict[str, dict[str, dict[str, Any]]] = {}
    layout = []
    for title, units in chapters:
        parts = []
        for key, text, pause in units:
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
            parts.append((refs, pause))
        layout.append((title, parts))
    total = sum(len(p[0]) for _, ps in layout for p in ps)
    todo = sum(len(j) for j in jobs.values())
    tagged = sum(1 for _, units in chapters for _, text, _ in units if isinstance(text, TaggedText))
    if enhanced:
        log(f'      enhance.txt: {tagged} Drama-3 lines with tags ({len(enhanced)} entries)')
    log(
        f'      {len(layout)} chapters, {total} chunks; {total - todo} cached, {todo} to synthesize: '
        + (
            ', '.join(f'{e} {len(j)} chunks / {sum(len(x["text"]) for x in j.values())} chars' for e, j in jobs.items())
            or 'nothing'
        )
    )
    started = time.perf_counter()
    if not jobs:
        log('[2/4] Nothing to synthesize; everything is cached')
    for n, engine in enumerate(sorted(jobs, key=lambda e: e != 'vieneu'), 1):  # fast engine first
        cache = out / 'cache' / engine
        cache.mkdir(parents=True, exist_ok=True)
        label = f'{engine} ({args.vieneu_backend})' if engine == 'vieneu' else engine
        log(f'[2/4] Synthesizing with {label} ({n}/{len(jobs)} engines; Ctrl-C is safe, rerun to resume)')
        # Drama-3 needs ~26 GB of unified memory: one worker. VieNeu is latency-bound (more threads don't help),
        # so it runs as several small processes instead, on GGUF as on ONNX.
        workers = args.workers if engine == 'vieneu' else 1
        jobs_list = list(jobs[engine].values())
        if not run_workers(engine, jobs_list, cache, args.threads, workers, log, args.vieneu_backend):
            raise SystemExit(f'{engine} worker failed; finished chunks are cached, rerun build to resume.')
    synth_seconds = time.perf_counter() - started
    # Assemble chapter WAVs (PCM16) with pauses, measuring chapter boundaries.
    log('[3/4] Assembling chapters')
    chapter_dir = out / 'chapters'
    shutil.rmtree(chapter_dir, ignore_errors=True)
    chapter_dir.mkdir()
    first_engine, first_id, _ = layout[0][1][0][0][0]
    rate, channels, width, _ = read_pcm(out / 'cache' / first_engine / f'{first_id}.wav')
    marks, position, files, converted = [], 0, [], 0
    for n, (title, parts) in enumerate(layout, 1):
        path = chapter_dir / f'{n:02d}.wav'
        frames = 0
        with wave.open(str(path), 'wb') as w:
            w.setparams((channels, width, rate, 0, 'NONE', 'not compressed'))
            for refs, pause in parts:
                for engine, cid, join in refs:
                    chunk = out / 'cache' / engine / f'{cid}.wav'
                    r, c, sw, pcm = read_pcm(chunk)
                    if (r, c, sw) != (rate, channels, width):
                        # Engines differ (VieNeu 48 kHz, Drama-3 44.1 kHz): resample once, keep the copy.
                        fixed = chunk.with_name(f'{cid}.{rate}.wav')
                        if not fixed.is_file():
                            subprocess.run(
                                [
                                    'ffmpeg',
                                    '-hide_banner',
                                    '-loglevel',
                                    'error',
                                    '-y',
                                    '-i',
                                    str(chunk),
                                    '-ar',
                                    str(rate),
                                    '-ac',
                                    str(channels),
                                    '-c:a',
                                    f'pcm_s{8 * width}le',
                                    str(fixed),
                                ],
                                check=True,
                            )
                            converted += 1
                        r, c, sw, pcm = read_pcm(fixed)
                    pcm = trim_edges(pcm, rate, channels, width) + b'\0' * round(rate * join / 1000) * channels * width
                    w.writeframes(pcm)
                    frames += len(pcm) // (channels * width)
                silence = round(rate * pause / 1000)
                w.writeframes(b'\0' * silence * channels * width)
                frames += silence
        start = position
        position += frames
        marks.append((title, round(start * 1000 / rate), round(position * 1000 / rate)))
        files.append(path)
        log(
            f'      chapter {n}/{len(layout)}: {frames / rate / 60:5.1f} min  {title}'
            + (f'  ({converted} chunks resampled to {rate} Hz so far)' if converted else '')
        )
    volume = args.volume or source_volume(script.meta.get('source', ''))
    series, title = volume_title(script.meta.get('title') or script_path.parent.name, volume)
    tags = dict(
        title=title,
        artist=args.author or script.meta.get('author', ''),
        album_artist=args.author or '',
        album=args.series or series or title,
        track=volume or '',
        genre='Audiobook',
        comment=script.meta.get('description', ''),
        media_type=2,
    )
    (out / 'chapters.ffmeta').write_text(ffmetadata(tags, marks), encoding='utf-8')
    (out / 'chapters.list').write_text(''.join(f"file '{p}'\n" for p in files), encoding='utf-8')
    cover = (
        None if args.no_cover else (args.cover or (Path(script.meta['cover']) if script.meta.get('cover') else None))
    )
    name = ' '.join(re.sub(r'\s*[\\/:*?"<>|]+\s*', ' - ', tags['title']).split()).strip(' -')
    if args.chapters:  # a pilot build never overwrites the full volume
        name = f'{name} (thử {len(layout)} chương)'
    elif args.only:
        name = f'{name} (thử chương {args.only.replace(" ", "")})'
    m4b = out / f'{name}.m4b'
    encoder = (
        'aac_at'
        if 'aac_at' in subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
        else 'aac'
    )
    command = [
        'ffmpeg',
        '-hide_banner',
        '-loglevel',
        'error',
        '-nostats',
        '-progress',
        'pipe:1',
        '-y',
        '-f',
        'concat',
        '-safe',
        '0',
        '-i',
        str(out / 'chapters.list'),
        '-i',
        str(out / 'chapters.ffmeta'),
    ]
    if cover and cover.is_file():
        command += ['-i', str(cover)]
    command += ['-map', '0:a', '-map_metadata', '1', '-map_chapters', '1']
    if cover and cover.is_file():
        command += [
            '-map',
            '2:v',
            '-c:v',
            'mjpeg',
            '-q:v',
            '3',
            '-vf',
            'scale=min(1400\\,iw):-2',
            '-disposition:v:0',
            'attached_pic',
        ]
    command += [
        '-c:a',
        encoder,
        '-b:a',
        args.bitrate,
        '-ac',
        '1',
        '-movflags',
        '+faststart',
        '-brand',
        'M4B ',
        '-f',
        'ipod',
        str(m4b),
    ]
    log(
        f'[4/4] Encoding {position / rate / 60:.1f} min of audio ({encoder} {args.bitrate}, '
        f'cover: {cover.name if cover and cover.is_file() else "none"})'
    )
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    shown = 0
    assert process.stdout is not None
    for line in process.stdout:
        if line.startswith('out_time_us=') and line.strip()[12:].isdigit():
            percent = int(line.strip()[12:]) / 1e6 / (position / rate) * 100
            if percent >= shown + 20:
                shown = int(percent // 20 * 20)
                log(f'      encoded {shown}%')
    if process.wait():
        raise SystemExit('ffmpeg failed; see the error above.')
    summary = dict(
        script=str(script_path),
        mix=mix,
        voices={k: dict(engine=e, voice=v) for k, (e, v) in voices.items()},
        vieneu_backend=args.vieneu_backend,
        chapters=len(marks),
        chunks_synthesized={e: len(j) for e, j in jobs.items()},
        synthesis_wall_seconds=synth_seconds,
        audio_seconds=position / rate,
        sample_rate=rate,
        encoder=encoder,
        bitrate=args.bitrate,
        cover=str(cover) if cover and cover.is_file() else None,
        output=str(m4b),
        chapter_marks_ms=marks,
    )
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    log(f'Done: {m4b} ({position / rate / 60:.1f} min, {len(marks)} chapters, {m4b.stat().st_size / 1e6:.1f} MB)')


def frame_budget(text):
    """Drama-3 frames (~21.5/s) a take may use before it is rejected as never ending: ~3 per character plus
    room for the pauses that "..." and sentence breaks bring. A larger budget for tagged takes (256 floor,
    ~4 per character) was tried: takes that run past this one ran past 16 s for a 3.5 s line too, so it only
    made each failed attempt slower."""
    pauses = 40 * text.count('...') + 15 * len(re.findall(r'[.!?…]', text))
    return min(600, max(128, len(text) * 3 + pauses))


def cmd_repair(args):
    """Delete cached chunks with long internal silences so the next build regenerates only those."""
    script_path = args.script.resolve()
    cache = script_path.parent / 'cache' / args.engine
    if not cache.is_dir():
        raise SystemExit(f'No {args.engine} cache next to {script_path.name}.')
    if args.fallbacks:  # tagged chunks that were read plain: let the next build retry the tags
        markers = sorted(cache.glob('*.plain'))
        for marker in markers:
            print(f'{marker.stem[:10]}  {marker.read_text(encoding="utf-8").strip()[:70]}')
            if not args.dry_run:
                for stale in [*cache.glob(f'{marker.stem}.wav'), *cache.glob(f'{marker.stem}.*.wav'), marker]:
                    stale.unlink()
        print(f'{len(markers)} chunks read without their tags' + (' deleted.' if markers and not args.dry_run else '.'))
        if markers and not args.dry_run:
            print('Rerun the same build command; only the deleted chunks are synthesized again.')
        return
    command, env = uv_command(
        args.engine,
        'scan',
        str(cache),
        '--max-silence',
        str(args.max_silence),
        *(['--delete'] if not args.dry_run else []),
    )
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    if not args.dry_run:
        print('Rerun the same build command; only the deleted chunks are synthesized again.')


def cmd_scan(args):
    import numpy as np
    import soundfile as sf

    texts = {}
    jobs = args.cache / 'jobs.jsonl'
    if jobs.is_file():
        for line in jobs.read_text(encoding='utf-8').splitlines():
            job = json.loads(line)
            texts[job['id']] = job['text']
    bad = []
    for path in sorted(args.cache.glob('*.wav')):
        samples, rate = sf.read(path, dtype='float32', always_2d=True)
        gap = longest_silence(samples[:, 0], rate, np)
        if gap > args.max_silence:
            bad.append((gap, path))
    for gap, path in sorted(bad, reverse=True):
        print(f'{gap:4.1f}s silence  {path.stem[:10]}  {texts.get(path.stem, "")[:70]}')
        if args.delete:
            path.unlink()
    print(f'{len(bad)} chunks with a pause over {args.max_silence}s' + (' deleted.' if args.delete and bad else '.'))


def cmd_make_ref(args):
    out_dir = ROOT / 'references'
    target = out_dir / f'vieneu-{slugify(args.voice)}.wav'
    text = args.text or REF_SENTENCE
    jobs = out_dir / '.make-ref.jsonl'
    jobs.write_text(
        json.dumps(dict(id=target.stem, text=text, voice=args.voice), ensure_ascii=False) + '\n', encoding='utf-8'
    )
    command, env = uv_command('vieneu', 'worker', 'vieneu', str(jobs), str(out_dir), '--threads', '4')
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    jobs.unlink()
    target.with_suffix('.txt').write_text(text + '\n', encoding='utf-8')
    print(
        f'Reference: {target}\nTranscript: {target.with_suffix(".txt")}\n'
        f'Use it in a Drama-3 cast as "{target.relative_to(ROOT)}".'
    )


def silent_frames(samples, rate, np, floor_db=-50.0):
    hop = max(1, rate // 100)
    usable = samples[: len(samples) // hop * hop]
    if not usable.size:
        return np.zeros(0, dtype=bool), hop
    return np.abs(usable.reshape(-1, hop)).max(axis=1) < 10 ** (floor_db / 20), hop


def longest_silence(samples, rate, np):
    quiet, _ = silent_frames(samples, rate, np)
    best = run = 0
    for q in quiet:
        run = run + 1 if q else 0
        best = max(best, run)
    return best / 100


def squeeze(samples, rate, np, longer_than=0.8, keep=0.5):
    """Shorten pauses inside a chunk; the builder adds the pauses between lines itself."""
    quiet, hop = silent_frames(samples, rate, np)
    keep_frames, pieces, start, i = int(keep * 100), [], 0, 0
    while i < len(quiet):
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < len(quiet) and quiet[j]:
            j += 1
        inside = i > 0 and j < len(quiet)
        if inside and (j - i) / 100 > longer_than:
            pieces.append(samples[start : (i + keep_frames // 2) * hop])
            start = (j - keep_frames // 2) * hop
        i = j
    pieces.append(samples[start:])
    return np.concatenate(pieces)


def level(samples, np, target_db=-20.0, max_gain_db=12.0, peak=0.89):
    """Bring every chunk to the same speech loudness so voices from different references match."""
    voiced = samples[np.abs(samples) > 0.01]
    if voiced.size < 100:
        return samples
    rms_db = 20 * np.log10(np.sqrt(np.mean(voiced**2)))
    gain = 10 ** (max(-max_gain_db, min(max_gain_db, target_db - rms_db)) / 20)
    samples = samples * gain
    top = np.max(np.abs(samples))
    return samples * (peak / top) if top > peak else samples


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
