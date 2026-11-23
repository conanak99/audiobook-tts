import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from viettts.audiobook.assembly import Assembler
from viettts.sfx import cues as cue_file
from viettts.sfx import library as lib

RATE = 44100


def write_wav(path, seconds, value=8000, rate=RATE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as w:
        w.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        w.writeframes(array('h', [value, -value] * round(rate * seconds / 2)).tobytes())


TIMELINE = {
    'sample_rate': RATE,
    'chapters': [
        {'chapter': 1, 'title': 'Chương 1', 'start_ms': 0, 'duration_ms': 20000},
        {'chapter': 2, 'title': 'Chương 2', 'start_ms': 20000, 'duration_ms': 10000},
    ],
    'lines': [
        {'line': 9, 'chapter': 1, 'start_ms': 4000, 'end_ms': 6000, 'pause_ms': 300},
        {'line': 10, 'chapter': 1, 'start_ms': 6300, 'end_ms': 9000, 'pause_ms': 600},
        {'line': 12, 'chapter': 1, 'start_ms': 18000, 'end_ms': 19500, 'pause_ms': 500},
        {'line': 20, 'chapter': 2, 'start_ms': 2000, 'end_ms': 3000, 'pause_ms': 1700},
    ],
}


class LibraryTests(unittest.TestCase):
    def test_add_validates_and_keeps_only_the_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = dict(id='bed-creak', category='bed', kind='loop', seconds=5, prompt='A bed creaking slowly.')
            lib.add({**entry, 'file': 'x.wav'}, root)
            (sound,) = lib.load(root)['sounds']
            self.assertEqual(sound, entry)
            self.assertEqual((lib.sound_files(sound, root), lib.missing_takes(sound, root)), ([], lib.DEFAULT_TAKES))
            self.assertEqual([lib.take_seconds(sound, n) for n in (1, 2, 3)], [5.0, 3.0, 7.5])
            self.assertEqual([lib.take_file(sound, n) for n in (1, 2)], ['bed/bed-creak.wav', 'bed/bed-creak-2.wav'])
            with self.assertRaisesRegex(ValueError, 'already exists'):
                lib.add(entry, root)
            with self.assertRaisesRegex(ValueError, 'kind.*seconds'):
                lib.add({**entry, 'id': 'other', 'kind': 'drone', 'seconds': 60}, root)
            with self.assertRaisesRegex(ValueError, 'lowercase'):
                lib.add({**entry, 'id': 'Bed Creak'}, root)
            with self.assertRaisesRegex(ValueError, 'takes'):
                lib.add({**entry, 'id': 'other', 'takes': 0}, root)

    def test_takes_grow_and_shrink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = dict(id='splash', category='body', kind='oneshot', seconds=2, prompt='A short splash of water.')
            lib.add(entry, root)
            library = lib.load(root)
            library['sounds'][0]['rendered'] = [
                dict(file='body/splash.wav', seconds=2.0, seed=0),
                dict(file='body/splash-2.wav', seconds=2.0, seed=1),  # another length than take 2 gets now: kept
            ]
            lib.save(library, root)
            for name in ('splash', 'splash-2'):
                write_wav(root / 'body' / f'{name}.wav', 0.1)
            sound = lib.set_takes('splash', 4, root)
            self.assertEqual(lib.stale_takes(sound, root), [3, 4])
            self.assertEqual([p.name for p in lib.sound_files(sound, root)], ['splash.wav', 'splash-2.wav'])
            sound = lib.set_takes('splash', 1, root)
            self.assertEqual([p.name for p in lib.sound_files(sound, root)], ['splash.wav'])
            self.assertFalse((root / 'body' / 'splash-2.wav').exists())  # a dropped take's file goes too


class CueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

        def takes(*files):
            return [dict(file=f, seconds=seconds, seed=n) for n, (f, seconds) in enumerate(files)]

        sounds = [
            dict(
                id='creak',
                category='bed',
                kind='loop',
                seconds=5,
                prompt='p' * 12,
                takes=2,
                rendered=takes(('bed/creak.wav', 5.0), ('bed/creak-2.wav', 3.0)),
            ),
            dict(
                id='knock',
                category='scene',
                kind='oneshot',
                seconds=2,
                prompt='p' * 12,
                takes=3,
                rendered=takes(('scene/knock.wav', 2.0), ('scene/knock-2.wav', 1.2), ('scene/knock-3.wav', 3.0)),
            ),
            dict(id='unrendered', category='scene', kind='oneshot', seconds=2, prompt='p' * 12),
        ]
        lib.save(dict(sample_rate=RATE, level_dbfs=-20, sounds=sounds), self.root)
        for name, seconds in (('bed/creak.wav', 5), ('bed/creak-2.wav', 3)):
            write_wav(self.root / name, seconds)
        for name, seconds in (('scene/knock.wav', 2), ('scene/knock-2.wav', 1.2), ('scene/knock-3.wav', 3)):
            write_wav(self.root / name, seconds)
        self.library = lib.load(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def place(self, text):
        cues, problems = cue_file.read_cues(text)
        placed, more = cue_file.place(cues, TIMELINE, self.library, self.root)
        return placed, problems + more

    def test_parse_spans_options_and_comments(self):
        cues, problems = cue_file.read_cues(
            '# head\nL9-L10: creak gain=-18  # bed\nL12: knock at=end len=1\n\nL9 creak\n'
        )
        self.assertEqual([(c.first, c.last, c.sound) for c in cues], [(9, 10, 'creak'), (12, 12, 'knock')])
        self.assertEqual(cues[1].options, {'at': 'end', 'len': '1'})
        self.assertEqual([row for row, _ in problems], [5])

    def test_a_loop_fills_its_span_including_the_pause(self):
        (p,), problems = self.place('L9-L10: creak gain=-18\n')
        self.assertEqual(problems, [])
        self.assertEqual((p['chapter'], p['start_s'], p['seconds'], p['gain_db']), (1, 4.0, 5.0, -18.0))
        self.assertEqual((p['fade_in_s'], p['fade_out_s']), (cue_file.LOOP_FADE_IN_S, cue_file.LOOP_FADE_OUT_S))
        (late,), _ = self.place('L9-L10: creak at=1.5 len=2\n')
        self.assertEqual((late['start_s'], late['seconds']), (5.5, 2.0))

    def test_one_shots_play_whole_from_their_anchor(self):
        placed, problems = self.place('L9: knock\nL10: knock at=end\nL10: knock at=-0.5 len=1\n')
        self.assertEqual(problems, [])
        # takes in book order: 4.0 s gets take 1 (2 s), 5.8 s take 2 (1.2 s, cut by len=1), 9.0 s take 3 (3 s)
        self.assertEqual([(p['start_s'], p['seconds']) for p in placed], [(4.0, 2.0), (9.0, 3.0), (5.8, 1.0)])
        self.assertEqual([p['fade_out_s'] for p in placed], [0.0, 0.0, cue_file.ONESHOT_FADE_OUT_S])
        self.assertEqual(placed[0]['gain_db'], cue_file.ONESHOT_GAIN_DB)
        (cut,), _ = self.place('L12: knock at=end\n')  # 19.5 s + 2 s runs past the 20 s chapter
        self.assertEqual(cut['seconds'], 0.5)
        self.assertGreater(cut['fade_out_s'], 0)

    def test_takes_rotate_in_book_order_and_can_be_pinned(self):
        # written out of order: the rotation follows the book, so L10 (later) gets the second take
        placed, problems = self.place('L10: knock\nL9: knock\nL12: knock\nL20: knock\nL9: knock take=3 at=end\n')
        self.assertEqual(problems, [])
        takes = {(p['chapter'], p['start_s']): (p['take'], Path(p['files'][0]).name) for p in placed}
        self.assertEqual(takes[1, 4.0], (1, 'knock.wav'))
        self.assertEqual(takes[1, 6.3], (2, 'knock-2.wav'))
        self.assertEqual(takes[1, 18.0], (3, 'knock-3.wav'))
        self.assertEqual(takes[2, 2.0], (1, 'knock.wav'))  # round again
        self.assertEqual(takes[1, 6.0], (3, 'knock-3.wav'))  # pinned, outside the rotation
        self.assertTrue(all(len(p['files']) == 1 for p in placed))
        loops, _ = self.place('L9: creak\nL10: creak\n')
        self.assertEqual(
            [[Path(f).name for f in p['files']] for p in loops],
            [['creak.wav', 'creak-2.wav'], ['creak-2.wav', 'creak.wav']],
        )  # a loop cycles from its take
        _, bad = self.place('L9: knock take=4\n')
        self.assertIn('take must be 1..3', bad[0][1])

    def test_clear_makes_room_and_shifts_what_follows(self):
        placed, problems = self.place('L9-L10: creak\nL9: knock at=end clear\nL10: knock\nL12: knock\n')
        self.assertEqual(problems, [])
        by_row = {p['row']: p for p in placed}
        clear, loop, next_line, late = by_row[2], by_row[1], by_row[3], by_row[4]
        # take 1 (2 s) starts 0.15 s into L9's 0.3 s pause; L10 waits until 0.25 s after it: 2.1 s more
        self.assertEqual((clear['start_s'], clear['seconds'], clear['insert']), (6.15, 2.0, [6.225, 2.1]))
        self.assertEqual(next_line['start_s'], 6.3 + 2.1)
        self.assertEqual((loop['start_s'], loop['seconds']), (4.0, 5.0 + 2.1))  # the bed goes on through it
        self.assertEqual(late['start_s'], 18.0 + 2.1)
        self.assertEqual([p['insert'] for p in (loop, next_line, late)], [None, None, None])
        self.assertAlmostEqual(cue_file.shift_time(placed, 1, 6.3), 8.4)
        self.assertEqual(cue_file.shift_time(placed, 2, 2.0), 2.0)  # other chapters stay put
        (first,), _ = self.place('L20: knock at=start clear\n')  # a chapter's first line: the title pause
        self.assertAlmostEqual(first['start_s'], 2.0 - cue_file.TITLE_PAUSE_S + cue_file.CLEAR_LEAD_S)

    def test_clear_needs_a_one_shot_in_a_free_pause(self):
        _, problems = self.place('L9: creak clear\nL9: knock at=0.5 clear\nL9: knock at=end clear\nL10: knock clear\n')
        messages = dict(problems)
        self.assertIn('clear is for a one-shot', messages[1])
        self.assertIn('clear is for a one-shot', messages[2])
        self.assertIn('already holds a clear cue (sfx.txt:3)', messages[4])  # L9's pause is the one before L10

    def test_problems_name_the_row(self):
        _, problems = self.place(
            'L9-L20: creak\nL11: knock\nL9: nope\nL9: unrendered\nL9: creak at=end\nL9: knock gain=loud\nL9: creak at=1.9\n'
        )
        messages = dict(problems)
        self.assertIn('crosses chapters', messages[1])
        self.assertIn('not a spoken line', messages[2])
        self.assertIn('not in the library', messages[3])
        self.assertIn('not rendered', messages[4])
        self.assertIn('at=start or at=<seconds>', messages[5])
        self.assertIn('gain', messages[6])
        self.assertIn('would last', messages[7])


class TimelineTests(unittest.TestCase):
    def test_measured_lines_match_the_written_chapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for cid, seconds in (('title', 1.0), ('a', 2.0), ('b', 0.5)):
                write_wav(out / 'cache' / 'drama3' / f'{cid}.wav', seconds)
            layout = [
                (
                    'Chương 1',
                    [
                        ([('drama3', 'title', 0)], 1200, None),
                        ([('drama3', 'a', 250), ('drama3', 'b', 0)], 300, 7),
                        ([('drama3', 'b', 0)], 1700, 8),
                    ],
                )
            ]
            measured = Assembler(out).run(layout)
            self.assertEqual(measured.rate, RATE)
            ms = [(i['line'], measured.ms(i['start']), measured.ms(i['end'])) for i in measured.lines]
            self.assertEqual(ms, [(7, 2200, 4950), (8, 5250, 5750)])
            self.assertEqual(measured.marks(), [('Chương 1', 0, measured.ms(measured.frames))])
            (out / 'chapters').mkdir()
            written = Assembler(out).run(layout, out / 'chapters')
            with wave.open(str(out / 'chapters' / '01.wav'), 'rb') as w:
                self.assertEqual(w.getnframes(), measured.chapters[0][1])
            self.assertEqual(written.chapters, measured.chapters)


if __name__ == '__main__':
    unittest.main()
