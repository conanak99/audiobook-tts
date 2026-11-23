"""audiobook repair, scan and make-ref: cache upkeep and VieNeu-made Drama-3 references."""

import json
import subprocess

from viettts.paths import ROOT
from viettts.text import slugify

from .audio import longest_silence
from .workers import uv_command

REF_SENTENCE = (
    'Xin chào, tôi là người đọc truyện hôm nay. Mời bạn cùng lắng nghe câu chuyện chậm rãi và rõ ràng này nhé.'
)


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
