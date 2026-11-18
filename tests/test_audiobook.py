import unittest
from unittest import mock

from viettts.audiobook.build import (
    PAUSES_MS,
    TaggedText,
    cache_key,
    ffmeta_escape,
    ffmetadata,
    load_cast,
    match_enhance,
    plan_units,
    read_enhance,
    resolve_voice,
    shard,
    slugify,
    split_tagged,
    spoken,
    tag_problems,
    trim_edges,
    untagged,
    voice_for,
)
from viettts.audiobook.script import (
    apply_review,
    build_book,
    check_script,
    export_review,
    parse_markdown,
    read_script,
    segment,
    write_script,
)

STORY = """# Sương Nguyệt — Tập Một

Kịch bản: chỉ là mô tả.

---

## Chương 1: Mở Đầu

Sương Nguyệt sư muội bước vào phòng. Sương Nguyệt ngồi xuống cạnh ta.

![](cover.jpg)

"Sư huynh!" Sương Nguyệt gọi. "Dậy đi."

Ta hé mở một mắt. "Muội lại tới."

"Muội nhớ huynh," nàng đáp.

"Ừ."

"Thật đấy."

Nàng ghi chữ "cấm vào" lên cửa. Sương Nguyệt cười.
"""


def speakers_of(book):
    return [(q.speaker, q.rule) for c in book.chapters for p in c.paragraphs for q in p.quotes]


class ParseTests(unittest.TestCase):
    def test_structure_front_matter_and_images(self):
        title, description, chapters, images = parse_markdown(STORY)
        self.assertEqual(title, 'Sương Nguyệt — Tập Một')
        self.assertEqual(description, 'Kịch bản: chỉ là mô tả.')
        self.assertEqual([c.title for c in chapters], ['Chương 1: Mở Đầu'])
        self.assertEqual(images, ['cover.jpg'])
        self.assertFalse(any('cover.jpg' in p for p in chapters[0].paragraphs))

    def test_emphasis_markup_is_stripped(self):
        _, _, chapters, _ = parse_markdown(
            '# T\n\n## C\n\n"Nó *có tác dụng* rồi," nàng nói. Chữ *debuff*, **đậm** '
            '_nghiêng_ __gạch__ ***cả hai*** ~~xóa~~ `mã`, snake_case giữ nguyên.\n'
        )
        self.assertEqual(
            chapters[0].paragraphs[0],
            '"Nó có tác dụng rồi," nàng nói. Chữ debuff, đậm nghiêng gạch cả hai xóa mã, snake_case giữ nguyên.',
        )

    def test_no_chapters_means_one_chapter(self):
        _, _, chapters, _ = parse_markdown('# T\n\nMột đoạn.\n\nHai đoạn.')
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].paragraphs, ['Một đoạn.', 'Hai đoạn.'])

    def test_segment_and_open_quote(self):
        segs = segment('"A," nàng nói. "B')
        self.assertEqual(
            [(s.kind, s.text) for s in segs], [('quote', 'A,'), ('narration', 'nàng nói.'), ('quote', 'B')]
        )
        self.assertTrue(segs[-1].open_end)
        self.assertEqual(segment('tiếp tục." Ta gật đầu.', inside=True)[0].kind, 'quote')


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.book = build_book(STORY)

    def test_narrator_detected(self):
        self.assertEqual(self.book.narrator, 'ta')

    def test_rules(self):
        got = speakers_of(self.book)
        self.assertEqual(got[0], ('Sương Nguyệt', 'tag-after'))  # "Sư huynh!" Sương Nguyệt gọi.
        self.assertEqual(got[1][0], 'Sương Nguyệt')  # same paragraph
        self.assertEqual(got[2], ('ta', 'tag-before'))  # Ta hé mở một mắt. "..."
        self.assertEqual(got[3][1], 'tag-after')  # ..." nàng đáp.
        self.assertEqual(self.book.speakers[got[3][0]], 'female')
        self.assertEqual(got[4], ('ta', 'turn-taking'))
        self.assertEqual(got[5], ('Sương Nguyệt', 'turn-taking'))
        self.assertEqual(self.book.speakers['Sương Nguyệt'], 'female')

    def test_inline_quote_stays_narration(self):
        last = self.book.chapters[0].paragraphs[-1]
        self.assertEqual([s.kind for s in last.segments], ['narration'])
        self.assertIn('"cấm vào"', last.segments[0].text)

    def test_quote_resumed_after_comma_tag_is_dialogue(self):
        book = build_book('# T\n\n## C\n\nTa ngồi đó.\n\n"Nếu còn nằm đây," ta vừa nói vừa lau tay, "thì sẽ lạnh."\n')
        para = book.chapters[0].paragraphs[-1]
        self.assertEqual([s.kind for s in para.segments], ['quote', 'narration', 'quote'])
        self.assertEqual([q.speaker for q in para.quotes], ['ta', 'ta'])

    def test_kinship_and_adverb_tags(self):
        book = build_book(
            '# T\n\n## C\n\nTôi ngồi đó. Tôi đợi tôi.\n\n"Con về rồi à?" mẹ tôi hỏi.\n\n'
            '"Vâng," cuối cùng em cũng đáp.\n'
        )
        got = speakers_of(book)
        self.assertEqual(got[0][0], 'mẹ tôi')
        self.assertEqual(book.speakers['mẹ tôi'], 'female')
        self.assertEqual(book.speakers[got[1][0]], 'female')


