"""Drama-3 performance tags in a line's text: [directions], [sounds] and paired <whisper>…</whisper> tags.

enhance.txt next to script.txt holds "L<n>: <line with tags>" for Drama-3 lines; script.txt stays plain
(.opencode/skills/audiobook/references/enhance.md).
"""

import re


def spoken(text):
    """Text as sent to TTS: drop quote marks and decorations the engines would read or choke on."""
    text = re.sub(r'["«»“”~*_]', '', text)
    return ' '.join(text.split())


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
