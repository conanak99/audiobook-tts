import unittest

try:
    import numpy as np
except ImportError:  # the orchestrator runs on plain python3; the mixer runs in engines/sfx
    np = None

RATE = 8000


def clicks(seconds, every=0.5, offset=0.1):
    """A rhythmic take: a 30 ms burst every `every` seconds, silence between (like slaps)."""
    x = np.zeros(int(seconds * RATE), dtype=np.float32)
    burst = int(0.03 * RATE)
    for start in np.arange(offset, seconds - 0.05, every):
        i = int(start * RATE)
        x[i : i + burst] = 0.8
    return x


@unittest.skipIf(np is None, 'numpy is only installed in the dev and engine environments')
class LoopBedTests(unittest.TestCase):
    def setUp(self):
        from viettts.sfx import loops

        self.loops = loops
        self.takes = [clicks(5.0), clicks(3.0, offset=0.2), clicks(7.5, offset=0.3)]

    def test_order_shuffles_without_repeats_and_leads_with_the_first_take(self):
        rng = np.random.default_rng(1)
        seq = [k for k, _ in zip(self.loops.order(3, rng, first=2), range(60))]
        self.assertEqual(seq[0], 2)
        self.assertTrue(all(a != b for a, b in zip(seq, seq[1:])))
        rounds = {tuple(seq[i : i + 3]) for i in range(0, 60, 3)}
        self.assertGreater(len(rounds), 1)  # not one fixed A-B-C pattern

    def test_seams_are_cut_in_the_quiet_between_hits(self):
        rng = np.random.default_rng(7)
        parts = self.loops.pieces(self.takes, 40 * RATE, RATE, rng)
        edge = int(0.01 * RATE)
        for part in parts[1:]:
            self.assertLess(np.abs(part[:edge]).max(), 0.01)  # starts between two hits
        for part in parts[:-1]:
            self.assertLess(np.abs(part[-edge:]).max(), 0.01)  # and ends between two hits
        self.assertGreaterEqual(sum(map(len, parts)), 40 * RATE)

    def test_bed_has_the_length_is_repeatable_and_drifts_gently(self):
        a = self.loops.bed(self.takes, 30 * RATE, RATE, seed=3)
        self.assertEqual(len(a), 30 * RATE)
        np.testing.assert_array_equal(a, self.loops.bed(self.takes, 30 * RATE, RATE, seed=3))
        self.assertFalse(np.array_equal(a, self.loops.bed(self.takes, 30 * RATE, RATE, seed=4)))
        gain = self.loops.drift(60 * RATE, RATE, np.random.default_rng(0))
        db = 20 * np.log10(gain)
        self.assertLessEqual(np.abs(db).max(), self.loops.DRIFT_DB + 1e-4)
        self.assertGreater(db.max() - db.min(), 1.0)  # it does move

    def test_a_short_span_is_one_piece_of_the_first_take(self):
        x = self.loops.bed(self.takes, RATE, RATE, seed=0)
        self.assertEqual(len(x), RATE)
        self.assertGreater(np.abs(x).max(), 0.5)


if __name__ == '__main__':
    unittest.main()
