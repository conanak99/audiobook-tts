import unittest

from viettts.text import join_kind, plain_text, split_chunks


class StoryTests(unittest.TestCase):
    def test_markdown_removes_images_urls_markup_keeps_text(self):
        source = '# Tiêu đề\n\n**Xin chào** [bạn](https://example.org).\n![](image.jpg)\n---\n> *Tạm biệt!*'
        self.assertEqual(plain_text(source), 'Tiêu đề\n\nXin chào bạn.\n\nTạm biệt!')

    def test_sentence_and_quotes_preserved(self):
        self.assertEqual(
            split_chunks('“Xin chào!” Hôm nay vui.\n\nTạm biệt.'), ['“Xin chào!”', 'Hôm nay vui.', 'Tạm biệt.']
        )

    def test_long_sentence_no_loss(self):
        text = ' '.join(['tiếng Việt'] * 100) + '.'
        chunks = split_chunks(text, 100)
        self.assertTrue(all(len(c) <= 100 for c in chunks))
        self.assertEqual(' '.join(chunks), text)

    def test_token_limit(self):
        chunks = split_chunks('Một hai ba bốn năm sáu.', 225, lambda s: len(s.split()), 3)
        self.assertTrue(all(len(c.split()) <= 3 for c in chunks))
        self.assertEqual(' '.join(chunks), 'Một hai ba bốn năm sáu.')

    def test_unbroken_word_not_discarded(self):
        text = 'a' * 600
        chunks = split_chunks(text, 225)
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(len(c) <= 225 for c in chunks))

    def test_long_sentence_is_cut_at_a_comma_not_mid_phrase(self):
        text = (
            'Sương sớm trên Hàn Sơn Phong xưa nay vẫn lặng lẽ trôi qua mấy khung cửa giấy không một tiếng động, '
            'cũng bởi thế mà ta mới chuộng gian trúc xá lưng chừng mây này.'
        )
        self.assertEqual(
            split_chunks(text, 120),
            [
                'Sương sớm trên Hàn Sơn Phong xưa nay vẫn lặng lẽ trôi qua mấy khung cửa giấy không một tiếng động,',
                'cũng bởi thế mà ta mới chuộng gian trúc xá lưng chừng mây này.',
            ],
        )

    def test_clauses_are_packed_into_few_balanced_chunks(self):
        text = 'Một hai ba, bốn năm sáu, bảy tám chín, mười mười một, mười hai mười ba.'
        chunks = split_chunks(text, 40)
        self.assertEqual(chunks, ['Một hai ba, bốn năm sáu, bảy tám chín,', 'mười mười một, mười hai mười ba.'])

    def test_comma_cuts_win_over_fewer_word_cuts(self):
        text = 'aaaa bbbb cccc dddd, eeee ffff gggg hhhh iiii, jjjj.'
        self.assertTrue(all(c.endswith((',', '.')) for c in split_chunks(text, 30)))

    def test_a_clause_without_commas_is_cut_near_its_middle(self):
        text = ' '.join(['chữ'] * 30) + '.'
        chunks = split_chunks(text, 100)
        self.assertEqual(len(chunks), 2)
        self.assertLessEqual(abs(len(chunks[0]) - len(chunks[1])), 4)

    def test_byte_limit(self):
        text = ' '.join(['được'] * 40) + '.'  # 'được' is 4 characters but 8 UTF-8 bytes
        chunks = split_chunks(text, 225, max_bytes=100)
        self.assertTrue(all(len(c.encode()) <= 100 for c in chunks))
        self.assertEqual(' '.join(chunks), text)

    def test_join_kind(self):
        self.assertEqual(join_kind('Ta hé một mắt.'), 'sentence')
        self.assertEqual(join_kind('“Xin chào!”'), 'sentence')
        self.assertEqual(join_kind('không một tiếng động,'), 'clause')
        self.assertEqual(join_kind('cũng bởi thế mà ta'), 'word')


if __name__ == '__main__':
    unittest.main()
