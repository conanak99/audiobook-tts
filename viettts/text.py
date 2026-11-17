"""Shared text normalization and lossless, sentence-first chunking."""

import html
import re
import unicodedata
from collections.abc import Callable


def slugify(text: str) -> str:
    text = unicodedata.normalize('NFKD', text.replace('đ', 'd').replace('Đ', 'D'))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-').lower()[:60] or 'audiobook'


def plain_text(markdown: str) -> str:
    """Extract narration from ordinary Markdown, omitting images and code blocks."""
    text = re.sub(r'(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', markdown)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    text = re.sub(r'!\[[^\]]*\]\([^\n]*?\)|!\[[^\]]*\]\[[^\]]*\]', '', text)
    text = re.sub(r'(?m)^\s*\[[^\]]+\]:.*$', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\n]*?\)|\[([^\]]+)\]\[[^\]]*\]', lambda m: m[1] or m[2], text)
    text = re.sub(r'<https?://[^>]+>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    lines = []
    for line in text.splitlines():
        if re.fullmatch(r'\s*(?:[-*_]\s*){3,}|\s*[=-]{2,}\s*', line):
            continue
        line = re.sub(r'^\s*(?:>\s*)+', '', line)
        line = re.sub(r'^\s{0,3}#{1,6}\s+|\s+#+\s*$', '', line)
        line = re.sub(r'^\s*(?:[-+*]|\d+[.)])\s+(?:\[[ xX]\]\s*)?', '', line)
        line = re.sub(r'[*_`~]', '', line)
        lines.append(html.unescape(line).strip())
    paragraphs = re.split(r'\n\s*\n', '\n'.join(lines))
    return '\n\n'.join(' '.join(p.split()) for p in paragraphs if p.strip())


SENTENCE_END = re.compile(r'[.!?…]["”’\')\]]*$')
CLAUSE_END = re.compile(r'[,;:—–]$')


def join_kind(chunk: str) -> str:
    """Classify a join as a sentence, clause, or word boundary."""
    return 'sentence' if SENTENCE_END.search(chunk) else 'clause' if CLAUSE_END.search(chunk) else 'word'


def split_chunks(
    text: str,
    max_chars: int = 225,
    token_count: Callable[[str], int] | None = None,
    max_tokens: int = 512,
    max_bytes: int | None = None,
) -> list[str]:
    """One sentence per chunk, without loss; split long sentences at balanced clause boundaries."""

    def fits(s: str) -> bool:
        return (
            len(s) <= max_chars
            and (max_bytes is None or len(s.encode('utf-8')) <= max_bytes)
            and (token_count is None or token_count(s) <= max_tokens)
        )

    chunks: list[str] = []
    for paragraph in text.split('\n'):
        sentences = re.split(r'(?<=[.!?…])(?=[\s”’\"\'])', paragraph.strip())
        fixed: list[str] = []
        for sentence in sentences:
            match = re.match(r'^([”’\"\']+)(?:\s+|$)', sentence)
            if match and fixed:
                fixed[-1] += match[1]
                sentence = sentence[match.end() :]
            if sentence.strip():
                fixed.append(sentence.strip())
        for sentence in fixed:
            chunks.extend([sentence] if fits(sentence) else _split_long(sentence, fits))
    return chunks


def _split_long(sentence: str, fits: Callable[[str], bool]) -> list[str]:
    # Atoms are clauses; oversized clauses become words (or character pieces).
    # soft[i] marks a word boundary, less desirable than a clause boundary.
    atoms, soft = [], []
    for clause in re.split(r'(?<=[,;:—–])\s+', sentence):
        if fits(clause):
            atoms.append(clause)
            soft.append(False)
            continue
        for word in clause.split():
            while not fits(word):
                end = len(word)
                while end and not fits(word[:end]):
                    end -= 1
                if not end:
                    raise ValueError('A single character exceeds the token budget.')
                atoms.append(word[:end])
                soft.append(True)
                word = word[end:]
            atoms.append(word)
            soft.append(True)
        soft[-1] = False
    # Prefer fewest word cuts, then fewest chunks, then shortest longest chunk.
    best: list[tuple[int, int, int, int] | None] = [(0, 0, 0, 0)] + [None] * len(atoms)
    for end in range(1, len(atoms) + 1):
        for start in range(end - 1, -1, -1):
            piece = ' '.join(atoms[start:end])
            if not fits(piece):
                break
            previous = best[start]
            if previous is None:
                continue
            cuts, count, longest, _ = previous
            score = (cuts + (start > 0 and soft[start - 1]), count + 1, max(longest, len(piece)), start)
            current = best[end]
            if current is None or score[:3] < current[:3]:
                best[end] = score
    pieces, end = [], len(atoms)
    while end:
        chosen = best[end]
        assert chosen is not None  # Every atom fits, so there is a path to this endpoint.
        start = chosen[3]
        pieces.append(' '.join(atoms[start:end]))
        end = start
    return pieces[::-1]