class ScriptTests(unittest.TestCase):
    def test_round_trip_and_review(self):
        book = build_book(STORY)
        text = write_script(book, '/tmp/cover.jpg')
        script = read_script(text)
        self.assertEqual(script.meta['title'], 'Sương Nguyệt — Tập Một')
        self.assertEqual(script.meta['cover'], '/tmp/cover.jpg')
        self.assertEqual(script.narrator, 'ta')
        lines = [line for _, paras in script.chapters for p in paras for line in p]
        self.assertEqual(sum(line.needs_review for line in lines), 2)  # the two turn-taking guesses
        review, _, items = export_review(text)
        self.assertEqual(items, 3)  # + confirm Sương Nguyệt's gender
        self.assertIn('## SPEAKER Sương Nguyệt (guess: female)', review)
        target = next(line for line in lines if line.needs_review)
        edited = review.replace(f'=> L{target.number}: ta', f'=> L{target.number}: new: Lão Cố | male')
        updated, changes = apply_review(text, edited)
        self.assertEqual(changes, 3)
        again = read_script(updated)
        self.assertEqual(again.speakers['Lão Cố'], 'male')
        relabeled = [line for _, paras in again.chapters for p in paras for line in p if line.text == target.text][0]
        self.assertEqual(relabeled.label, 'Lão Cố')
        self.assertFalse(any(line.needs_review for _, paras in again.chapters for p in paras for line in p))

    def test_compact_answers_and_batches(self):
        text = write_script(build_book(STORY))
        _, written, total = export_review(text, limit=1)
        self.assertEqual(total, 3)
        self.assertGreaterEqual(written, 1)
        lines = [line for _, paras in read_script(text).chapters for p in paras for line in p if line.needs_review]
        answers = f'L{lines[0].number}: ta\nL{lines[1].number}: Sương Nguyệt\nSPEAKER Sương Nguyệt: female\n'
        updated, changes = apply_review(text, answers)
        self.assertEqual(changes, 3)
        self.assertIn('@speaker Sương Nguyệt female\n', updated)
        self.assertEqual(export_review(updated, limit=0)[2], 0)
        with self.assertRaises(ValueError):
            apply_review(text, 'L1: ta\n')  # line 1 is @title, not a dialogue line

    def test_relabel_moves_every_line_of_a_speaker(self):
        text = (
            '@title T\n@speaker ta male narrator\n@speaker Zinie female?\n@speaker female female\n## C\n'
            '[female] A\n[female?] B\n[ta] C\n'
        )
        updated, changes = apply_review(text, 'RELABEL female: Zinie\nSPEAKER Zinie: female\n')
        self.assertEqual(changes, 3)
        self.assertIn('[Zinie] A\n[Zinie?] B\n[ta] C', updated)  # B is still a guess
        self.assertIn('@speaker Zinie female\n', updated)
        with self.assertRaises(ValueError):
            apply_review(text, 'RELABEL female: Nobody\n')

    def test_check_flags_suspicious_lines(self):
        text = (
            '@title T\n@speaker ta male narrator\n@speaker Sương Nguyệt female\n## C\n'
            '[ta] Chàng đừng đi mà.\n[Sương Nguyệt] Nương tử của ta đâu?\n'
            '[narrator] Nàng nói "đây là một câu thoại rất dài bị bỏ sót mất" rồi cười.\n'
        )
        found = [m for _, m in check_script(text)]
        self.assertTrue(any('male speaker' in m for m in found))
        self.assertTrue(any('female speaker' in m for m in found))
        self.assertTrue(any('long quoted passage' in m for m in found))

    def test_apply_review_rejects_unknown_speaker(self):
        text = write_script(build_book(STORY))
        review, _, _ = export_review(text)
        bad = review.replace(': ta\n', ': Nobody\n', 1)
        with self.assertRaises(ValueError):
            apply_review(text, bad)


