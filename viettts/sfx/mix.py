"""Mix placed cues under voice-only chapter WAVs (runs in engines/sfx: python -m viettts.sfx.mix plan.json).

plan.json: {"chapters": [{"voice": in.wav, "out": out.wav, "inserts": [[at_s, seconds], ...], "cues": [...]}]}
with placements from viettts.sfx.cues.place. inserts (from clear cues) are silences spliced into the voice at
voice-only times; the cues are already timed for the longer chapter. A loop becomes a bed of its takes
(viettts.sfx.loops); the sum goes through a soft limiter so the voice never clips. Prints one JSON summary line per chapter.
"""

import json
import sys

import numpy as np
import soundfile as sf

from viettts.sfx import loops

LIMIT = 0.89  # about -1 dBFS: samples above it are bent softly towards 1.0


def resample(x, rate, target):
    if rate == target:
        return x
    n = round(len(x) * target / rate)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def soft_limit(x):
    over = np.abs(x) > LIMIT
    if over.any():
        a = np.abs(x[over])
        x[over] = np.sign(x[over]) * (LIMIT + (1 - LIMIT) * np.tanh((a - LIMIT) / (1 - LIMIT)))
    return int(over.sum())


def load(path, rate, clips):
    if (path, rate) not in clips:
        x, r = sf.read(path, dtype='float32')
        clips[path, rate] = resample(x if x.ndim == 1 else x.mean(axis=1), r, rate)
    return clips[path, rate]


def splice(voice, rate, inserts):
    """The voice with silence inserted at each [at_s, seconds] (voice-only times)."""
    pieces, last = [], 0
    for at, seconds in sorted(inserts):
        cut = min(len(voice), round(at * rate))
        pieces += [voice[last:cut], np.zeros(round(seconds * rate), dtype=voice.dtype)]
        last = cut
    return np.concatenate([*pieces, voice[last:]])


def mix_chapter(chapter, clips):
    voice, rate = sf.read(chapter['voice'], dtype='float32')
    if voice.ndim > 1:
        voice = voice.mean(axis=1)
    voice = splice(voice, rate, chapter.get('inserts', []))
    bed = np.zeros_like(voice)
    for cue in chapter['cues']:
        takes = [load(path, rate, clips) for path in cue['files']]
        start = round(cue['start_s'] * rate)
        frames = min(round(cue['seconds'] * rate), len(bed) - start)
        if frames <= 0:
            continue
        if cue['kind'] == 'loop':
            x = loops.bed(takes, frames, rate, loops.cue_seed(cue['sound'], cue['chapter'], cue['start_s']))
        else:
            x = takes[0][:frames].copy()
        fade_in, fade_out = round(cue['fade_in_s'] * rate), round(cue['fade_out_s'] * rate)
        if fade_in:
            x[:fade_in] *= np.linspace(0, 1, fade_in, dtype=np.float32)
        if fade_out:
            x[-fade_out:] *= np.linspace(1, 0, fade_out, dtype=np.float32)
        bed[start : start + len(x)] += x * 10 ** (cue['gain_db'] / 20)
    out = voice + bed
    limited = soft_limit(out)
    sf.write(chapter['out'], out, rate, subtype='PCM_16')
    return dict(
        out=chapter['out'],
        frames=len(out),
        rate=rate,
        cues=len(chapter['cues']),
        peak_dbfs=round(float(20 * np.log10(np.abs(out).max() + 1e-9)), 1),
        limited_samples=limited,
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    plan = json.loads(open(argv[0], encoding='utf-8').read())
    clips: dict = {}
    for chapter in plan['chapters']:
        print(json.dumps(mix_chapter(chapter, clips), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
