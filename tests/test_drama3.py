import unittest

from viettts.engines.drama3 import parse_args


class DramaArgs(unittest.TestCase):
    def test_default_sample(self):
        args = parse_args([])
        self.assertEqual(args.text, 'Xin chào các anh, em là AI nè')
        self.assertEqual(args.seed, 42)

    def test_reference_pair_required(self):
        with self.assertRaises(SystemExit):
            parse_args(['--ref-audio', 'other.wav'])

    def test_input_and_text_exclusive(self):
        with self.assertRaises(SystemExit):
            parse_args(['--input', 'story.md', '--text', 'hello'])


if __name__ == '__main__':
    unittest.main()


class StorySafety(unittest.TestCase):
    def test_story_split_preserves_text_and_caps_size(self):
        from viettts.engines.drama3 import story_chunks

        text = ' '.join(['Xin chào các bạn.'] * 50)
        chunks = story_chunks(text)
        self.assertEqual(' '.join(chunks), text)
        self.assertTrue(all(len(c) <= 120 for c in chunks))

    def test_generation_at_cap_is_rejected(self):
        from viettts.engines.drama3 import check_frame_limit

        with self.assertRaises(RuntimeError):
            check_frame_limit(600, 600)
        check_frame_limit(599, 600)


class TaggedStory(unittest.TestCase):
    def test_keeps_scoped_and_point_tags_intact(self):
        from viettts.engines.drama3 import spoken_text, tagged_chunks

        line = '[calm] Xin chào. <whisper>Nói nhỏ thôi.</whisper> [sighs]'
        self.assertEqual(tagged_chunks(line), [line])
        self.assertEqual(spoken_text(line), 'Xin chào. Nói nhỏ thôi.')

    def test_rejects_broken_scope(self):
        from viettts.engines.drama3 import tagged_chunks

        with self.assertRaises(ValueError):
            tagged_chunks('<whisper>Xin chào.')

    def test_rejects_long_tagged_line_instead_of_splitting_scope(self):
        from viettts.engines.drama3 import tagged_chunks

        with self.assertRaises(ValueError):
            tagged_chunks('[calm] ' + 'a' * 301)