class BuildHelperTests(unittest.TestCase):
    def test_voices_and_units(self):
        script = read_script(write_script(build_book(STORY)))
        voices = {'narrator': 'N', 'male': 'M', 'female': 'F'}
        ((title, units),) = plan_units(script, voices, 'fail')
        self.assertEqual(units[0], ('narrator', 'Sương Nguyệt — Tập Một', PAUSES_MS['title']))
        self.assertEqual(units[1], ('narrator', 'Chương 1: Mở Đầu', PAUSES_MS['title']))
        self.assertIn(('female', 'Sư huynh!', PAUSES_MS['segment']), units)
        self.assertIn(('narrator', 'Muội lại tới.', PAUSES_MS['paragraph']), units)  # the MC speaks as the narrator
        ((_, own),) = plan_units(script, {**voices, 'mc': 'C'}, 'fail')  # the cast gave the MC a voice
        self.assertIn(('mc', 'Muội lại tới.', PAUSES_MS['paragraph']), own)
        self.assertIn(('narrator', 'Chương 1: Mở Đầu', PAUSES_MS['title']), own)
        self.assertEqual(voice_for('ta', {'ta': 'male'}, {**voices, 'ta': 'X'}, 'fail', 'ta'), 'ta')
        self.assertEqual(units[-1][2], PAUSES_MS['chapter_end'])
        self.assertEqual(voice_for('narrator', {}, voices, 'fail'), 'narrator')
        with self.assertRaises(SystemExit):
            voice_for('Ai đó', {'Ai đó': '?'}, voices, 'fail')
        self.assertEqual(voice_for('Ai đó', {'Ai đó': '?'}, voices, 'narrator'), 'narrator')

    def test_lines_without_words_are_skipped(self):
        text = write_script(build_book(STORY))
        old = '[narrator] Ta hé mở một mắt.'
        self.assertIn(old, text)
        text = text.replace(old, '[narrator] ▰▰▰▱▱\n[narrator] [🔒 ??? —\n' + old, 1)
        ((_, units),) = plan_units(read_script(text), {'narrator': 'N', 'male': 'M', 'female': 'F'}, 'fail')
        self.assertFalse(any(t in ('▰▰▰▱▱', '[🔒 ??? —') for _, t, _ in units))
        self.assertIn(('narrator', 'Ta hé mở một mắt.', PAUSES_MS['segment']), units)

    def test_drama3_cache_follows_model_revision(self):
        from unittest import mock

        from viettts.audiobook import build as run_audiobook

        vieneu, drama3 = cache_key('vieneu', 'Hải Đăng', 'Chào.'), cache_key('drama3', {'ref': 'a'}, 'Chào.')
        with mock.patch.object(run_audiobook, 'DRAMA3_REVISION', 'older'):
            self.assertEqual(cache_key('vieneu', 'Hải Đăng', 'Chào.'), vieneu)
            self.assertNotEqual(cache_key('drama3', {'ref': 'a'}, 'Chào.'), drama3)

    def test_voice_engines_and_presets(self):
        self.assertEqual(resolve_voice('Thiện Minh'), ('vieneu', 'Thiện Minh'))
        engine, voice = resolve_voice('lynasa')  # an onboarded voice id
        self.assertEqual(engine, 'drama3')
        self.assertTrue(voice['ref_audio'][0].endswith('references/voices/lynasa/reference-1.wav'))
        self.assertTrue(voice['ref_text'][0].startswith('Thì phải nổi tiếng'))  # one transcript per clip
        self.assertEqual(resolve_voice({'engine': 'vieneu', 'voice': 'Trúc Ly'}), ('vieneu', 'Trúc Ly'))
        self.assertEqual(resolve_voice('references/vieneu-hai-dang.wav')[0], 'drama3')  # make-ref output
        with self.assertRaises(SystemExit):
            resolve_voice('/tmp/some_clip.wav')  # raw audio must be onboarded first
        with self.assertRaises(SystemExit):
            resolve_voice('Not A Voice')

    def test_the_cast_is_the_only_voice_choice(self):
        import json
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace

        from viettts.paths import ROOT

        def cast(data=None, path=None):
            if data is not None:
                path = Path(tempfile.mkdtemp()) / 'cast.json'
                path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            return load_cast(SimpleNamespace(cast=path))

        preset, voices = cast()  # no --cast: the mixed preset, as casts/mixed.json spells out
        self.assertEqual(preset, 'mixed')
        self.assertEqual(voices, cast(path=ROOT / 'casts' / 'mixed.json')[1])
        self.assertEqual(voices['narrator'], ('vieneu', 'Thiện Minh'))
        self.assertEqual(voices['female'][0], 'drama3')
        self.assertEqual(cast(path=ROOT / 'casts' / 'vieneu.json'), cast({'engine': 'vieneu'}))
        self.assertEqual(cast({'engine': 'vieneu'})[1]['female'], ('vieneu', 'Ngọc Huyền'))
        self.assertEqual(cast(path=ROOT / 'casts' / 'drama3.json')[0], 'drama3')
        _, voices = cast({'voices': {'mc': 'Đức Trí', 'female': 'lynasa', 'Sương Nguyệt': 'Thùy Dung'}})
        self.assertEqual(voices['mc'], ('vieneu', 'Đức Trí'))
        self.assertEqual(voices['male'], ('vieneu', 'Hải Đăng'))  # roles left out keep the preset's voice
        self.assertEqual(voice_for('ta', {'ta': 'male'}, voices, 'fail', 'ta'), 'mc')
        self.assertEqual(voice_for('Sương Nguyệt', {'Sương Nguyệt': 'female'}, voices, 'fail', 'ta'), 'Sương Nguyệt')
        with self.assertRaises(SystemExit):
            cast({'engine': 'fast'})

    def test_cast_keys_that_match_nothing_are_reported(self):
        from viettts.audiobook.build import unmatched_cast_keys

        script = read_script(write_script(build_book(STORY)))  # speakers: ta, Sương Nguyệt
        voices = dict.fromkeys(['narrator', 'mc', 'male', 'female', 'Sương Nguyệt', 'ta', 'Suong Nguyet'], 'v')
        self.assertEqual(unmatched_cast_keys(voices, script), ['Suong Nguyet'])

    def test_unknown_line_fails_unless_allowed(self):
        script = read_script('@title T\n## C\n[?] Ai nói?\n')
        with self.assertRaises(SystemExit):
            plan_units(script, {'narrator': 'N', 'male': 'M', 'female': 'F'}, 'fail')

    def test_ffmetadata(self):
        meta = ffmetadata({'title': 'A=B; #1', 'genre': 'Audiobook', 'track': ''}, [('Chương 1', 0, 1500)])
        self.assertIn('title=A\\=B\\; \\#1', meta)
        self.assertNotIn('track=', meta)
        self.assertIn('[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1500\ntitle=Chương 1', meta)
        self.assertEqual(ffmeta_escape('a\nb'), 'a\\\nb')

    def test_chapter_spec(self):
        from viettts.audiobook.build import parse_chapter_spec

        self.assertEqual(parse_chapter_spec('6', 11), [6])
        self.assertEqual(parse_chapter_spec('1, 6-8,7', 11), [1, 6, 7, 8])
        for bad in ('0', '12', '8-6', 'x', '6-'):
            with self.assertRaises(SystemExit):
                parse_chapter_spec(bad, 11)

    def test_volume_from_folder_and_title(self):
        from viettts.audiobook.build import source_volume, volume_title

        self.assertEqual(source_volume('/s/_archived/meimei_v2/story_vn.md'), 2)
        self.assertEqual(source_volume('/s/foo_vol3/story_vn.md'), 3)
        self.assertIsNone(source_volume('/s/dev/story_vn.md'))
        self.assertEqual(volume_title('Mị Mị — Khi Ngọn Núi', 2), ('Mị Mị', 'Mị Mị v2 - Khi Ngọn Núi'))
        self.assertEqual(volume_title('Mị Mị v2 — Khi Ngọn Núi', 2), ('Mị Mị', 'Mị Mị v2 - Khi Ngọn Núi'))
        self.assertEqual(volume_title('Sương Nguyệt', 3), ('Sương Nguyệt', 'Sương Nguyệt v3'))
        self.assertEqual(volume_title('Sương Nguyệt', None), ('', 'Sương Nguyệt'))

    def test_frame_budget(self):
        from viettts.audiobook.build import frame_budget

        self.assertEqual(frame_budget('Người,'), 128)
        self.assertEqual(frame_budget('a' * 60 + '... b.'), 66 * 3 + 40 + 15 * 4)  # '...' is 3 breaks too
        self.assertEqual(frame_budget('a' * 500), 600)

    def test_text_helpers(self):
        self.assertEqual(slugify('Sương Nguyệt — Đỉnh Hàn Sơn'), 'suong-nguyet-dinh-han-son')
        self.assertEqual(spoken('Nàng ghi "cấm vào" nhé~'), 'Nàng ghi cấm vào nhé')


