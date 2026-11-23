#!/usr/bin/env python3
"""Reconcile several speech-to-text hypotheses into one exact transcript.

Independent judges via NanoGPT: audio-capable models listen to the clip together with the hypotheses, and a
text-only model reconciles the hypotheses. Pairwise agreement is reported so a person (or agent) can
review; with --write, the answer that agrees most with the other judges goes to <clip>.txt.
Key: $NANOGPT_API_KEY or --key-file.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .transcription import agreement, words

CHAT = 'https://nano-gpt.com/api/v1/chat/completions'
AUDIO_JUDGES = ['qwen/qwen3.5-omni-plus', 'qwen/qwen3.8-omni-flash', 'perceptron/perceptron-mk1.5', 'gemini-2.5-flash']
TEXT_JUDGE = 'anthropic/claude-opus-5.5'
INSTRUCTIONS = """You are producing the exact verbatim transcript of a short Vietnamese speech clip (cut from a
stream, video or recording). It will be the reference transcript for voice cloning, so it must match what is spoken, word for word.

Rules:
- Vietnamese with correct diacritics; keep fillers and particles exactly as spoken (á, nè, hả, nha, ờ, ừm).
- Keep English loanwords as spoken (stream, Twitch, donate, sub).
- Drop speech-recognition hallucinations that are not in the audio, for example "Hãy subscribe cho kênh Ghiền Mì Gõ
  Để không bỏ lỡ những video hấp dẫn", subtitle credits, or repeated phrases.
- No annotations such as *cười* or [laughs], no speaker labels, no quotes. Normal punctuation only.
- Write numbers the way they are spoken if that is clear (e.g. "năm mươi năm mươi" vs "50/50"): prefer words.
Output ONLY the transcript text."""
INSTRUCTIONS_OTHER = """You are producing the exact verbatim transcript of a short {language} speech clip (cut from a
stream, video or recording). It will be the reference transcript for voice cloning, so it must match what is spoken, word for word.

Rules:
- Write {language} in its normal script; keep fillers and particles exactly as spoken.
- Drop speech-recognition hallucinations that are not in the audio (subtitle credits, "thanks for watching",
  repeated phrases).
- No annotations such as [laughs], no speaker labels, no quotes, no translation. Normal punctuation only.
Output ONLY the transcript text."""
LANGUAGES = {'ja': 'Japanese', 'en': 'English', 'zh': 'Chinese', 'ko': 'Korean'}
PUNCTUATE = """Add Vietnamese punctuation and capitalization to this transcript. Do NOT add, remove, reorder or
change any word; keep every particle and filler. Capitalize names (Mika, Twitch, YouTube). Output only the text.

"""


def chat(model, content, key):
    body = json.dumps({'model': model, 'temperature': 0, 'messages': [{'role': 'user', 'content': content}]})
    request = urllib.request.Request(
        CHAT, body.encode(), {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'{model}: HTTP {error.code} {error.read().decode("utf-8", "replace")[:300]}') from None
    return data['choices'][0]['message']['content'].strip().strip('"').strip()


def hypotheses_text(report, hint):
    lines = [f'Hypothesis {i + 1} ({model}): {text}' for i, (model, text) in enumerate(report['models'].items())]
    if hint:
        lines.append(f'Partial transcript from an earlier note (may be incomplete or start mid-clip): {hint}')
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('clips', nargs='+', type=Path)
    p.add_argument('--key-file', type=Path)
    p.add_argument('--audio-judges', default=','.join(AUDIO_JUDGES))
    p.add_argument('--text-judge', default=TEXT_JUDGE)
    p.add_argument('--write', action='store_true')
    p.add_argument('--hint', help='A partial human transcript, if any')
    p.add_argument('--language', default='vi', help='ISO 639-1 code of the spoken language (default: vi)')
    args = p.parse_args()
    global INSTRUCTIONS, PUNCTUATE
    if args.language != 'vi':
        language = LANGUAGES.get(args.language, args.language)
        INSTRUCTIONS = INSTRUCTIONS_OTHER.format(language=language)
        PUNCTUATE = PUNCTUATE.replace('Vietnamese', language)
    key = os.environ.get('NANOGPT_API_KEY') or (args.key_file.read_text().strip() if args.key_file else '')
    if not key:
        sys.exit('Set NANOGPT_API_KEY or pass --key-file.')
    for clip in args.clips:
        report_path = clip.with_suffix('.stt.json')
        report = json.loads(report_path.read_text(encoding='utf-8'))
        hyps = hypotheses_text(report, args.hint)
        audio = base64.b64encode(clip.read_bytes()).decode()
        answers, errors = {}, {}
        for model in args.audio_judges.split(','):
            try:
                answers[model] = chat(
                    model,
                    [
                        {
                            'type': 'text',
                            'text': INSTRUCTIONS + '\n\nListen to the attached audio. These automatic '
                            'hypotheses may help, but the audio decides:\n' + hyps,
                        },
                        {'type': 'input_audio', 'input_audio': {'data': audio, 'format': 'wav'}},
                    ],
                    key,
                )
            except RuntimeError as error:
                errors[model] = str(error)
        try:
            answers[args.text_judge] = chat(
                args.text_judge,
                INSTRUCTIONS + '\n\nYou cannot hear the audio; reconcile '
                'these hypotheses into the most likely exact transcript:\n' + hyps,
                key,
            )
        except RuntimeError as error:
            errors[args.text_judge] = str(error)
        names = list(answers)
        pairs = {
            f'{a} vs {b}': round(agreement(answers[a], answers[b]), 3)
            for i, a in enumerate(names)
            for b in names[i + 1 :]
        }
        listened = [m for m in names if m != args.text_judge] or names
        best = max(listened, key=lambda m: sum(agreement(answers[m], answers[o]) for o in names if o != m))
        chosen = answers[best]
        try:
            punctuated = chat(args.text_judge, PUNCTUATE + chosen, key)
            if words(punctuated) == words(chosen):  # only punctuation/case may change
                chosen = punctuated
            else:
                errors['punctuation'] = 'punctuated text changed words; kept the raw transcript'
        except RuntimeError as error:
            errors['punctuation'] = str(error)
        report.update(judges=answers, judge_errors=errors, judges_agreement=pairs, chosen_judge=best, chosen=chosen)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'\n== {clip.name}: chosen {best} ({len(words(chosen))} words)\n  FINAL: {chosen}')
        for model, text in answers.items():
            print(f'  {model:28} {text}')
        for model, message in errors.items():
            print(f'  {model:28} ERROR {message[:160]}')
        print('  agreement: ' + ', '.join(f'{k} {v}' for k, v in pairs.items()))
        if args.write:
            clip.with_suffix('.txt').write_text(chosen + '\n', encoding='utf-8')
            print(f'  wrote {clip.with_suffix(".txt").name}')


if __name__ == '__main__':
    main()
