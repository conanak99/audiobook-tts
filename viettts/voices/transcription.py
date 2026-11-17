#!/usr/bin/env python3
"""Transcribe reference clips with several NanoGPT speech-to-text models and compare them.

The API key is read from $NANOGPT_API_KEY or --key-file (never pass it on the command line).
Results go to <clip>.stt.json next to each clip; with --write, the consensus transcript is written to
<clip>.txt. Normally run through `python3 -m viettts voice transcribe`, followed by reconciliation.
"""

import argparse
import difflib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = 'https://api.nano-gpt.com/api/v1/audio/transcriptions'
MODELS = ['Whisper-Large-V3', 'gpt-4o-mini-transcribe', 'Wizper']


def transcribe(path, model, key, language='vi', retries=2):
    boundary = uuid.uuid4().hex
    fields = [('model', model), ('language', language), ('response_format', 'json')]
    body = b''.join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields
    )
    body += (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f'Content-Type: audio/wav\r\n\r\n'
        ).encode()
        + path.read_bytes()
        + f'\r\n--{boundary}--\r\n'.encode()
    )
    request = urllib.request.Request(
        API, body, {'Authorization': f'Bearer {key}', 'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = json.load(response)
            return (data.get('text') or data.get('transcription') or '').strip()
        except urllib.error.HTTPError as error:
            detail = error.read().decode('utf-8', 'replace')[:200]
            if attempt == retries or error.code in (400, 401, 402, 413):
                raise RuntimeError(f'{model}: HTTP {error.code} {detail}') from None
        except urllib.error.URLError as error:
            if attempt == retries:
                raise RuntimeError(f'{model}: {error}') from None
        time.sleep(2 * (attempt + 1))


def words(text):
    return re.findall(r'\w+', unicodedata.normalize('NFC', text).lower())


def agreement(a, b):
    return difflib.SequenceMatcher(None, words(a), words(b)).ratio()


def consensus(results):
    """The transcript that agrees most with the others (ties: the longer one)."""
    texts = {m: t for m, t in results.items() if t}
    if len(texts) == 1:
        return next(iter(texts.items()))
    scored = {m: sum(agreement(t, o) for n, o in texts.items() if n != m) / (len(texts) - 1) for m, t in texts.items()}
    best = max(scored, key=lambda m: (scored[m], len(texts[m])))
    return best, texts[best]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('clips', nargs='+', type=Path)
    p.add_argument('--models', default=','.join(MODELS))
    p.add_argument('--key-file', type=Path)
    p.add_argument('--write', action='store_true', help='Write the consensus transcript to <clip>.txt')
    args = p.parse_args()
    key = os.environ.get('NANOGPT_API_KEY') or (args.key_file.read_text().strip() if args.key_file else '')
    if not key:
        sys.exit('Set NANOGPT_API_KEY or pass --key-file.')
    for clip in args.clips:
        results, errors = {}, {}
        for model in args.models.split(','):
            try:
                results[model] = transcribe(clip, model, key)
            except RuntimeError as error:
                errors[model] = str(error)
        if not results:
            print(f'{clip.name}: all models failed: {errors}')
            continue
        best_model, best = consensus(results)
        pairs = {
            f'{a} vs {b}': round(agreement(results[a], results[b]), 3)
            for i, a in enumerate(results)
            for b in list(results)[i + 1 :]
        }
        report = dict(
            clip=clip.name, models=results, errors=errors, agreement=pairs, consensus_model=best_model, consensus=best
        )
        clip.with_suffix('.stt.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
        )
        print(f'\n== {clip.name} ({len(words(best))} words, consensus from {best_model})')
        for model, text in results.items():
            print(f'  {model:24} {text}')
        for model, message in errors.items():
            print(f'  {model:24} ERROR {message}')
        print('  agreement: ' + ', '.join(f'{k} {v}' for k, v in pairs.items()))
        if args.write:
            clip.with_suffix('.txt').write_text(best + '\n', encoding='utf-8')
            print(f'  wrote {clip.with_suffix(".txt").name}')


if __name__ == '__main__':
    main()
