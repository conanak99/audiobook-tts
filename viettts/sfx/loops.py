"""Long beds from short takes, so a 60 s scene doesn't sound like one clip on repeat (numpy only).

- Pieces come from the takes in a shuffled order each round, never the same take twice in a row, each
  starting at its own point in the take.
- Every seam is cut where both sides are quietest (between two slaps or creaks), with a short crossfade,
  so the rhythm doesn't hiccup.
- A slow, gentle level drift (about ±1.5 dB) keeps the bed alive.

Everything random is seeded per cue, so a remix of the same sfx.txt sounds the same.
"""

import zlib

import numpy as np

CROSSFADE_S = 0.03  # short: a seam is placed where the sound is quiet
PIECE_MIN_S = 1.5  # a piece is at least this long (or the whole take)
SEARCH_S = 0.6  # how far a seam may move to find a quiet spot
EDGE_S = 0.15  # the library fades each take's ends; never cut inside them
FRAME_S = 0.01
DRIFT_DB = 1.5
DRIFT_PERIODS_S = (5.3, 8.9)


def cue_seed(*parts) -> int:
    return zlib.crc32('|'.join(map(str, parts)).encode('utf-8'))


def envelope(x, rate):
    """RMS per FRAME_S frame."""
    hop = max(1, round(FRAME_S * rate))
    n = len(x) // hop
    if not n:
        return np.zeros(0, dtype=np.float32), hop
    return np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1)), hop


def quietest(x, rate, around, lo, hi):
    """The sample index in [lo, hi) nearest `around`'s neighbourhood where x is quietest."""
    lo, hi = max(0, int(lo)), min(len(x), int(hi))
    if hi - lo < 2:
        return min(max(int(around), 0), len(x))
    env, hop = envelope(x[lo:hi], rate)
    if not len(env):
        return int(around)
    return lo + int(np.argmin(env)) * hop + hop // 2


def order(n_takes, rng, first=0):
    """Endless take indices: shuffled each round, never the same take twice in a row, starting at `first`."""
    last = None
    while True:
        round_ = list(rng.permutation(n_takes))
        if last is None:
            round_.remove(first)
            round_.insert(0, first)
        elif n_takes > 1 and round_[0] == last:
            round_.append(round_.pop(0))
        for k in round_:
            yield int(k)
            last = int(k)


def drift(frames, rate, rng):
    """A slow gain curve of about ±DRIFT_DB: two slow sines at random phases."""
    t = np.arange(frames, dtype=np.float32) / rate
    db = sum((DRIFT_DB / 2) * np.sin(2 * np.pi * t / period + rng.uniform(0, 2 * np.pi)) for period in DRIFT_PERIODS_S)
    return (10 ** (db / 20)).astype(np.float32)


def pieces(takes, frames, rate, rng):
    """Cut pieces from the takes until they cover `frames` (with the crossfades). Each piece runs from a
    quiet spot early in its take to a quiet spot near the take's end, inside the library's faded edges."""
    edge, fade = round(EDGE_S * rate), max(1, round(CROSSFADE_S * rate))
    search, piece_min = round(SEARCH_S * rate), round(PIECE_MIN_S * rate)
    covered, cut = 0, []
    for n, k in enumerate(order(len(takes), rng)):
        take = takes[k]
        inner = edge if len(take) > 2 * edge + piece_min else 0
        first, last = inner, len(take) - inner
        if n == 0:
            start = first
        else:
            spot = first + rng.uniform(0, 0.6) * max(0, last - first - piece_min)
            start = quietest(take, rate, spot, spot - search / 2, spot + search / 2)
        stop = quietest(take, rate, last, max(start + piece_min, last - search), last)
        if stop - start < 2 * fade:
            start, stop = first, last
        cut.append(take[start:stop])
        covered += len(cut[-1]) - (fade if n else 0)
        if covered >= frames:
            return cut
    return cut


def join(parts, fade):
    """Pieces end to end, each seam an equal-power crossfade over `fade` samples."""
    out = parts[0].astype(np.float32, copy=True)
    t = np.linspace(0, np.pi / 2, fade, dtype=np.float32)
    fade_out, fade_in = np.cos(t), np.sin(t)
    for piece in parts[1:]:
        n = min(fade, len(out), len(piece))
        out[len(out) - n :] = out[len(out) - n :] * fade_out[-n:] + piece[:n] * fade_in[:n]
        out = np.concatenate([out, piece[n:]])
    return out


def bed(takes, frames, rate, seed):
    """`frames` samples of a loop built from its takes (the first take leads), with a slow level drift."""
    rng = np.random.default_rng(seed)
    fade = max(1, round(CROSSFADE_S * rate))
    out = join(pieces(takes, frames, rate, rng), fade)[:frames]
    if len(out) < frames:  # only with degenerate, tiny takes
        out = np.concatenate([out, np.zeros(frames - len(out), dtype=np.float32)])
    return out * drift(frames, rate, rng)
