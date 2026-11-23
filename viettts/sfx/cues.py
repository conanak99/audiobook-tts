"""sfx.txt: sound-effect cues on script lines, placed on the book's timeline.

    # comment
    L9-L14: bed-creak-fast gain=-16      a loop under lines 9..14, pauses between them included
    L12: spank-single at=0.4             a one-shot 0.4 s after line 12 starts
    L30: door-knock-soft at=end          a one-shot as line 30 ends (in the pause after it)

A loop fills its span (from at=<seconds> after the first line starts, at most len=<seconds>), repeated or cut
as needed, with fades. A one-shot plays whole (or len=<seconds> of it) from at=start (default), at=end or
at=<±seconds> from the first line's start; only the chapter's end cuts it. gain is dB against the library
level; the defaults sit loops well under the voice and one-shots a little under it.

A sound with several takes varies by itself: its cues, in book order, take turns through the takes (a loop
also strings its takes together as it repeats). take=<n> pins a cue to take n.

`clear` puts a one-shot in the foreground (L331: squirt-gush at=end clear): it plays in the pause after the
line (at=end) or before it (at=start), and the mix inserts silence there so the next line waits until it is
over. Everything after shifts later, in the SFX book only.
"""

import re
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import library as lib

LOOP_GAIN_DB = -14.0
ONESHOT_GAIN_DB = -8.0
CLEAR_GAIN_DB = -5.0  # a clear one-shot plays alone, nearer the voice's level
SFX_LEVEL_DB = -3.0  # every cue, on top of its gain= or default: the overall SFX level under the voice
MIN_LOOP_S = 0.25
LOOP_FADE_IN_S = 0.3
LOOP_FADE_OUT_S = 0.5
ONESHOT_FADE_OUT_S = 0.05  # only when len= cuts it or the chapter ends first
CLEAR_LEAD_S = 0.15  # a clear one-shot starts this far into its pause ...
CLEAR_TAIL_S = 0.25  # ... and the next line waits this long after it ends
TITLE_PAUSE_S = 1.2  # the pause after a chapter's title, before its first line (layout.PAUSES_MS['title'])

CUE_RE = re.compile(r'^L(\d+)(?:\s*-\s*L?(\d+))?\s*:\s*(\S+)(.*)$')
OPTION_RE = re.compile(r'^(gain|at|len|take)=(\S+)$')


@dataclass
class Cue:
    row: int  # line in sfx.txt
    first: int
    last: int
    sound: str
    options: dict[str, str] = field(default_factory=dict)


def cues_path(script_path: Path) -> Path:
    return script_path.parent / 'sfx.txt'


