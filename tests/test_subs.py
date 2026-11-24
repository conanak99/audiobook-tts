import importlib.util
import tempfile
import unittest
from pathlib import Path

from viettts.subs import cues as plan
from viettts.subs.cli import default_out, find_tracks

ROOT = Path(__file__).resolve().parents[1]


def load_parse_cues():
    spec = importlib.util.spec_from_file_location(
        'parse_cues', ROOT / '.opencode/skills/translate/scripts/parse_cues.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PlanTests(unittest.TestCase):
    def test_merge_joins_breath_gaps_but_not_pauses_or_long_lines(self):
        spans = [(0.0, 1.0), (1.1, 2.0), (3.0, 4.0), (4.1, 15.5)]
        self.assertEqual(plan.merge_spans(spans), [(0.0, 2.0), (3.0, 4.0), (4.1, 15.5)])

    def test_split_long_keeps_clips_inside_the_whisper_window(self):
        self.assertEqual(plan.split_long([(0.0, 10.0)]), [(0.0, 10.0)])
        parts = plan.split_long([(10.0, 70.0)])
        self.assertEqual(len(parts), 3)
        self.assertEqual((parts[0][0], parts[-1][1]), (10.0, 70.0))
        self.assertTrue(all(b - a <= plan.MAX_CLIP for a, b in parts))

    def test_blank_drops_punctuation_but_keeps_moans(self):
        for text in ('…', '…?', ' 。、 ', '!?', ''):
            self.assertTrue(plan.is_blank(text), text)
        for text in ('ふふっ', 'んっ…', 'ちゅっ'):
            self.assertFalse(plan.is_blank(text), text)

    def test_loop_detects_stuck_decoder(self):
        self.assertTrue(plan.is_loop('決起羅羅羅羅羅羅羅羅羅羅'))
        self.assertTrue(plan.is_loop('ちょっと' * 8))
        self.assertFalse(plan.is_loop('もっともっと強くなってもらおうか'))

    def test_speakers_are_numbered_by_first_appearance(self):
        self.assertEqual(plan.label_speakers(['S02', 'S01', 'S02', None]), ['S1', 'S2', 'S1', None])

    def test_source_md_round_trips_through_the_translate_parser(self):
        cues = [
            {'start': 1.63, 'end': 3.54, 'speaker': 'S1', 'text': 'アオハル'},
            {'start': 3661.5, 'end': 3662.0, 'speaker': 'S2', 'text': 'ふふっ'},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.md'
            path.write_text(plan.source_md([('01. 始まり', cues), ('02', cues[:1])]), encoding='utf-8')
            tracks = load_parse_cues().parse_source(path)
        self.assertEqual([t for t, _ in tracks], ['01. 始まり', '02'])
        first = tracks[0][1]
        self.assertEqual([c['text'] for c in first], ['S1: アオハル', 'S2: ふふっ'])
        self.assertEqual(first[1]['start_str'], '01:01:01.500')
        self.assertAlmostEqual(first[1]['gap'], 3661.5 - 3.54)

    def test_chapter_title_drops_the_track_number(self):
        for stem, title in [
            ('01. 強化合宿の始まり…♡', '強化合宿の始まり…♡'),
            ('track00_标题朗读', '标题朗读'),
            ('Track 3 - Bath', 'Bath'),
            ('#05 耳かき', '耳かき'),
            ('02', '02'),
            ('おまけ', 'おまけ'),
        ]:
            self.assertEqual(plan.chapter_title(stem), title)

    def test_vtt_without_speakers_has_plain_text(self):
        text = plan.vtt([{'start': 0, 'end': 1.2, 'text': 'この程度か'}])
        self.assertEqual(text, 'WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.200\nこの程度か\n')


class CliTests(unittest.TestCase):
    def test_folders_list_audio_in_natural_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('10.mp3', '2.mp3', '1.wav', 'cover.jpg'):
                (Path(tmp) / name).touch()
            self.assertEqual([p.name for p in find_tracks([Path(tmp)])], ['1.wav', '2.mp3', '10.mp3'])

    def test_japanese_names_keep_a_readable_output_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            track = Path(tmp) / '01. 強化合宿の始まり…♡.mp3'
            track.touch()
            self.assertEqual(default_out([track]).name, '01.-強化合宿の始まり…♡')
            self.assertEqual(default_out([Path(tmp) / 'Elf Paradise.mp3']).name, 'elf-paradise')
            folder = Path(tmp) / 'エルフ作品'
            folder.mkdir()
            self.assertEqual(default_out([folder]).name, 'エルフ作品')


if __name__ == '__main__':
    unittest.main()
