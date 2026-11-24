"""Cue planning and subtitle files; standard library only, shared by the CLI and the engine worker."""

import re

MERGE_GAP = 0.25  # VAD spans closer than this are one line
MAX_CUE = 12.0  # stop merging past this; anime-whisper is trained on short clips
MAX_CLIP = 28.0  # hard cap per clip, inside whisper's 30 s window
CLIP_PAD = 0.2  # audio kept around a diarized turn when re-transcribing it

_BLANK = re.compile(r'^[\s…・.。、,，!！?？~〜ー―-]*$')
_LOOP = re.compile(r'(.{1,4}?)\1{7,}')


def merge_spans(spans: list[tuple[float, float]], gap: float = MERGE_GAP, longest: float = MAX_CUE):
    """Join speech spans split by short breaths, keeping each line short enough to transcribe well."""
    merged: list[list[float]] = []
    for start, end in sorted(spans):
        if merged and start - merged[-1][1] < gap and end - merged[-1][0] <= longest:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def split_long(spans: list[tuple[float, float]], longest: float = MAX_CLIP):
    """Cut any span longer than `longest` into equal parts (rare: one breathless VAD span)."""
    out: list[tuple[float, float]] = []
    for start, end in spans:
        parts = max(1, int((end - start) // longest) + (1 if (end - start) % longest else 0))
        step = (end - start) / parts
        out.extend((start + i * step, start + (i + 1) * step) for i in range(parts))
    return out


def is_blank(text: str) -> bool:
    """Only ellipses and punctuation: the model heard breath or noise, not a line. Moans like ふふっ stay."""
    return bool(_BLANK.match(text))


def is_loop(text: str) -> bool:
    """A short piece repeated 8+ times in a row: the decoder got stuck, so retry or fall back."""
    return bool(_LOOP.search(text))


def label_speakers(labels: list[str | None]) -> list[str | None]:
    """Rename diarization labels to S1, S2 … in order of first appearance."""
    names: dict[str, str] = {}
    out: list[str | None] = []
    for label in labels:
        if label is None:
            out.append(None)
            continue
        names.setdefault(label, f'S{len(names) + 1}')
        out.append(names[label])
    return out


def timestamp(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}'


def vtt_cues(cues: list[dict]) -> str:
    """Numbered cue blocks; a speaker becomes a standard WebVTT voice span (<v S1>)."""
    blocks = []
    for i, cue in enumerate(cues, 1):
        text = cue['text'].replace('\n', ' ')
        if cue.get('speaker'):
            text = f'<v {cue["speaker"]}>{text}</v>'
        blocks.append(f'{i}\n{timestamp(cue["start"])} --> {timestamp(cue["end"])}\n{text}\n')
    return '\n'.join(blocks)


def vtt(cues: list[dict]) -> str:
    return 'WEBVTT\n\n' + vtt_cues(cues)


_TRACK_PREFIX = re.compile(r'^\s*(?:track|tr|#)?\s*\d+\s*[._\-:)\]]*\s*', re.IGNORECASE)


def chapter_title(file_stem: str) -> str:
    """The chapter name from a file name, without its track number (translate numbers chapters itself)."""
    return _TRACK_PREFIX.sub('', file_stem, count=1).strip() or file_stem


def source_md(tracks: list[tuple[str, list[dict]]]) -> str:
    """All tracks in one file, each under `## <title>`, in the translate skill's input format."""
    return '\n'.join(f'## {title}\n\nWEBVTT\n\n{vtt_cues(cues)}' for title, cues in tracks)
