"""Synthesis worker processes (one engine environment each), the build log, and their shared helpers."""

import json
import queue
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from viettts.paths import ROOT
from viettts.paths import uv_command as python_command


def uv_command(engine, *args):
    return python_command(engine, '-m', 'viettts', 'audiobook', *args)


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


def frame_budget(text):
    """Drama-3 frames (~21.5/s) a take may use before it is rejected as never ending: ~3 per character plus
    room for the pauses that "..." and sentence breaks bring. A larger budget for tagged takes (256 floor,
    ~4 per character) was tried: takes that run past this one ran past 16 s for a 3.5 s line too, so it only
    made each failed attempt slower."""
    pauses = 40 * text.count('...') + 15 * len(re.findall(r'[.!?…]', text))
    return min(600, max(128, len(text) * 3 + pauses))


RESCUE_DIRECTION = '[calm, natural]'


def take_texts(job):
    """[(kind, text)] a Drama-3 chunk is tried with, 4 takes each, until one ends: as written, then (tagged
    chunks) its words alone, then its words under RESCUE_DIRECTION. A plain chunk that runs on (a "...?" question
    or a title with a colon) ends reliably once it has a direction, so a runaway no longer stops the build."""
    words = job.get('plain') or job['text']
    texts = [('as written', job['text'])]
    if job.get('plain'):
        texts.append(('without tags', words))
    texts.append(('neutral direction', f'{RESCUE_DIRECTION} {words}'))
    return texts


def jsonl(jobs):
    return ''.join(json.dumps(j, ensure_ascii=False) + '\n' for j in jobs)


class WorkerPool:
    """Synthesize jobs into one engine's cache with `workers` processes. backend: VieNeu's gguf|onnx.

    With several workers, their per-chunk progress lines are merged into one combined line (at most every
    5 s); other lines are passed through tagged with the worker number. The first worker loads (and on a
    fresh machine downloads) the model before the others start, so they never download at the same time.
    """

    PROGRESS_EVERY_S = 5

    def __init__(self, engine: str, cache: Path, threads: int, workers: int, log, backend: str = 'gguf'):
        self.engine, self.cache, self.threads, self.workers = engine, cache, threads, workers
        self.log, self.backend = log, backend

    def run(self, jobs: list[dict[str, Any]]) -> bool:
        """True if every worker succeeded."""
        (self.cache / 'jobs.jsonl').write_text(jsonl(jobs), encoding='utf-8')  # every job: scan/repair read it
        for old in self.cache.glob('jobs-*.jsonl'):
            old.unlink()
        shards = shard(jobs, max(1, self.workers)) if self.workers > 1 else [jobs]
        if len(shards) == 1:
            return self._run_one(self.cache / 'jobs.jsonl')
        return self._run_shards(jobs, shards)

    def _start(self, path: Path) -> subprocess.Popen:
        extra = ['--backend', self.backend] if self.engine == 'vieneu' else []
        # A chunk that fails every take is reported and skipped, so the rest still gets synthesized;
        # the build lists what is missing afterwards (Build.synthesize).
        command, env = uv_command(
            self.engine,
            'worker',
            self.engine,
            str(path),
            str(self.cache),
            '--threads',
            str(self.threads),
            '--skip-failed',
            *extra,
        )
        return subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8'
        )

    def _run_one(self, path: Path) -> bool:
        process = self._start(path)
        assert process.stdout is not None  # stdout=PIPE guarantees a readable stream.
        for line in process.stdout:
            self.log(line.rstrip('\n'), stamp=False)
        return process.wait() == 0

    def _run_shards(self, jobs, shards) -> bool:
        engine = self.engine
        self.log(f'      {len(shards)} {engine} workers × {self.threads} threads')
        sizes = [[len(j['text']) for j in part] for part in shards]
        total = sum(map(sum, sizes))
        lines: queue.Queue[tuple[int, str | None]] = queue.Queue()
        procs: list[subprocess.Popen] = []

        def start(k):
            path = self.cache / f'jobs-{k + 1}.jsonl'
            path.write_text(jsonl(shards[k]), encoding='utf-8')
            process = self._start(path)
            procs.append(process)

            def pump():
                assert process.stdout is not None
                for line in process.stdout:
                    lines.put((k, line.rstrip('\n')))
                lines.put((k, None))

            threading.Thread(target=pump, daemon=True).start()

        start(0)
        progress = re.compile(rf'\[{engine}\] (\d+)/\d+ \(')
        done, running, started, shown = [0] * len(shards), 1, time.perf_counter(), 0.0
        while running:
            k, line = lines.get()
            if line is None:
                running -= 1
                if k == 0 and len(procs) == 1:  # the first worker died before loading: start no others
                    break
                continue
            if k == 0 and len(procs) == 1 and 'model loaded' in line:
                for other in range(1, len(shards)):
                    start(other)
                running += len(shards) - 1
            m = progress.match(line)
            if not m:
                self.log(re.sub(rf'^\[{engine}\]', f'[{engine} w{k + 1}]', line), stamp=False)
                continue
            done[k] = int(m[1])
            now = time.perf_counter()
            chars = sum(sum(sz[:d]) for sz, d in zip(sizes, done))
            if now - shown >= self.PROGRESS_EVERY_S or chars == total:
                elapsed = now - started
                self.log(
                    f'[{engine}] {sum(done)}/{len(jobs)} ({100 * chars / total:5.1f}%) · {len(procs)} workers · '
                    f'elapsed {clock(elapsed)} · ETA {clock(elapsed / chars * (total - chars))}',
                    stamp=False,
                )
                shown = now
        return all(p.wait() == 0 for p in procs)
