"""Transcribe 16 kHz mono WAVs into cues (runs in engines/drama3: python -m viettts.subs.worker request.json).

Single speaker: Silero VAD cuts the lines and anime-whisper transcribes each one. anime-whisper is trained on
short galgame clips, so it must never see a whole track (long-form decoding turns into gibberish), and it gets
no initial prompt (its model card: prompts make it hallucinate). Two speakers: MOSS-Transcribe-Diarize gives
the turns and speaker labels, and anime-whisper re-transcribes each turn; MOSS's own text is the fallback.
"""

import json
import re
import sys
import time

import numpy as np
import soundfile as sf

from viettts.subs import cues as plan

SR = 16000
VAD = ('mlx-community/silero-vad', '7bc17f22d3c0451bd3a6cd71e759b009271ff49a')
ASR = ('litagin/anime-whisper', '22e2008a8182b357da3922a6308d095008f72973')
DIARIZE = ('OpenMOSS-Team/MOSS-Transcribe-Diarize', '10304d926740cf5a5cee05a268086e3265197910')
# Tested on two DLsite tracks: 0.3/300 ms keeps first syllables that 0.4/150 ms clipped (この程度か → の程度か)
VAD_OPTIONS = dict(threshold=0.3, min_silence_duration_ms=400, speech_pad_ms=300, return_seconds=True)


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def transcribe(asr, clip: np.ndarray) -> str:
    # Greedy first; whisper's temperature fallback only kicks in for looping or low-confidence output.
    result = asr.generate(clip, language='ja', return_timestamps=False, condition_on_previous_text=False)
    text = result.text.strip()
    return '' if plan.is_loop(text) else text


def single_speaker(audio: np.ndarray, vad, asr) -> list[dict]:
    spans = [(s['start'], s['end']) for s in vad.get_speech_timestamps(audio, sample_rate=SR, **VAD_OPTIONS)]
    cues = []
    for start, end in plan.split_long(plan.merge_spans(spans)):
        text = transcribe(asr, audio[int(start * SR) : int(end * SR)])
        if text and not plan.is_blank(text):
            cues.append({'start': round(start, 3), 'end': round(end, 3), 'text': text})
    return cues


def two_speakers(wav: str, audio: np.ndarray, diarizer, asr) -> list[dict]:
    duration = len(audio) / SR
    turns = diarizer.generate(wav).segments
    cues = []
    for turn, speaker in zip(turns, plan.label_speakers([t.get('speaker_id') for t in turns])):
        start, end = turn['start'], turn['end']
        fallback = re.sub(r'^\[S\d+\]\s*', '', turn['text']).strip()
        text = ''
        for a, b in plan.split_long([(max(0.0, start - plan.CLIP_PAD), min(duration, end + plan.CLIP_PAD))]):
            part = transcribe(asr, audio[int(a * SR) : int(b * SR)])
            text += part if part and not plan.is_blank(part) else ''
        text = text or fallback
        if text and not plan.is_blank(text):
            cues.append({'start': round(start, 3), 'end': round(end, 3), 'speaker': speaker, 'text': text})
    return cues


def main() -> None:
    request = json.loads(open(sys.argv[1], encoding='utf-8').read())
    from mlx_audio.stt import load as load_stt
    from mlx_audio.vad import load as load_vad

    t0 = time.time()
    asr = load_stt(ASR[0], revision=ASR[1])
    if request['speakers'] == 1:
        vad, diarizer = load_vad(VAD[0], revision=VAD[1]), None
    else:
        vad, diarizer = None, load_stt(DIARIZE[0], revision=DIARIZE[1])
    log(f'models loaded in {time.time() - t0:.0f}s')

    for track in request['tracks']:
        t0 = time.time()
        audio, sr = sf.read(track['wav'], dtype='float32')
        if sr != SR or audio.ndim != 1:
            raise SystemExit(f'{track["wav"]}: expected 16 kHz mono, got {sr} Hz, {audio.ndim} channel(s)')
        cues = two_speakers(track['wav'], audio, diarizer, asr) if diarizer else single_speaker(audio, vad, asr)
        with open(track['out'], 'w', encoding='utf-8') as f:
            json.dump(cues, f, ensure_ascii=False, indent=1)
        print(json.dumps({'out': track['out'], 'cues': len(cues), 'seconds': round(time.time() - t0, 1)}), flush=True)


if __name__ == '__main__':
    main()