class EnhanceTests(unittest.TestCase):
    def test_tag_problems(self):
        plain = 'Ta không sao. Thật mà. Đi đi.'
        self.assertEqual(
            tag_problems(
                '[barely holding it together] Ta không sao. [shaky breath] Thật mà. <whisper>Đi đi.</whisper>', plain
            ),
            [],
        )
        self.assertEqual(tag_problems(plain, plain), [])
        for bad in [
            '[sad] Ta ổn. Thật mà. Đi đi.',  # words changed
            'Ta không sao. Thật mà. <shout>Đi đi.</shout>',  # unsupported tag
            'Ta không sao. Thật mà. <whisper>Đi đi.',  # not closed
            'Ta <soft>không <fast>sao.</fast></soft> Thật mà. Đi đi.',  # nested
            '[] Ta không sao. Thật mà. Đi đi.',
            '[calm Ta không sao. Thật mà. Đi đi.',
            '[' + 'very ' * 13 + '] Ta không sao. Thật mà. Đi đi.',
            'Ta không sao. Thật mà. <whisper></whisper> Đi đi.',
        ]:
            self.assertTrue(tag_problems(bad, plain), bad)

    def test_split_keeps_tags_whole_and_carries_the_direction(self):
        text = '[leans in, conspiratorial] ' + ', '.join(['một hai ba bốn năm sáu bảy'] * 8) + '. [small laugh]'
        chunks = split_tagged(text, 80)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c.startswith('[leans in, conspiratorial] ') for c in chunks))
        self.assertTrue(chunks[-1].endswith('. [small laugh]'))  # a tag-only piece stays with its words
        self.assertEqual(untagged(' '.join(chunks)), untagged(text))

    def test_split_carries_the_current_direction_but_never_a_sound(self):
        sentence = ', '.join(['một hai ba bốn năm'] * 3)
        chunks = split_tagged(f'[weary] {sentence}. [sighs] {sentence}. [suddenly bright] {sentence}. {sentence}.', 200)
        self.assertEqual(
            [c[: c.index(' một')] for c in chunks],
            ['[weary]', '[weary] [sighs]', '[suddenly bright]', '[suddenly bright]'],
        )
        chunks = split_tagged(
            f'[breathless, intimate] {sentence}. [soft moan] {sentence}. [laughing] {sentence}. {sentence}.', 200
        )
        self.assertEqual(
            [c[: c.index(' một')] for c in chunks],
            ['[breathless, intimate]', '[breathless, intimate] [soft moan]', '[laughing]', '[laughing]'],
        )

    def test_sounds_and_directions(self):
        from viettts.audiobook.build import is_sound

        for sound in ['[sighs]', '[small laugh]', '[shaky breath]', '[soft moan]', '[gasps]', '[pause]', '[pants]']:
            self.assertTrue(is_sound(sound), sound)
        for direction in [
            '[breathless, intimate]',
            '[laughing]',
            '[breathing heavily]',
            '[low, sultry]',
            '[whispering]',
            '[teasing]',
        ]:
            self.assertFalse(is_sound(direction), direction)

    def test_split_closes_and_reopens_a_paired_tag(self):
        chunks = split_tagged('Nghe này. <whisper>Đừng nói với ai. Bí mật đấy.</whisper> Rồi.', 200)
        self.assertEqual(
            chunks, ['Nghe này.', '<whisper>Đừng nói với ai.</whisper>', '<whisper>Bí mật đấy.</whisper> Rồi.']
        )

    def test_plain_text_splits_as_before(self):
        from viettts.text import split_chunks

        text = 'Một câu. Hai câu, ba câu.'
        self.assertEqual(split_tagged(text, 10), split_chunks(text, 10))

    def test_entries_follow_moved_lines_and_only_drama3_uses_them(self):
        text = write_script(build_book(STORY))
        script = read_script(text)
        line = next(line for _, ps in script.chapters for p in ps for line in p if line.text == 'Sư huynh!')
        entries = read_enhance(f'# comment\nL{line.number}: [bright, teasing] Sư huynh!\nL999: [x] Không có.\n')
        moved = read_script(text.replace('\n@speaker', '\n@speaker Ai female\n@speaker', 1))  # one line down
        matched, stale = match_enhance(moved, entries)
        self.assertEqual(matched, {line.number + 1: '[bright, teasing] Sư huynh!'})
        self.assertEqual(stale, [(999, '[x] Không có.')])
        ((_, units),) = plan_units(
            script,
            {'narrator': ('vieneu', 'N'), 'male': ('vieneu', 'M'), 'female': ('drama3', {})},
            'fail',
            enhanced={line.number: entries[line.number]},
        )
        self.assertIn(('female', '[bright, teasing] Sư huynh!', PAUSES_MS['segment']), units)
        self.assertTrue(any(isinstance(t, TaggedText) for _, t, _ in units))
        ((_, units),) = plan_units(
            script,
            {'narrator': 'N', 'male': 'M', 'female': ('vieneu', 'F')},
            'fail',
            enhanced={line.number: entries[line.number]},
        )
        self.assertIn(('female', 'Sư huynh!', PAUSES_MS['segment']), units)  # VieNeu would read the tags


