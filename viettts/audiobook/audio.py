"""PCM helpers shared by the builder (stdlib) and the engine workers (numpy passed in)."""

import sys
import wave
from array import array

MAX_SILENCE_S = 1.5  # a generated chunk with a longer internal pause is regenerated (Drama-3) or squeezed


EDGE_MS = 30


def read_pcm(path):
    with wave.open(str(path), 'rb') as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.readframes(w.getnframes())


def trim_edges(pcm, rate, channels, width, threshold_db=-40, margin_ms=EDGE_MS):
    """Cut a chunk's leading and trailing silence (10 ms windows peaking under threshold_db) to margin_ms,
    so the pauses between chunks are exactly the planned ones. Silent or non-16-bit-mono audio is kept."""
    if (channels, width) != (1, 2):
        return pcm
    a = array('h')
    a.frombytes(pcm)
    if sys.byteorder != 'little':
        a.byteswap()
    win, level = max(1, rate // 100), round(32768 * 10 ** (threshold_db / 20))

    def loud(i):
        return max(max(a[i : i + win]), -min(a[i : i + win])) > level

    start = 0
    while start < len(a) and not loud(start):
        start += win
    if start >= len(a):
        return pcm
    end = len(a)
    while end - win > start and not loud(end - win):
        end -= win
    margin = rate * margin_ms // 1000
    return pcm[max(0, start - margin) * 2 : min(len(a), end + margin) * 2]


def silent_frames(samples, rate, np, floor_db=-50.0):
    hop = max(1, rate // 100)
    usable = samples[: len(samples) // hop * hop]
    if not usable.size:
        return np.zeros(0, dtype=bool), hop
    return np.abs(usable.reshape(-1, hop)).max(axis=1) < 10 ** (floor_db / 20), hop


def longest_silence(samples, rate, np):
    quiet, _ = silent_frames(samples, rate, np)
    best = run = 0
    for q in quiet:
        run = run + 1 if q else 0
        best = max(best, run)
    return best / 100


def squeeze(samples, rate, np, longer_than=0.8, keep=0.5):
    """Shorten pauses inside a chunk; the builder adds the pauses between lines itself."""
    quiet, hop = silent_frames(samples, rate, np)
    keep_frames, pieces, start, i = int(keep * 100), [], 0, 0
    while i < len(quiet):
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < len(quiet) and quiet[j]:
            j += 1
        inside = i > 0 and j < len(quiet)
        if inside and (j - i) / 100 > longer_than:
            pieces.append(samples[start : (i + keep_frames // 2) * hop])
            start = (j - keep_frames // 2) * hop
        i = j
    pieces.append(samples[start:])
    return np.concatenate(pieces)


def level(samples, np, target_db=-20.0, max_gain_db=12.0, peak=0.89):
    """Bring every chunk to the same speech loudness so voices from different references match."""
    voiced = samples[np.abs(samples) > 0.01]
    if voiced.size < 100:
        return samples
    rms_db = 20 * np.log10(np.sqrt(np.mean(voiced**2)))
    gain = 10 ** (max(-max_gain_db, min(max_gain_db, target_db - rms_db)) / 20)
    samples = samples * gain
    top = np.max(np.abs(samples))
    return samples * (peak / top) if top > peak else samples
