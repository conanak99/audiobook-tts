#!/usr/bin/env python3
"""Run rule-based speaker attribution over many stories; print coverage and dump samples for review."""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from viettts.audiobook.script import UNKNOWN, build_book  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path, help='Directory searched for */story_vn.md')
    p.add_argument('--pattern', default='*/story_vn.md')
    p.add_argument('--samples', type=int, default=0, help='Random quotes to dump for manual review')
    p.add_argument('--rule', help='Only sample quotes decided by this rule')
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--brief', action='store_true', help="Show only the quote's own paragraph")
    p.add_argument('--out', type=Path, help='Write samples as JSONL here')
    args = p.parse_args()
    total, rows, pool = Counter(), [], []
    for path in sorted(args.root.glob(args.pattern)):
        book = build_book(path.read_text(encoding='utf-8-sig'))
        rules = Counter()
        for ci, chapter in enumerate(book.chapters):
            paras = chapter.paragraphs
            for pi, para in enumerate(paras):
                for q in para.quotes:
                    rules[q.rule] += 1
                    context = [
                        ' '.join(f'«{s.text}»' if s.kind == 'quote' else s.text for s in x.segments)
                        for x in paras[max(0, pi - 2) : pi + 2]
                    ]
                    own = ' '.join(f'«{s.text}»' if s.kind == 'quote' else s.text for s in para.segments)
                    pool.append(
                        dict(
                            story=path.parent.name,
                            chapter=ci + 1,
                            quote=q.text,
                            rule=q.rule,
                            paragraph=own,
                            speaker=q.speaker,
                            gender=book.speakers.get(q.speaker, '?'),
                            narrator=book.narrator,
                            context=context,
                        )
                    )
        quotes = sum(rules.values())
        unknown_gender = sum(1 for x in pool[-quotes:] if x['gender'] == '?') if quotes else 0
        total.update(rules)
        total['_quotes'] += quotes
        total['_unknown_gender'] += unknown_gender
        rows.append(
            (
                path.parent.name,
                book.narrator,
                quotes,
                rules[UNKNOWN if False else 'unknown'],
                unknown_gender,
                len(book.speakers),
            )
        )
    print(f'{"story":28} narr  quotes  unk  ?gender  speakers')
    for r in rows:
        print(f'{r[0]:28} {r[1]:5} {r[2]:6} {r[3]:5} {r[4]:7} {r[5]:5}')
    q = total.pop('_quotes')
    ug = total.pop('_unknown_gender')
    print(
        f'\n{len(rows)} stories, {q} quotes; unresolved speaker {total["unknown"]} '
        f'({100 * total["unknown"] / max(q, 1):.1f}%), unknown gender {ug} ({100 * ug / max(q, 1):.1f}%)'
    )
    for rule, n in total.most_common():
        print(f'  {rule:15} {n:7} {100 * n / max(q, 1):5.1f}%')
    if args.samples:
        random.seed(args.seed)
        chosen = [x for x in pool if not args.rule or x['rule'] == args.rule]
        chosen = random.sample(chosen, min(args.samples, len(chosen)))
        if args.out:
            args.out.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in chosen) + '\n', encoding='utf-8')
        else:
            for i, x in enumerate(chosen, 1):
                print(f'\n#{i} {x["story"]} ch{x["chapter"]} rule={x["rule"]} -> {x["speaker"]} ({x["gender"]})')
                print('   QUOTE:', x['quote'][:120])
                if args.brief:
                    print('   PARA :', x['paragraph'][:400])
                    continue
                for c in x['context']:
                    print('   |', c[:300])


if __name__ == '__main__':
    main()