if __name__ == '__main__':
    unittest.main()


try:
    import numpy as np
except ImportError:  # the orchestrator runs on plain python3; audio helpers run in the engine envs
    np = None


class TrimTests(unittest.TestCase):
    def test_trim_edges_keeps_a_short_margin_and_the_speech(self):
        from array import array

        rate = 48000
        speech = array('h', [8000, -8000] * (rate // 4))  # 0.5 s of loud audio
        pcm = (array('h', [3] * (rate // 5)) + speech + array('h', [0] * (rate // 2))).tobytes()
        out = trim_edges(pcm, rate, 1, 2)
        self.assertAlmostEqual(len(out) / 2 / rate, 0.5 + 0.06, delta=0.011)
        self.assertIn(speech.tobytes()[:2000], out)

    def test_silent_or_stereo_audio_is_kept(self):
        silent = bytes(9600)
        self.assertEqual(trim_edges(silent, 48000, 1, 2), silent)
        self.assertEqual(trim_edges(b'\1\2' * 100, 48000, 2, 2), b'\1\2' * 100)


class ShardTests(unittest.TestCase):
    def test_shards_balance_characters_and_keep_every_job(self):
        jobs = [dict(id=str(i), text='x' * n) for i, n in enumerate([200, 10, 150, 40, 90, 60, 5, 120])]
        parts = shard(jobs, 3)
        self.assertEqual(sorted(j['id'] for p in parts for j in p), sorted(j['id'] for j in jobs))
        sizes = [sum(len(j['text']) for j in p) for p in parts]
        self.assertLessEqual(max(sizes) - min(sizes), 60)

    def test_never_more_shards_than_jobs(self):
        self.assertEqual(len(shard([dict(id='a', text='hi')], 4)), 1)


class VieneuBackendTests(unittest.TestCase):
    def test_requests_are_seeded_per_job_and_keep_the_pieces_whole(self):
        from viettts.engines.vieneu_gguf import requests_for

        job = dict(id='abc123', text='Một. Hai.', voice='Thiện Minh')
        first = requests_for(7, job, ['mˈot.', 'hˈaːj.'], '/v/ref_codes.txt', '/v/speaker.emb.txt')
        self.assertEqual([r['id'] for r in first], ['000007-0', '000007-1'])
        self.assertEqual(first[0]['options']['reference_codes_file'], '/v/ref_codes.txt')
        self.assertEqual(first[0]['options']['seed'], requests_for(9, job, ['x'], 'c', 'e')[0]['options']['seed'])
        self.assertNotEqual(
            first[0]['options']['seed'], requests_for(7, dict(job, id='other'), ['x'], 'c', 'e')[0]['options']['seed']
        )
        self.assertGreater(int(first[0]['options']['text_chunk_size']), 225 * 4)

    def test_gguf_needs_apple_silicon_and_audio_cpp(self):
        from viettts.engines import vieneu_gguf

        with mock.patch.object(vieneu_gguf.platform, 'system', return_value='Linux'):
            self.assertIn('Apple Silicon', vieneu_gguf.unavailable())
        with (
            mock.patch.object(vieneu_gguf.platform, 'system', return_value='Darwin'),
            mock.patch.object(vieneu_gguf.platform, 'machine', return_value='arm64'),
        ):
            with mock.patch.object(vieneu_gguf.shutil, 'which', return_value=None):
                self.assertIn('brew install audio-cpp', vieneu_gguf.unavailable())
            with mock.patch.object(vieneu_gguf.shutil, 'which', return_value='/opt/homebrew/bin/audiocpp_cli'):
                self.assertIsNone(vieneu_gguf.unavailable())

    def test_only_vieneu_workers_get_the_backend(self):
        import tempfile
        from pathlib import Path

        from viettts.audiobook import build

        process = mock.Mock(stdout=iter([]), wait=mock.Mock(return_value=0))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(build.subprocess, 'Popen', return_value=process):
            for engine in ('vieneu', 'drama3'):
                build.run_workers(engine, [dict(id='a', text='hi')], Path(tmp), 2, 1, mock.Mock(), 'onnx')
            commands = [call.args[0] for call in build.subprocess.Popen.call_args_list]
        self.assertEqual(commands[0][-2:], ['--backend', 'onnx'])
        self.assertNotIn('--backend', commands[1])


@unittest.skipIf(np is None, 'numpy is only installed in the engine environments')
class AudioHelperTests(unittest.TestCase):
    def test_gguf_results_stay_in_order_and_a_crash_skips_only_its_chunk(self):
        import json
        import sys
        import tempfile
        import types
        from pathlib import Path

        from viettts.engines import vieneu_gguf

        sessions = []

        def fake_cli(command, status):  # finishes the first request, then crashes on the second, once
            sequence = json.loads(Path(command[command.index('--request-sequence') + 1]).read_text('utf-8'))
            out = Path(command[command.index('--out-dir') + 1])
            sessions.append([r['id'] for r in sequence['requests']])
            for n, request in enumerate(sequence['requests']):
                if len(sessions) == 1 and n == 1:
                    yield 'GGML_ASSERT failed'
                    status['code'] = 134
                    return
                (out / f'{request["id"]}.wav').touch()
                yield f'audio_out={out / request["id"]}.wav'
            status['code'] = 0

        def normalize(text):
            pieces = [p.strip() + '.' for p in text.split('.') if p.strip()]
            return pieces, ['sentence'] * (len(pieces) - 1)

        fakes = {
            'soundfile': types.SimpleNamespace(read=lambda *a, **k: (np.ones((10, 2), np.float32), 48000)),
            'vieneu_utils': types.ModuleType('vieneu_utils'),
            'vieneu_utils.core_utils': types.SimpleNamespace(
                gaps_to_silence=lambda gaps: [0.1] * len(gaps),
                join_audio_chunks=lambda waves, rate, silence_ps: np.concatenate(waves),
            ),
            'vieneu_utils.phonemize_text': types.SimpleNamespace(
                normalize_to_chunks_v3_with_gaps=normalize, phonemize_text_with_emotions=str.lower
            ),
        }
        jobs = [dict(id=f'j{i}', text=t, voice='Thiện Minh') for i, t in enumerate(['A. B.', 'C.', '', 'D.'])]
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(sys.modules, fakes),
            mock.patch.object(vieneu_gguf, 'lines', fake_cli),
            mock.patch.object(vieneu_gguf, 'ensure_model', return_value=Path('m.gguf')),
            mock.patch.object(vieneu_gguf, 'voice_files', return_value=('c', 'e')),
        ):
            results = list(vieneu_gguf.synthesize(jobs, 2, Path(tmp)))
        self.assertEqual([job['id'] for job, *_ in results], ['j0', 'j1', 'j2', 'j3'])
        self.assertIn('134', results[0][3])  # both pieces of j0 are needed; its second one crashed
        self.assertEqual(len(results[1][1]), 10)  # the next session resumes after the crashed job
        self.assertIn('nothing to read', results[2][3])
        self.assertIsNotNone(results[3][1])
        self.assertEqual(sessions, [['000000-0', '000000-1', '000001-0', '000003-0'], ['000001-0', '000003-0']])

    def test_squeeze_shortens_only_long_inner_pauses(self):
        from viettts.audiobook.build import longest_silence, squeeze

        r = 44100

        def tone(s):
            return (0.3 * np.sin(np.arange(int(r * s)) * 0.05)).astype(np.float32)

        def gap(s):
            return np.zeros(int(r * s), np.float32)

        x = np.concatenate([gap(0.3), tone(1), gap(3), tone(1), gap(0.6), tone(0.5), gap(0.2)])
        y = squeeze(x, r, np)
        self.assertAlmostEqual(len(y) / r, len(x) / r - 2.5, delta=0.05)
        self.assertLessEqual(longest_silence(y, r, np), 0.61)
