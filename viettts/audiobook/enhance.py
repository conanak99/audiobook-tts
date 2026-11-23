"""enhance.txt: the agent's tagged versions of script lines, matched back to the script and checked."""

import re
from collections import defaultdict

from .layout import MAX_BYTES, MAX_CHARS
from .tags import split_tagged, spoken, tag_problems, untagged


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
