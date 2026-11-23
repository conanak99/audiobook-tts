"""Join a layout's cached chunks into chapter WAVs with their pauses, and time every script line on the way."""

import json
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audio import read_pcm, trim_edges


@dataclass
class Assembly:
    """What assembling measured: the sample rate, each chapter's (title, frames), and every script line's
    {line, chapter, start, end, pause} in frames: start and end from the start of its chapter, then the
    silence after it."""

    rate: int
    chapters: list[tuple[str, int]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)

    @property
    def frames(self) -> int:
        return sum(frames for _, frames in self.chapters)

    def ms(self, frames: int) -> int:
        return round(frames * 1000 / self.rate)

    def offsets(self) -> list[int]:
        """Each chapter's first frame in the whole book."""
        starts, position = [], 0
        for _, frames in self.chapters:
            starts.append(position)
            position += frames
        return starts

    def marks(self) -> list[tuple[str, int, int]]:
        """(title, start_ms, end_ms) per chapter, for ffmetadata."""
        return [
            (title, self.ms(start), self.ms(start + frames))
            for (title, frames), start in zip(self.chapters, self.offsets())
        ]

    def timeline(self, script, enhanced=None) -> dict[str, Any]:
        """Each chapter's length and each line's start/end and the pause after it, in ms from the start of
        its chapter (book_start_ms: of the book), with its enhance.txt tags if any (viettts sfx uses it)."""
        enhanced = enhanced or {}
        offsets = self.offsets()
        texts = {line.number: (line.speaker, line.text) for _, ps in script.chapters for p in ps for line in p}
        return dict(
            sample_rate=self.rate,
            chapters=[
                dict(chapter=n, title=title, start_ms=self.ms(offsets[n - 1]), duration_ms=self.ms(frames))
                for n, (title, frames) in enumerate(self.chapters, 1)
            ],
            lines=[
                dict(
                    line=item['line'],
                    chapter=item['chapter'],
                    speaker=texts[item['line']][0],
                    text=texts[item['line']][1],
                    **({'tagged': enhanced[item['line']]} if item['line'] in enhanced else {}),
                    start_ms=self.ms(item['start']),
                    end_ms=self.ms(item['end']),
                    pause_ms=self.ms(item['pause']),
                    book_start_ms=self.ms(offsets[item['chapter'] - 1] + item['start']),
                )
                for item in self.lines
            ],
        )

    def write_timeline(self, out: Path, script, enhanced=None) -> dict[str, Any]:
        """timeline.json beside the script; returns it."""
        timeline = self.timeline(script, enhanced)
        (out / 'timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding='utf-8')
        return timeline


class Assembler:
    """Reads the chunks a layout names from out/cache/<engine>/ and lays them out with their pauses.

    run() writes chapter_dir/NN.wav (PCM16) when given a directory, else only measures, so the timeline of
    an already built book comes from the very same arithmetic as its chapters."""

    def __init__(self, out: Path):
        self.out = out
        self.converted = 0  # chunks resampled to the book's rate so far

    def chunk_pcm(self, engine, cid, rate, channels, width):
        """A cached chunk as trimmed PCM in the book's format. A chunk in another format (VieNeu 48 kHz,
        Drama-3 44.1 kHz) is resampled once and the copy kept beside it."""
        chunk = self.out / 'cache' / engine / f'{cid}.wav'
        r, c, sw, pcm = read_pcm(chunk)
        if (r, c, sw) != (rate, channels, width):
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
                self.converted += 1
            r, c, sw, pcm = read_pcm(fixed)
        return trim_edges(pcm, rate, channels, width)

    def run(self, layout, chapter_dir: Path | None = None, on_chapter=None) -> Assembly:
        """on_chapter(n, title, frames, assembly) is called after each chapter."""
        first_engine, first_id, _ = layout[0][1][0][0][0]
        rate, channels, width, _ = read_pcm(self.out / 'cache' / first_engine / f'{first_id}.wav')
        assembly = Assembly(rate)
        for n, (title, parts) in enumerate(layout, 1):
            writer = None
            if chapter_dir is not None:
                writer = wave.open(str(chapter_dir / f'{n:02d}.wav'), 'wb')
                writer.setparams((channels, width, rate, 0, 'NONE', 'not compressed'))
            frames = 0
            try:
                for refs, pause, number in parts:
                    start = frames
                    for engine, cid, join in refs:
                        pcm = self.chunk_pcm(engine, cid, rate, channels, width)
                        pcm += b'\0' * round(rate * join / 1000) * channels * width
                        if writer:
                            writer.writeframes(pcm)
                        frames += len(pcm) // (channels * width)
                    silence = round(rate * pause / 1000)
                    if number is not None:
                        assembly.lines.append(dict(line=number, chapter=n, start=start, end=frames, pause=silence))
                    if writer:
                        writer.writeframes(b'\0' * silence * channels * width)
                    frames += silence
            finally:
                if writer:
                    writer.close()
            assembly.chapters.append((title, frames))
            if on_chapter:
                on_chapter(n, title, frames, assembly)
        return assembly
