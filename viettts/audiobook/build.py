"""audiobook build: script.txt -> cached chunks -> chapter WAVs -> <Title>.m4b, logged to build.log."""

import json
import re
import shutil
import time
from pathlib import Path

from .assembly import Assembler, Assembly
from .cast import ROLES, load_cast, unmatched_cast_keys, voice_for, voice_label
from .enhance import check_enhance
from .layout import plan_layout, plan_units
from .m4b import M4bEncoder, ffmetadata, file_name, source_volume, volume_title, write_listing
from .script import read_script
from .tags import TaggedText
from .workers import Log, WorkerPool


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


class BookBuild:
    """One build run. Every step logs to build.log; a failed or interrupted run resumes from the cache."""

    def __init__(self, args):
        if args.chapters and args.only:
            raise SystemExit('Use either --chapters N or --only SPEC, not both.')
        self.args = args
        self.script_path = args.script.resolve()
        self.out = self.script_path.parent
        self.script = read_script(self.script_path.read_text(encoding='utf-8'))
        self.mix, self.voices = load_cast(args.cast)
        self.log = Log(self.out / 'build.log')
        self.pilot = bool(args.chapters or args.only)  # a pilot never replaces the full volume or its timeline

    def run(self):
        self.plan()
        synth_seconds = self.synthesize()
        assembly = self.assemble()
        m4b, cover = self.encode(assembly)
        self.summarize(assembly, m4b, cover, synth_seconds)

    def plan(self):
        """[1/4] Cast, enhance.txt and chapter units -> self.layout of cached chunks and self.jobs to make."""
        args, script, voices, log = self.args, self.script, self.voices, self.log
        mc = voice_for(script.narrator, script.speakers, voices, 'narrator', script.narrator)
        log(
            f'[1/4] Planning {self.script_path.name} ({self.mix}{", cast " + args.cast.name if args.cast else ""}); '
            f'MC "{script.narrator}" uses the {mc} voice: '
            + ', '.join(f'{k}={voice_label(*v)}' for k, v in voices.items())
        )
        for key in unmatched_cast_keys(voices, script):
            log(
                f'      warning: cast key "{key}" is not a role ({", ".join(ROLES)}) or a speaker in '
                f'{self.script_path.name}, so it is unused; speakers: {", ".join(script.speakers)}'
            )
        self.enhanced, problems = check_enhance(self.script_path, script)
        if problems:
            raise SystemExit(
                'enhance.txt has problems; fix them (run check):\n' + '\n'.join(f'  L{n}: {m}' for n, m in problems)
            )
        chapters = plan_units(script, voices, args.unknown, enhanced=self.enhanced)
        if args.chapters:
            chapters = chapters[: args.chapters]
        if args.only:
            chapters = [chapters[i - 1] for i in parse_chapter_spec(args.only, len(chapters))]
        # Every unit becomes one or more cached chunks (cache/<engine>/<key>.wav).
        self.layout, self.jobs = plan_layout(self.out, chapters, voices)
        total = sum(len(p[0]) for _, ps in self.layout for p in ps)
        todo = sum(len(j) for j in self.jobs.values())
        if self.enhanced:
            tagged = sum(1 for _, units in chapters for _, text, _, _ in units if isinstance(text, TaggedText))
            log(f'      enhance.txt: {tagged} Drama-3 lines with tags ({len(self.enhanced)} entries)')
        log(
            f'      {len(self.layout)} chapters, {total} chunks; {total - todo} cached, {todo} to synthesize: '
            + (
                ', '.join(
                    f'{e} {len(j)} chunks / {sum(len(x["text"]) for x in j.values())} chars'
                    for e, j in self.jobs.items()
                )
                or 'nothing'
            )
        )

    def synthesize(self) -> float:
        """[2/4] One worker run per engine for the missing chunks, the fast engine first. Returns seconds."""
        args, started = self.args, time.perf_counter()
        if not self.jobs:
            self.log('[2/4] Nothing to synthesize; everything is cached')
        for n, engine in enumerate(sorted(self.jobs, key=lambda e: e != 'vieneu'), 1):
            cache = self.out / 'cache' / engine
            cache.mkdir(parents=True, exist_ok=True)
            label = f'{engine} ({args.vieneu_backend})' if engine == 'vieneu' else engine
            self.log(f'[2/4] Synthesizing with {label} ({n}/{len(self.jobs)} engines; Ctrl-C is safe, rerun to resume)')
            # Drama-3 needs ~26 GB of unified memory: one worker. VieNeu is latency-bound (more threads don't
            # help), so it runs as several small processes instead, on GGUF as on ONNX.
            workers = args.workers if engine == 'vieneu' else 1
            pool = WorkerPool(engine, cache, args.threads, workers, self.log, args.vieneu_backend)
            if not pool.run(list(self.jobs[engine].values())):
                raise SystemExit(f'{engine} worker failed; finished chunks are cached, rerun build to resume.')
        return time.perf_counter() - started

    def assemble(self) -> Assembly:
        """[3/4] chapters/NN.wav with their pauses, and timeline.json for a full build."""
        self.log('[3/4] Assembling chapters')
        chapter_dir = self.out / 'chapters'
        shutil.rmtree(chapter_dir, ignore_errors=True)
        chapter_dir.mkdir()
        assembler = Assembler(self.out)

        def chapter_done(n, title, frames, assembly):
            converted = assembler.converted
            self.log(
                f'      chapter {n}/{len(self.layout)}: {frames / assembly.rate / 60:5.1f} min  {title}'
                + (f'  ({converted} chunks resampled to {assembly.rate} Hz so far)' if converted else '')
            )

        assembly = assembler.run(self.layout, chapter_dir, chapter_done)
        if not self.pilot:  # line numbers and chapter indexes are those of the whole book
            assembly.write_timeline(self.out, self.script, self.enhanced)
        return assembly

    def tags(self):
        args, meta = self.args, self.script.meta
        volume = args.volume or source_volume(meta.get('source', ''))
        series, title = volume_title(meta.get('title') or self.out.name, volume)
        return dict(
            title=title,
            artist=args.author or meta.get('author', ''),
            album_artist=args.author or '',
            album=args.series or series or title,
            track=volume or '',
            genre='Audiobook',
            comment=meta.get('description', ''),
            media_type=2,
        )

    def cover(self):
        args, meta = self.args, self.script.meta
        cover = None if args.no_cover else (args.cover or (Path(meta['cover']) if meta.get('cover') else None))
        return cover if cover and cover.is_file() else None

    def target(self, title):
        name = file_name(title)
        if self.args.chapters:
            name = f'{name} (thử {len(self.layout)} chương)'
        elif self.args.only:
            name = f'{name} (thử chương {self.args.only.replace(" ", "")})'
        return self.out / f'{name}.m4b'

    def encode(self, assembly: Assembly):
        """[4/4] chapters.ffmeta + chapters.list + cover -> the .m4b."""
        tags = self.tags()
        ffmeta = self.out / 'chapters.ffmeta'
        ffmeta.write_text(ffmetadata(tags, assembly.marks()), encoding='utf-8')
        files = [self.out / 'chapters' / f'{n:02d}.wav' for n in range(1, len(assembly.chapters) + 1)]
        listing = write_listing(self.out / 'chapters.list', files)
        cover, m4b = self.cover(), self.target(tags['title'])
        encoder = M4bEncoder(self.args.bitrate)
        seconds = assembly.frames / assembly.rate
        self.log(
            f'[4/4] Encoding {seconds / 60:.1f} min of audio ({encoder.codec} {self.args.bitrate}, '
            f'cover: {cover.name if cover else "none"})'
        )
        encoder.encode(listing, m4b, ffmeta, cover, seconds=seconds, log=self.log)
        self.encoder = encoder.codec
        return m4b, cover

    def summarize(self, assembly: Assembly, m4b, cover, synth_seconds):
        args, seconds = self.args, assembly.frames / assembly.rate
        summary = dict(
            script=str(self.script_path),
            mix=self.mix,
            voices={k: dict(engine=e, voice=v) for k, (e, v) in self.voices.items()},
            vieneu_backend=args.vieneu_backend,
            chapters=len(assembly.chapters),
            chunks_synthesized={e: len(j) for e, j in self.jobs.items()},
            synthesis_wall_seconds=synth_seconds,
            audio_seconds=seconds,
            sample_rate=assembly.rate,
            encoder=self.encoder,
            bitrate=args.bitrate,
            cover=str(cover) if cover else None,
            output=str(m4b),
            chapter_marks_ms=assembly.marks(),
        )
        (self.out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        self.log(
            f'Done: {m4b} ({seconds / 60:.1f} min, {len(assembly.chapters)} chapters, {m4b.stat().st_size / 1e6:.1f} MB)'
        )


def cmd_build(args):
    BookBuild(args).run()
