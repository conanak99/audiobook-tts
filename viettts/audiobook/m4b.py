"""The book file: volume and title tags, ffmetadata chapter marks, and AAC/M4B encoding for BookPlayer."""

import re
import subprocess
import tempfile
from pathlib import Path


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


def file_name(title):
    """A title as a file name: path characters become " - "."""
    return ' '.join(re.sub(r'\s*[\\/:*?"<>|]+\s*', ' - ', title).split()).strip(' -')


def ffmeta_escape(text):
    return re.sub(r'([=;#\\\n])', r'\\\1', text)


def ffmetadata(tags, chapters_ms):
    lines = [';FFMETADATA1'] + [f'{k}={ffmeta_escape(str(v))}' for k, v in tags.items() if v]
    for title, start, end in chapters_ms:
        lines += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={start}', f'END={end}', f'title={ffmeta_escape(title)}']
    return '\n'.join(lines) + '\n'


def write_listing(path: Path, wavs) -> Path:
    """An ffmpeg concat list of the chapter WAVs."""
    path.write_text(''.join(f"file '{p}'\n" for p in wavs), encoding='utf-8')
    return path


def book_cover(book: Path, picture: Path) -> Path | None:
    """The attached picture of an .m4b/.m4a written to picture (None if the book has no cover)."""
    result = subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(book), '-map', '0:v:0?', '-c', 'copy']
        + ['-frames:v', '1', str(picture)],
        capture_output=True,
        text=True,
    )
    return picture if result.returncode == 0 and picture.is_file() and picture.stat().st_size else None


class M4bEncoder:
    """Chapter WAVs (an ffmpeg concat list) -> mono AAC in an .m4b (or a plain .m4a preview).

    Tags and chapter marks come from an ffmetadata file. The cover is an image, re-encoded as JPEG at most
    1400 px wide, or another .m4b/.m4a whose attached picture is used (the SFX mix reuses the book's). That
    picture is extracted to a JPEG first: mapping it straight from the .m4b made ffmpeg write the chapter marks
    in a 1/4410000 timebase that overflows after ~8 minutes (zero-length and repeated chapters)."""

    def __init__(self, bitrate='64k'):
        self.bitrate = bitrate
        encoders = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
        self.codec = 'aac_at' if 'aac_at' in encoders else 'aac'

    def command(self, listing: Path, target: Path, ffmeta: Path | None = None, cover: Path | None = None):
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostats', '-progress', 'pipe:1', '-y']
        command += ['-f', 'concat', '-safe', '0', '-i', str(listing)]
        inputs = 1
        if ffmeta:
            command += ['-i', str(ffmeta)]
            meta, inputs = inputs, inputs + 1
        if cover:
            command += ['-i', str(cover)]
        command += ['-map', '0:a']
        if ffmeta:
            command += ['-map_metadata', str(meta), '-map_chapters', str(meta)]
        if cover:
            command += ['-map', f'{inputs}:v', '-c:v', 'mjpeg', '-q:v', '3', '-vf', 'scale=min(1400\\,iw):-2']
            command += ['-disposition:v:0', 'attached_pic']
        command += ['-c:a', self.codec, '-b:a', self.bitrate, '-ac', '1', '-movflags', '+faststart']
        if target.suffix.lower() == '.m4b':
            command += ['-brand', 'M4B ']
        return [*command, '-f', 'ipod', str(target)]

    def encode(self, listing, target, ffmeta=None, cover=None, seconds=None, log=None):
        """Encode; with the audio's length in seconds and a log, report progress every 20%."""
        if cover and Path(cover).suffix.lower() in ('.m4b', '.m4a'):
            with tempfile.TemporaryDirectory() as scratch:
                picture = book_cover(Path(cover), Path(scratch) / 'cover.jpg')
                return self.encode(listing, target, ffmeta, picture, seconds, log)
        process = subprocess.Popen(self.command(listing, target, ffmeta, cover), stdout=subprocess.PIPE, text=True)
        shown = 0
        assert process.stdout is not None
        for line in process.stdout:
            if log and seconds and line.startswith('out_time_us=') and line.strip()[12:].isdigit():
                percent = int(line.strip()[12:]) / 1e6 / seconds * 100
                if percent >= shown + 20:
                    shown = int(percent // 20 * 20)
                    log(f'      encoded {shown}%')
        if process.wait():
            raise SystemExit('ffmpeg failed; see the error above.')
        return target
