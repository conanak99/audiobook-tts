"""Transcribe 16 kHz mono WAVs into cues (runs in engines/drama3: python -m viettts.subs.worker request.json).

MOSS-Transcribe-Diarize finds every spoken phrase and who says it, moaned and breathy lines included (Silero
VAD heard nothing in 10 of 15 minutes of a moaning scene). Its turns run end to end, so each is trimmed to its
loud part, which brings back the pauses the translate skill reads as scene breaks. A speaker's phrases are
merged into lines and anime-whisper transcribes each line: its text is far better for acted and explicit
speech (MOSS heard オナニー as 女に). anime-whisper is trained on short galgame clips, so it never sees a whole
track, and it gets no prompt (its model card: prompts make it hallucinate). MOSS's own text is the fallback.

anime-whisper only knows Japanese. A Chinese track keeps MOSS's text: on a whispered ear-licking scene it
beat Qwen3-ASR, which made up whole sentences (我也要舔了 became 我也要点歌); MOSS only slips on sound-alikes
(射箭 for 射精) that the translator fixes from context. The language is read off MOSS's transcript.
"""

import json
import re
import sys
import time

import numpy as np
import soundfile as sf

from viettts.subs import cues as plan

SR = 16000
HOP = SR // 100  # 10 ms loudness frames
ASR = ('litagin/anime-whisper', '22e2008a8182b357da3922a6308d095008f72973')
DIARIZE = ('OpenMOSS-Team/MOSS-Transcribe-Diarize', '10304d926740cf5a5cee05a268086e3265197910')
# Trim threshold between the track's quiet floor and its loud speech (10th/90th percentile of 10 ms frames).
# 0.35 kept every moaned phrase of a 15-minute 手マン track and still restored pauses between lines.
TRIM_LEVEL = 0.35
# MOSS stops at max_tokens (generate() defaults to 2048, which cut every track after 5-10 minutes); dense
# moaning ran ~400 tokens a minute, so allow 1,000 a minute.
TOKENS_PER_MINUTE = 1000
MIN_TOKENS = 4096
MAX_TAIL = 90.0  # seconds of audio after the last turn before the transcript counts as cut short


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def loudness(audio: np.ndarray) -> tuple[np.ndarray, float]:
    frames = audio[: len(audio) // HOP * HOP].reshape(-1, HOP)
    db = 10 * np.log10(np.mean(frames**2, axis=1) + 1e-10)
    db = np.convolve(db, np.ones(5) / 5, mode='same')
    heard = db[db > -70]
    if not len(heard):
        return db, 0.0
    floor, loud = np.percentile(heard, 10), np.percentile(heard, 90)
    return db, float(floor + TRIM_LEVEL * (loud - floor))


def trim(db: np.ndarray, threshold: float, start: float, end: float) -> tuple[float, float] | None:
    i, j = int(start * 100), min(int(end * 100), len(db))
    loud = np.nonzero(db[i:j] > threshold)[0]
    if not len(loud):
        return None
    return (i + loud[0]) / 100, (i + loud[-1] + 1) / 100


def transcribe(asr, clip: np.ndarray) -> str:
    # Greedy first; whisper's temperature fallback only kicks in for looping or low-confidence output.
    result = asr.generate(clip, language='ja', return_timestamps=False, condition_on_previous_text=False)
    text = result.text.strip()
    return '' if plan.is_loop(text) or plan.is_blank(text) else text


class JapaneseASR:
    """anime-whisper, loaded the first time a Japanese track needs it."""

    def __init__(self):
        self.model = None

    def __call__(self, clip: np.ndarray) -> str:
        if self.model is None:
            from mlx_audio.stt import load

            self.model = load(ASR[0], revision=ASR[1])
        return transcribe(self.model, clip)


def track_cues(
    wav: str, audio: np.ndarray, diarizer, asr, speakers: int, language: str = 'auto'
) -> tuple[list[dict], str]:
    duration = len(audio) / SR
    db, threshold = loudness(audio)
    budget = max(MIN_TOKENS, int(duration / 60 * TOKENS_PER_MINUTE))
    segments = diarizer.generate(wav, max_tokens=budget).segments
    last = max((s['end'] for s in segments), default=0.0)
    if duration - last > MAX_TAIL:
        log(
            f'WARNING: the last line ends at {last:.0f}s of {duration:.0f}s ({len(segments)} turns, {budget} '
            'tokens). Either the track ends without words, or MOSS ran out of tokens: listen to the end.'
        )
    turns = []
    for seg in segments:
        span = trim(db, threshold, seg['start'], seg['end'])
        if span:
            text = re.sub(r'^\[S\d+\]\s*', '', seg['text']).strip()
            turns.append((*span, seg.get('speaker_id') if speakers > 1 else None, text))
    if language == 'auto':
        language = plan.detect_language([t for *_, t in turns])
    lines = plan.merge_turns([(a, b, s) for a, b, s, _ in turns])
    labels = plan.label_speakers([s for _, _, s in lines])
    cues = []
    for (start, end, speaker), label in zip(lines, labels):
        text = ''
        if language == 'ja':
            for a, b in plan.split_long([(max(0.0, start - plan.CLIP_PAD), min(duration, end + plan.CLIP_PAD))]):
                text += asr(audio[int(a * SR) : int(b * SR)])
        text = text or ''.join(t for a, b, s, t in turns if s == speaker and start <= a and b <= end)
        if text and not plan.is_blank(text):
            cue = {'start': round(start, 3), 'end': round(end, 3), 'text': text}
            if label:
                cue['speaker'] = label
            cues.append(cue)
    return cues, language


def main() -> None:
    request = json.loads(open(sys.argv[1], encoding='utf-8').read())
    from mlx_audio.stt import load

    t0 = time.time()
    asr = JapaneseASR()
    diarizer = load(DIARIZE[0], revision=DIARIZE[1])
    log(f'MOSS loaded in {time.time() - t0:.0f}s')

    for track in request['tracks']:
        t0 = time.time()
        audio, sr = sf.read(track['wav'], dtype='float32')
        if sr != SR or audio.ndim != 1:
            raise SystemExit(f'{track["wav"]}: expected 16 kHz mono, got {sr} Hz, {audio.ndim} channel(s)')
        cues, language = track_cues(
            track['wav'], audio, diarizer, asr, request['speakers'], request.get('language', 'auto')
        )
        with open(track['out'], 'w', encoding='utf-8') as f:
            json.dump(cues, f, ensure_ascii=False, indent=1)
        print(
            json.dumps(
                {'out': track['out'], 'cues': len(cues), 'language': language, 'seconds': round(time.time() - t0, 1)}
            ),
            flush=True,
        )


if __name__ == '__main__':
    main()