def read_cues(text: str) -> tuple[list[Cue], list[tuple[int, str]]]:
    cues, problems = [], []
    for row, raw in enumerate(text.splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        m = CUE_RE.match(line)
        if not m:
            problems.append((row, f'not a cue: "{raw.strip()}" (expected "L12: sound-id" or "L9-L14: sound-id")'))
            continue
        first, last = int(m.group(1)), int(m.group(2) or m.group(1))
        options: dict[str, str] = {}
        for token in m.group(4).split():
            if token == 'clear':
                options['clear'] = ''
                continue
            o = OPTION_RE.match(token)
            if not o:
                problems.append(
                    (
                        row,
                        f'unknown option "{token}" (gain=<dB>, at=start|end|<seconds>, len=<seconds>, take=<n>, clear)',
                    )
                )
                continue
            options[o.group(1)] = o.group(2)
        cues.append(Cue(row, first, last, m.group(3), options))
    return cues, problems


def number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def clip_seconds(path: Path) -> float:
    with wave.open(str(path), 'rb') as w:
        return w.getnframes() / w.getframerate()


def place(
    cues: list[Cue], timeline: dict[str, Any], library: dict[str, Any], root: Path = lib.LIBRARY_DIR
) -> tuple[list[dict[str, Any]], list[tuple[int, str]]]:
    """Cues -> placements {row, chapter, sound, take, files, kind, start_s, seconds, gain_db, fade_in_s,
    fade_out_s, insert} in seconds from the start of the chapter in the SFX book, and problems (sfx.txt row,
    message). files: the one-shot's take, or a loop's takes in the order it plays them. insert: for a clear
    cue, [where, how long] in the voice-only chapter the mix inserts silence, else None."""
    lines = {item['line']: item for item in timeline['lines']}
    ordered = sorted(timeline['lines'], key=lambda i: (i['chapter'], i['start_ms']))
    previous = {b['line']: a for a, b in zip(ordered, ordered[1:]) if a['chapter'] == b['chapter']}
    durations = {c['chapter']: c['duration_ms'] / 1000 for c in timeline['chapters']}
    known = lib.sounds(library)
    placed, problems = [], []
    for cue in cues:
        missing = [n for n in (cue.first, cue.last) if n not in lines]
        if missing:
            problems.append((cue.row, f'L{missing[0]} is not a spoken line of script.txt'))
            continue
        a, b = lines[cue.first], lines[cue.last]
        if cue.last < cue.first:
            problems.append((cue.row, f'L{cue.first}-L{cue.last}: the span runs backwards'))
            continue
        if a['chapter'] != b['chapter']:
            problems.append((cue.row, f'L{cue.first}-L{cue.last} crosses chapters {a["chapter"]} and {b["chapter"]}'))
            continue
        sound = known.get(cue.sound)
        if not sound:
            problems.append((cue.row, f'"{cue.sound}" is not in the library (viettts sfx list; add it with sfx add)'))
            continue
        files = lib.sound_files(sound, root)
        if not files:
            problems.append((cue.row, f'"{cue.sound}" is listed but not rendered yet (viettts sfx generate)'))
            continue
        pinned = None
        if 'take' in cue.options:
            pinned = int(cue.options['take']) if cue.options['take'].isdigit() else 0
            if not 1 <= pinned <= len(files):
                problems.append((cue.row, f'take must be 1..{len(files)} for "{cue.sound}"'))
                continue
        gain = number(cue.options.get('gain', '')) if 'gain' in cue.options else None
        if 'gain' in cue.options and (gain is None or not -40 <= gain <= 12):
            problems.append((cue.row, 'gain must be a number of dB between -40 and 12'))
            continue
        length = number(cue.options['len']) if 'len' in cue.options else None
        if 'len' in cue.options and (length is None or length <= 0):
            problems.append((cue.row, 'len must be a positive number of seconds'))
            continue
        span_start, span_end = a['start_ms'] / 1000, b['end_ms'] / 1000
        at = cue.options.get('at', 'start')
        offset = number(at)
        chapter_end = durations[a['chapter']]
        gap = None  # a clear cue's pause: (start, length) in the voice-only chapter
        if 'clear' in cue.options:
            if sound['kind'] != 'oneshot' or at not in ('start', 'end'):
                problems.append((cue.row, 'clear is for a one-shot at=start or at=end (a pause between lines)'))
                continue
            if at == 'end':
                gap = (span_end, b['pause_ms'] / 1000)
            else:
                before = previous.get(cue.first)
                pause = before['pause_ms'] / 1000 if before else min(TITLE_PAUSE_S, span_start)
                gap = (span_start - pause, pause)
        if sound['kind'] == 'loop':
            if offset is None and at != 'start':
                problems.append((cue.row, f'a loop starts at=start or at=<seconds>, not at={at}'))
                continue
            start = span_start + (offset or 0)
            seconds = span_end - start if length is None else min(length, span_end - start)
            if seconds < MIN_LOOP_S:
                problems.append((cue.row, f'the loop would last {seconds:.2f} s; start it earlier or span more lines'))
                continue
            fade_in, fade_out = min(LOOP_FADE_IN_S, seconds / 4), min(LOOP_FADE_OUT_S, seconds / 3)
        else:
            if gap:
                start = gap[0] + min(CLEAR_LEAD_S, gap[1] / 2)
            elif at == 'start':
                start = span_start
            elif at == 'end':
                start = span_end
            elif offset is not None:
                start = span_start + offset
            else:
                problems.append((cue.row, f'at must be start, end or a number of seconds, not {at}'))
                continue
            seconds = length or 0.0  # set from the take it gets, in rotate()
            fade_in, fade_out = 0.0, 0.0
        if not 0 <= start < chapter_end:
            problems.append((cue.row, f'it would start at {start:.2f} s, outside chapter {a["chapter"]}'))
            continue
        if sound['kind'] == 'loop' and start + seconds > chapter_end:
            seconds, fade_out = chapter_end - start, min(fade_out, (chapter_end - start) / 3)
        default_gain = LOOP_GAIN_DB if sound['kind'] == 'loop' else CLEAR_GAIN_DB if gap else ONESHOT_GAIN_DB
        placed.append(
            dict(
                row=cue.row,
                chapter=a['chapter'],
                sound=cue.sound,
                take=pinned,
                files=[str(f) for f in files],
                kind=sound['kind'],
                start_s=round(start, 3),
                seconds=round(seconds, 3),
                gain_db=(default_gain if gain is None else gain) + SFX_LEVEL_DB,
                fade_in_s=round(fade_in, 3),
                fade_out_s=round(fade_out, 3),
                room_s=float('inf') if gap else round(chapter_end - start, 3),  # clear: the chapter grows
                gap=gap,
                insert=None,
            )
        )
    placed = rotate(placed)
    return make_room(placed, problems), problems


def rotate(placed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give each unpinned cue the next take of its sound in book order; a one-shot keeps only that take (and
    at most its length), a loop starts there and cycles through the rest."""
    turn: dict[str, int] = {}
    for p in sorted(placed, key=lambda p: (p['chapter'], p['start_s'], p['row'])):
        files = p['files']
        if p['take'] is None:
            p['take'] = turn.get(p['sound'], 0) % len(files) + 1
            turn[p['sound']] = turn.get(p['sound'], 0) + 1
        k = p['take'] - 1
        if p['kind'] == 'loop':
            p['files'] = files[k:] + files[:k]
        else:
            # A one-shot plays its whole take (takes differ in length), unless len= or the chapter's end cuts it.
            p['files'] = [files[k]]
            own = clip_seconds(Path(files[k]))
            seconds = min(own, p['seconds'] or own, p['room_s'])
            p['seconds'] = round(seconds, 3)
            if seconds < own:
                p['fade_out_s'] = min(ONESHOT_FADE_OUT_S, seconds / 3)
    for p in placed:
        del p['room_s']
    return placed


def make_room(placed: list[dict[str, Any]], problems: list[tuple[int, str]]) -> list[dict[str, Any]]:
    """Insert the silence clear cues need (late in their pause, so the next line moves) and shift every
    placement after it. A loop running across an insertion stretches over it."""
    inserts: dict[int, list[tuple[float, float]]] = {}
    used: dict[tuple[int, float], int] = {}
    for p in sorted(placed, key=lambda p: (p['chapter'], p['start_s'], p['row'])):
        gap = p.pop('gap')
        if not gap:
            continue
        # Silence goes in late in the pause (any point in it sounds the same): after the cue's own start, and
        # clear of the ms rounding between one line's end + pause and the next line's start.
        at = round(gap[0] + gap[1] * 0.75, 3)
        if (p['chapter'], at) in used:
            problems.append((p['row'], f'the pause already holds a clear cue (sfx.txt:{used[p["chapter"], at]})'))
            continue
        used[p['chapter'], at] = p['row']
        extra = round(max(0.0, (p['start_s'] - gap[0]) + p['seconds'] + CLEAR_TAIL_S - gap[1]), 3)
        p['insert'] = [at, extra]
        inserts.setdefault(p['chapter'], []).append((at, extra))

    def shifted(chapter, t):
        # Anything at or after an insertion point moves past it (the next line, cues on it, loops over it).
        return t + sum(extra for at, extra in inserts.get(chapter, []) if at <= t + 1e-9)

    for p in placed:
        end = p['start_s'] + p['seconds']
        if p['insert']:  # it sits in its pause, before its own insertion: only earlier insertions move it
            ins_at = p['insert'][0]
            p['start_s'] = round(p['start_s'] + sum(e for a, e in inserts[p['chapter']] if a < ins_at - 1e-9), 3)
            continue
        start = shifted(p['chapter'], p['start_s'])
        if p['kind'] == 'loop':
            p['seconds'] = round(shifted(p['chapter'], end) - start, 3)
        p['start_s'] = round(start, 3)
    return placed


def shift_time(placed: list[dict[str, Any]], chapter: int, t: float) -> float:
    """A time in the voice-only chapter -> the same moment in the SFX chapter."""
    return t + sum(p['insert'][1] for p in placed if p['insert'] and p['chapter'] == chapter and p['insert'][0] <= t)
