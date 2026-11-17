#!/usr/bin/env python3
"""Turn a Markdown story into a speaker-attributed audiobook script (rules only, stdlib only)."""

import html
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

NARRATION = 'narrator'
UNKNOWN = '?'

# Words are matched case-insensitively at word boundaries; longer phrases are tried first.
FEMALE_PRONOUNS = [
    'cô ấy',
    'cô ta',
    'cô nàng',
    'cô bé',
    'cô gái',
    'nàng ta',
    'nàng',
    'cô',
    'ả',
    'em ấy',
    'ẻm',
    'con bé',
    'tỷ tỷ',
    'sư tỷ',
    'tỷ',
    'sư muội',
    'bà ấy',
    'bà ta',
    'bà',
    'chị ấy',
    'chị ta',
    'chị',
    'dì',
    'thiếu nữ',
    'nữ nhân',
    'mỹ nhân',
    'tiểu nha đầu',
    'nha đầu',
    'nữ tu',
    'phu nhân',
    'tiên tử',
    'cô nương',
    'muội ấy',
    'tỷ ấy',
]
# Family/role nouns that act as a speaker: "mẹ tôi nói", "phụ thân ta trầm giọng".
KIN = {
    **{
        k: 'female'
        for k in [
            'mẹ',
            'mẫu thân',
            'bà nội',
            'bà ngoại',
            'nương',
            'mẫu hậu',
            'vợ',
            'chị gái',
            'em gái',
            'cô gái',
            'người phụ nữ',
            'nữ hoàng',
            'hoàng hậu',
            'công chúa',
        ]
    },
    **{
        k: 'male'
        for k in [
            'bố',
            'cha',
            'phụ thân',
            'ông nội',
            'ông ngoại',
            'phụ hoàng',
            'chồng',
            'anh trai',
            'em trai',
            'người đàn ông',
            'hoàng đế',
            'bệ hạ',
            'hoàng thượng',
            'lão già',
        ]
    },
}
MALE_PRONOUNS = [
    'anh ấy',
    'anh ta',
    'hắn ta',
    'hắn',
    'gã',
    'lão',
    'ông ấy',
    'ông ta',
    'ông',
    'cậu ta',
    'cậu ấy',
    'chàng',
    'y',
    'thiếu niên',
    'nam nhân',
    'chú',
    'huynh ấy',
    'đệ ấy',
    'ổng',
    'anh',
]
# Phrases that contain a narrator pronoun but do not refer to the narrator.
NOT_NARRATOR = [
    'chúng ta',
    'chúng tôi',
    'anh ta',
    'cô ta',
    'hắn ta',
    'nàng ta',
    'bà ta',
    'ông ta',
    'cậu ta',
    'chị ta',
    'người ta',
    'bọn ta',
    'các ta',
]
NARRATOR_PRONOUNS = ['ta', 'tôi']

# Cues inside a quote: she calls him "chàng"/"huynh", he calls her "nàng"/"nương tử". Self/other-ambiguous
# words ("muội", "em", "anh") are left out on purpose.
FEMALE_SPEAKER_CUES = [
    'sư huynh',
    'huynh',
    'thiếp',
    'tiểu nữ',
    'bổn cô nương',
    'nô tỳ',
    'phu quân',
    'tướng công',
    'công tử',
    'chàng',
]
MALE_SPEAKER_CUES = ['nàng', 'nương tử', 'cô nương', 'tại hạ', 'lão phu', 'nha đầu', 'tiểu yêu tinh']
# Titles written after a name: "Sương sư tỷ", "Liễu lão", "Noãn tỷ", "Huyền Cơ môn chủ".
FEMALE_TITLES = [
    'phu nhân',
    'công chúa',
    'sư tỷ',
    'sư muội',
    'tiên tử',
    'cô nương',
    'nương nương',
    'tiểu thư',
    'thánh nữ',
    'nữ hoàng',
    'hoàng hậu',
    'quận chúa',
    'tỷ tỷ',
    'tỷ',
    'muội muội',
    'muội',
]
MALE_TITLES = [
    'sư huynh',
    'sư đệ',
    'công tử',
    'lão',
    'vương gia',
    'hoàng đế',
    'bảo chủ',
    'thái tử',
    'hoàng tử',
    'ca ca',
    'đại ca',
    'huynh',
    'đệ',
    'thiếu gia',
]
NAME_TITLES = sorted(
    set(
        FEMALE_TITLES
        + MALE_TITLES
        + [
            'trưởng lão',
            'môn chủ',
            'tông chủ',
            'chưởng môn',
            'đại sư',
            'thủ tọa',
            'sư phụ',
            'sư tôn',
            'nhi',
            'đại nhân',
            'tiền bối',
        ]
    ),
    key=len,
    reverse=True,
)
PRE_TITLES = {
    **{t: 'female' for t in ['cô', 'bà', 'chị', 'bé', 'dì', 'cô bé', 'con bé', 'nàng', 'cô nàng', 'mẹ']},
    **{t: 'male' for t in ['anh', 'ông', 'chú', 'lão', 'cậu', 'gã', 'hắn', 'bố', 'thằng', 'cha']},
}
NAME_STOPWORDS = {
    'Chương',
    'Hồi',
    'Chapter',
    'Rồi',
    'Nhưng',
    'Và',
    'Khi',
    'Lúc',
    'Sau',
    'Trước',
    'Ngay',
    'Thế',
    'Vậy',
    'Nếu',
    'Dù',
    'Dẫu',
    'Có',
    'Không',
    'Một',
    'Hai',
    'Ba',
    'Đó',
    'Đây',
    'Này',
    'Ôi',
    'Trời',
    'Chúa',
    'Tổ',
    'Ừ',
    'Vâng',
    'Dạ',
    'Được',
    'Thật',
    'Sư',
    'Lý',
    'Mau',
    'Đừng',
}

WORD = r'[^\W\d_]'


def capitalized_run(text: str, limit: int = 3) -> str:
    """Leading run of capitalized words: 'Huyền Cơ môn chủ' -> 'Huyền Cơ'."""
    words: list[str] = []
    for m in re.finditer(rf'({WORD}+)(\s+|$)', text):
        if m.start() != sum(len(w) for w in words) or not m[1][0].isupper() or len(words) == limit:
            break
        words.append(m[0])
    return ''.join(words).strip()


def fold(text):
    return unicodedata.normalize('NFC', text).lower()


def phrase_at(text, phrases):
    """Return the phrase that starts text (whole words), or None."""
    low = fold(text)
    for phrase in sorted(phrases, key=len, reverse=True):
        if low.startswith(phrase) and (len(low) == len(phrase) or not re.match(WORD, low[len(phrase)])):
            return phrase
    return None


def contains(text, phrases):
    low = fold(text)
    return [p for p in phrases if re.search(rf'(?<!{WORD}){re.escape(p)}(?!{WORD})', low)]


@dataclass
class Segment:
    kind: str  # 'narration' or 'quote'
    text: str
    speaker: str = NARRATION
    rule: str = ''
    open_end: bool = False  # quote not closed in this paragraph


@dataclass
class Paragraph:
    segments: list

    @property
    def quotes(self):
        return [s for s in self.segments if s.kind == 'quote']


@dataclass
class Chapter:
    title: str
    paragraphs: list = field(default_factory=list)


@dataclass
class Book:
    title: str
    description: str
    chapters: list
    images: list
    narrator: str = 'ta'
    speakers: dict = field(default_factory=dict)  # id -> gender ('male'/'female'/'?')


def clean_inline(text):
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'(\*\*|__|\*|(?<![\w])_(?=\S)|(?<=\S)_(?![\w])|`|~~)', '', text)
    text = html.unescape(text.replace('“', '"').replace('”', '"'))
    return ' '.join(text.split())


def parse_markdown(markdown):
    """Split Markdown into title, front matter, chapters (## headings) and paragraphs."""
    markdown = re.sub(r'<!--.*?-->', '', markdown, flags=re.S)
    markdown = re.sub(r'(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', markdown)
    images = re.findall(r'!\[[^\]]*\]\(([^)\s]+)', markdown)
    title, front, chapters = '', [], []
    for block in re.split(r'\n\s*\n', markdown):
        lines = [line for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        rest = []
        for line in lines:
            heading = re.match(r'^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$', line)
            if heading:
                level, text = len(heading[1]), heading[2]
                if text.startswith('# '):  # "## # Title" typo seen in the corpus
                    level, text = 1, text[2:]
                text = clean_inline(text)
                if level == 1 and not title:
                    title = text
                elif level <= 2 and text:
                    chapters.append(Chapter(text))
                continue
            if re.fullmatch(r'\s*(?:[-*_]\s*){3,}', line):
                continue
            line = re.sub(r'^\s*(?:>\s*)+', '', line)
            line = re.sub(r'^\s*(?:[-+*]|\d+[.)])\s+', '', line)
            rest.append(line)
        text = clean_inline(' '.join(rest))
        if not text:
            continue
        if chapters:
            chapters[-1].paragraphs.append(text)
        else:
            front.append(text)
    if not chapters:  # no chapter headings: one chapter, front matter is the story
        chapters, front = [Chapter(title or 'Chương 1', front)], []
    return title, ' '.join(front), chapters, images


def segment(text, inside=False):
    """Split a paragraph into narration and quote segments. inside: paragraph continues an open quote."""
    parts = text.split('"')
    segs = []
    for i, part in enumerate(parts):
        is_quote = (i % 2 == 1) != inside
        if part.strip():
            segs.append(Segment('quote' if is_quote else 'narration', part.strip()))
        elif is_quote and segs and segs[-1].kind == 'narration':
            pass
    if (len(parts) % 2 == 0) != inside and segs and segs[-1].kind == 'quote':
        segs[-1].open_end = True
    return segs


SPEECH_VERBS = [
    'nói',
    'đáp',
    'hỏi',
    'bảo',
    'tuyên bố',
    'thì thầm',
    'thì thào',
    'gọi',
    'kêu',
    'hét',
    'rên',
    'lẩm bẩm',
    'lầm bầm',
    'thở',
    'cười',
    'nhắc',
    'giải thích',
    'tiếp',
    'thêm',
    'cãi',
    'ra lệnh',
    'thốt',
]


def inline_quote(before, quote, after, after_quote=False):
    """True for a quoted term inside a narration sentence, e.g. ghi chữ "Vào ăn đi" cùng...

    after_quote: the narration before this quote itself follows a quote, i.e. it is a speech tag
    that interrupts one speech: "...," nàng nói, "...".
    """
    b = before.rstrip()
    if not b:
        return False
    if b[-1] in '.!?…:;—–-':
        return False
    if b[-1] == ',' and (after_quote or contains(' '.join(b.split()[-6:]), SPEECH_VERBS)):
        return False
    # A quote ending a sentence/clause followed by a speech tag is dialogue: "...," cô nói.
    if quote.rstrip()[-1:] in ',!?…' and after[:1].islower():
        return False
    return True


class Attributor:
    narrator_gender: str

    def __init__(self, book, cast=None):
        self.book = book
        self.cast = dict(cast or {})  # name -> gender
        self.narrator = book.narrator
        self.names = {}
        self.name_gender = {}

    # --- names -----------------------------------------------------------------------------
    def find_names(self):
        """Capitalized word runs seen mid-sentence; sentence-initial capitals ("Đôi", "Những") don't count."""
        counts: Counter[str] = Counter()
        for chapter in self.book.chapters:
            for para in chapter.paragraphs:
                for seg in para.segments:
                    for clause in re.split(r'(?:[.!?…:;—–(\[]|\s-\s)\s*', seg.text):
                        words = re.findall(rf'{WORD}+', clause)
                        run = []
                        initial = True
                        for i, word in enumerate(words + ['x']):
                            if word[0].isupper():
                                run.append(word)
                                continue
                            # A sentence-initial capital is an ordinary word unless more capitals follow
                            # ("Sương Nguyệt bước vào" is a name, "Đôi mắt" is not).
                            if initial and run and len(run) == 1:
                                run = []
                            while run and run[0] in NAME_STOPWORDS:
                                run = run[1:]
                            if run and len(run) <= 4:
                                counts[' '.join(run)] += 1
                            run, initial = [], False
        names = {}
        for name, n in counts.items():
            common = sum(1 for _ in re.finditer(rf'(?<!{WORD}){re.escape(fold(name))}(?!{WORD})', fold(self.text))) - n
            if (
                n >= 3
                and len(name) > 1
                and common <= 3 * n
                and not name.isupper()
                and name.split()[0] not in ('Thứ', 'Chủ', 'Tháng', 'Ngày', 'Năm')
            ):
                names[name] = n
        for name in self.cast:
            names[name] = names.get(name, 0) + 100
        self.names = names
        return self.names

    def name_at(self, text):
        """Return a known name (with an optional title) that starts text."""
        for name in sorted(self.names, key=len, reverse=True):
            if text.startswith(name) and not re.match(WORD, text[len(name) : len(name) + 1] or ' '):
                after = text[len(name) :].lstrip()
                title = phrase_at(after, NAME_TITLES)
                return name, title
        # "Triệu trưởng lão" / "Huyền Cơ môn chủ" style: Name + title even if name is rare.
        caps = capitalized_run(text)
        if caps and caps.split()[0] not in NAME_STOPWORDS:
            title = phrase_at(text[len(caps) :].lstrip(), NAME_TITLES)
            if title:
                return caps, title
        return None

    def gender_of_name(self, name):
        if name in self.cast:
            return self.cast[name]
        return self.name_gender.get(name, '?')

    def learn_name_genders(self):
        """Infer a name's gender from titles and from the pronoun that refers back to it."""
        votes: defaultdict[str, Counter[str]] = defaultdict(Counter)
        for chapter in self.book.chapters:
            for para in chapter.paragraphs:
                text = ' '.join(s.text for s in para.segments if s.kind == 'narration')
                sentences = re.split(r'(?<=[.!?…])\s+', text)
                for i, sentence in enumerate(sentences):
                    hit = self.name_at(sentence)
                    if not hit:
                        continue
                    name, title = hit
                    if title in FEMALE_TITLES:
                        votes[name]['female'] += 3
                    elif title in MALE_TITLES:
                        votes[name]['male'] += 3
                    for follow in sentences[i + 1 : i + 3]:
                        if phrase_at(follow, FEMALE_PRONOUNS) or (self.narrator == 'tôi' and phrase_at(follow, ['em'])):
                            votes[name]['female'] += 1
                        elif phrase_at(follow, MALE_PRONOUNS):
                            votes[name]['male'] += 1
        for name in self.names:
            # Kinship next to the name: "chồng cô, Kenta", "Kenta, chồng của Zinie", "vợ tôi Minh".
            near = re.findall(
                rf'(?:(?<!{WORD})(chồng|vợ|anh trai|em trai|chị gái|em gái|bạn trai|bạn gái)'
                rf'(?:\s+(?:của\s+)?\w+)?,?\s+{re.escape(name)}(?!{WORD})|'
                rf'(?<!{WORD}){re.escape(name)},\s+(chồng|vợ|anh trai|em trai|chị gái|em gái|'
                rf'bạn trai|bạn gái)(?!{WORD}))',
                fold(self.text).replace(fold(name), name),
            )
            for a, b in near:
                kin = a or b
                votes[name]['male' if kin in ('chồng', 'anh trai', 'em trai', 'bạn trai') else 'female'] += 3
            honorific = Counter(re.findall(rf'{re.escape(name)}-(chan|kun)(?!{WORD})', self.text))
            votes[name]['female'] += 3 * honorific['chan']
            votes[name]['male'] += 3 * honorific['kun']
        for name, vote in votes.items():
            (top, n), *rest = vote.most_common() + [('?', 0)]
            if n >= 3 and n >= 3 * (rest[0][1] if rest else 0):
                self.name_gender[name] = top

    # --- subject of a narration clause --------------------------------------------------------
    def subject(self, text, scan=6):
        """Speaker id for the subject of the first clause of text, or None.

        Skips leading adverbials ("cuối cùng em cũng...", "Rồi, một giọng nói...") by trying each of
        the first few words; a clause of up to three words before a comma is treated as an opener.
        """
        clauses = re.split(r'[,.;:!?…—–]', text.lstrip(' ,.;:—–-'))
        for n, clause in enumerate(clauses[:2]):
            words = list(re.finditer(rf'{WORD}+', clause))
            for k, m in enumerate(words[:scan]):
                sid = self.pronoun_or_name(clause[m.start() :], initial=k == 0)
                if sid == self.narrator:
                    # "Tôi có thể nghe thấy tiếng cô di chuyển": the narrator perceives the speaker.
                    heard = re.search(
                        r'(?:nghe thấy|nghe|nhìn thấy|thấy|cảm nhận được|cảm nhận)\s+'
                        r'(?:(?:tiếng nói|tiếng cười|tiếng|giọng nói|giọng)\s+(?:của\s+)?)?(.+)',
                        clause[m.end() :],
                    )
                    other = self.pronoun_or_name(heard[1]) if heard else None
                    if other and other != self.narrator:
                        return other
                if sid:
                    return sid
            if len(words) > 3:
                break
        return None

    def pronoun_or_name(self, text, initial=True):
        if phrase_at(text, NOT_NARRATOR) in ('chúng ta', 'chúng tôi', 'người ta', 'bọn ta', 'các ta'):
            return None
        kin = phrase_at(text, list(KIN))
        if kin:
            owner = phrase_at(text[len(kin) :].lstrip(), NARRATOR_PRONOUNS + ['nàng', 'cô ấy', 'em', 'hắn'])
            sid = f'{kin} {owner}' if owner else kin
            self.name_gender.setdefault(sid, KIN[kin])
            return sid
        # "chú Hùng", "bé An", "lão Cố": a kinship title in front of a name gives the gender.
        title = phrase_at(text, list(PRE_TITLES))
        if title:
            name = capitalized_run(text[len(title) :].lstrip())
            if name and name.split()[0] not in NAME_STOPWORDS:
                self.name_gender.setdefault(name, PRE_TITLES[title])
                self.recent[self.gender_of_name(name)] = name
                return name
        if phrase_at(text, FEMALE_PRONOUNS):
            return self.resolve('female')
        # With a "tôi" narrator, narration calls the heroine "em" ("Em khựng lại.").
        if self.narrator == 'tôi' and phrase_at(text, ['em']) and not phrase_at(text, ['em trai', 'em bé']):
            return self.resolve('female')
        p = phrase_at(text, MALE_PRONOUNS)
        if p and not (p == 'y' and (not initial or phrase_at(text[1:].lstrip(), ['như', 'hệt', 'nguyên', 'phục']))):
            return self.resolve('male')
        if phrase_at(text, [self.narrator]) and not phrase_at(text, NOT_NARRATOR):
            return self.narrator
        hit = self.name_at(text)
        if hit:
            name, _ = hit
            self.recent[self.gender_of_name(name)] = name
            return name
        return None

    def resolve(self, gender):
        """A pronoun refers to the most recently named person of that gender in this chapter.

        With nobody of that gender known, the generic id ("female"/"male") is returned. (Crediting the
        pronoun to the last name of unknown gender was tried and mislabels absent people.)
        """
        return self.recent.get(gender) or self.main.get(gender) or gender

    # --- attribution ---------------------------------------------------------------------------
    def run(self):
        for chapter in self.book.chapters:
            inside = False
            paras = []
            for text in chapter.paragraphs:
                segs = segment(text, inside)
                inside = bool(segs) and segs[-1].kind == 'quote' and segs[-1].open_end
                # Inline quotes ("scare quotes") stay in the narrator voice; merge them into narration.
                merged: list[Segment] = []
                for i, seg in enumerate(segs):
                    before = segs[i - 1].text if i and segs[i - 1].kind == 'narration' else ''
                    after = segs[i + 1].text if i + 1 < len(segs) and segs[i + 1].kind == 'narration' else ''
                    after_quote = i >= 2 and segs[i - 2].kind == 'quote'
                    if seg.kind == 'quote' and i and inline_quote(before, seg.text, after, after_quote):
                        seg = Segment('narration', f'"{seg.text}"')
                    if merged and merged[-1].kind == seg.kind == 'narration':
                        merged[-1].text += ' ' + seg.text
                    else:
                        merged.append(seg)
                paras.append(Paragraph(merged))
            chapter.paragraphs = paras
        self.text = '\n'.join(s.text for c in self.book.chapters for p in c.paragraphs for s in p.segments)
        self.find_names()
        self.recent: dict[str, str] = {}
        self.main = {}
        self.learn_name_genders()
        for gender in ('female', 'male'):
            ranked = sorted((c, n) for n, c in self.names.items() if self.gender_of_name(n) == gender)
            if ranked:
                self.main[gender] = ranked[-1][1]
        for chapter in self.book.chapters:
            self.recent = {}
            self.attribute_chapter(chapter)
        for chapter in self.book.chapters:
            for para in chapter.paragraphs:
                for seg in para.quotes:
                    if seg.speaker not in self.book.speakers:
                        self.book.speakers[seg.speaker] = self.gender(seg.speaker)
        return self.book

    def gender(self, sid):
        if sid == self.narrator:
            return getattr(self, 'narrator_gender', 'male')
        if sid in ('male', 'female'):
            return sid
        return self.gender_of_name(sid) if sid != UNKNOWN else '?'

    def attribute_chapter(self, chapter):
        previous_open = None
        for para in chapter.paragraphs:
            segs = para.segments
            quotes = para.quotes
            # Keep recency of names mentioned in narration, even without dialogue.
            for seg in segs:
                if seg.kind == 'narration':
                    for sentence in re.split(r'(?<=[.!?…])\s+', seg.text):
                        self.pronoun_or_name(sentence)
            if not quotes:
                previous_open = None
                continue
            if previous_open and segs[0].kind == 'quote':
                segs[0].speaker, segs[0].rule = previous_open, 'continued'
            for i, seg in enumerate(segs):
                if seg.kind != 'quote' or seg.rule:
                    continue
                after = segs[i + 1].text if i + 1 < len(segs) else ''
                before = segs[i - 1].text if i else ''
                sid = None
                if after and (seg.text[-1:] in ',!?…—-' or after[:1].islower()):
                    sid, rule = self.subject(after), 'tag-after'
                if not sid and before:
                    last = re.split(r'(?<=[.!?…:])\s+', before.strip())[-1]
                    sid, rule = self.subject(last), 'tag-before'
                    if not sid:
                        sid, rule = self.subject(before), 'beat-before'
                if not sid and after:
                    sid, rule = self.subject(after), 'beat-after'
                if sid:
                    seg.speaker, seg.rule = sid, rule
            known = [q.speaker for q in quotes if q.rule]
            for q in quotes:
                if not q.rule and known:
                    q.speaker, q.rule = known[0], 'same-paragraph'
            for q in quotes:
                if not q.rule:
                    sid = self.cue(q.text)
                    if sid:
                        q.speaker, q.rule = sid, 'cue'
            previous_open = quotes[-1].speaker if quotes[-1].open_end else None
        self.turn_taking(chapter)

    def cue(self, quote):
        quote = re.sub(r'(?i)nàng ta', '', quote)
        female = contains(quote, FEMALE_SPEAKER_CUES)
        male = contains(quote, MALE_SPEAKER_CUES)
        vocative_names = [n for n in self.names if re.search(rf'(^|,\s*){re.escape(n)}(\s*[,.!?…]|$)', quote)]
        if vocative_names and not (female or male):
            g = self.gender_of_name(vocative_names[0])
            if g == 'female':
                return self.narrator
        if female and not male:
            return self.resolve('female')
        if male and not female:
            return self.narrator
        return None

    def turn_taking(self, chapter):
        """Alternate speakers across runs of consecutive dialogue paragraphs."""
        runs, run = [], []
        for para in chapter.paragraphs:
            if para.quotes:
                run.append(para)
            else:
                if run:
                    runs.append(run)
                run = []
        if run:
            runs.append(run)
        for run in runs:
            speakers = [p.quotes[0].speaker if p.quotes[0].rule else None for p in run]
            # "nàng" resolved to the generic "female" is the same person as the one named woman here.
            # If no named person has that gender here, a single name of unknown gender is the best match.
            for gender in ('male', 'female'):
                named = {s for s in speakers if s and s not in ('male', 'female') and self.gender(s) == gender}
                if not named and gender in speakers:
                    named = {s for s in speakers if s and s not in ('male', 'female') and self.gender(s) == '?'}
                if len(named) == 1:
                    speakers = [named.copy().pop() if s == gender else s for s in speakers]
            people = [s for s in dict.fromkeys(speakers) if s]
            if len(people) == 1:
                partner = self.default_partner(people[0])
                if partner:
                    people.append(partner)
            if len(people) != 2:
                continue
            changed = True
            while changed:
                changed = False
                for i, sp in enumerate(speakers):
                    if sp:
                        continue
                    neighbour = (
                        speakers[i - 1]
                        if i and speakers[i - 1]
                        else (speakers[i + 1] if i + 1 < len(speakers) and speakers[i + 1] else None)
                    )
                    if neighbour in people:
                        other = people[1 - people.index(neighbour)]
                        speakers[i] = other
                        for q in run[i].quotes:
                            if not q.rule:
                                q.speaker, q.rule = other, 'turn-taking'
                        changed = True
        for para in chapter.paragraphs:
            for q in para.quotes:
                if not q.rule:
                    q.speaker, q.rule = UNKNOWN, 'unknown'

    def default_partner(self, speaker):
        if speaker == self.narrator:
            return self.recent.get('female') or self.main.get('female')
        if self.gender(speaker) in ('female', 'male'):
            return self.narrator
        return None


def detect_narrator(chapters):
    counts: Counter[str] = Counter()
    for chapter in chapters:
        for text in chapter.paragraphs:
            narration = ' '.join(text.split('"')[0::2])
            low = fold(narration)
            for phrase in NOT_NARRATOR:
                low = re.sub(rf'(?<!{WORD}){re.escape(phrase)}(?!{WORD})', ' ', low)
            for p in NARRATOR_PRONOUNS:
                counts[p] += len(re.findall(rf'(?<!{WORD}){p}(?!{WORD})', low))
    return counts.most_common(1)[0][0] if counts else 'ta'


def build_book(markdown, cast=None, narrator=None, narrator_gender='male'):
    title, description, chapters, images = parse_markdown(markdown)
    book = Book(title, description, chapters, images)
    book.narrator = narrator or detect_narrator(chapters)
    attributor = Attributor(book, cast)
    attributor.narrator_gender = narrator_gender
    return attributor.run()


# --- script file ---------------------------------------------------------------------------------
# Rules whose answers are worth a second look; their lines are written as "[speaker?]".
REVIEW_RULES = {'turn-taking', 'cue'}
LINE = re.compile(r'^\[([^\]]*)\]\s?(.*)$')


def write_script(book, cover=None):
    lines = [f'@title {book.title}']
    if book.description:
        lines.append(f'@description {book.description}')
    if cover:
        lines.append(f'@cover {cover}')
    lines.append(f'@speaker {book.narrator} {book.speakers.get(book.narrator, "male")} narrator')
    for sid, gender in sorted(book.speakers.items()):
        if sid not in (book.narrator, UNKNOWN):
            # Genders learned from context are guesses ("female?"); only generic ids are certain.
            sure = sid in ('male', 'female') or gender == '?'
            lines.append(f'@speaker {sid} {gender}{"" if sure else "?"}')
    for chapter in book.chapters:
        lines += ['', f'## {chapter.title}']
        for para in chapter.paragraphs:
            lines.append('')
            for seg in para.segments:
                if seg.kind == 'narration':
                    label = NARRATION
                elif seg.speaker == UNKNOWN:
                    label = UNKNOWN
                else:
                    label = seg.speaker + ('?' if seg.rule in REVIEW_RULES else '')
                lines.append(f'[{label}] {seg.text}')
    return '\n'.join(lines) + '\n'


@dataclass
class ScriptLine:
    number: int  # 1-based line number in the script file
    label: str  # as written, e.g. "ta?", "?", "narrator"
    text: str

    @property
    def speaker(self):
        return self.label[:-1] if self.label.endswith('?') and self.label != UNKNOWN else self.label

    @property
    def needs_review(self):
        return self.label.endswith('?')


@dataclass
class Script:
    meta: dict[str, str]
    speakers: dict[str, str]  # id -> gender
    narrator: str
    chapters: list[tuple[str, list[list[ScriptLine]]]]
    unconfirmed: set[str] = field(default_factory=set)  # speakers whose gender is a guess ("female?")


def read_script(text: str) -> Script:
    meta: dict[str, str] = {}
    speakers: dict[str, str] = {}
    narrator: str | None = None
    chapters: list[tuple[str, list[list[ScriptLine]]]] = []
    unconfirmed: set[str] = set()
    paragraph: list[ScriptLine] | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            paragraph = None
            continue
        if line.startswith('@'):
            key, _, value = line[1:].partition(' ')
            if key == 'speaker':
                words = value.split()
                is_narrator = words[-1] == 'narrator'
                if is_narrator:
                    words = words[:-1]
                genders = ('male', 'female', '?', 'male?', 'female?')
                gender = words[-1] if words[-1] in genders else '?'
                sid = ' '.join(words[:-1] if words[-1] in genders else words)
                if gender.endswith('?') and gender != '?':
                    unconfirmed.add(sid)
                    gender = gender[:-1]
                speakers[sid] = gender
                if is_narrator:
                    narrator = sid
            else:
                meta[key] = value.strip()
            continue
        if line.startswith('## '):
            chapters.append((line[3:].strip(), []))
            paragraph = None
            continue
        m = LINE.match(line)
        if not m:
            raise ValueError(f'Line {number}: expected "[speaker] text", got: {raw[:80]}')
        if not chapters:
            raise ValueError(f'Line {number}: text before the first "## chapter" heading')
        if paragraph is None:
            paragraph = []
            chapters[-1][1].append(paragraph)
        paragraph.append(ScriptLine(number, m[1].strip(), m[2].strip()))
    return Script(meta, speakers, narrator or 'ta', chapters, unconfirmed)


# --- review export / import ----------------------------------------------------------------------
REVIEW_HELP = """You are checking who speaks each quoted line of a Vietnamese story that will become a
multi-voice audiobook. The narrator is {narrator_gender} and refers to himself as "{narrator}".

Edit ONLY the answer after "=> L<number>:" (and after "=> " on SPEAKER items). Keep every other line.
- Line answers: one speaker id from the list below, "narrator" if the text is not spoken dialogue,
  or "new: <Name> | male" / "new: <Name> | female" for a person who is not listed.
- SPEAKER answers: "male" or "female".
Lines starting with ">>> L<number>" are the ones to decide; the rest is context, but you may also
correct a context line by adding an "=> L<number>: speaker" answer for it.
"[x?]" is the current guess, "[?]" means unknown. Return the whole file."""


def export_review(script_text, context=3, limit=None):
    """A self-contained file an LLM (or a person) can edit; apply_review merges it back.

    limit: stop after about this many line items (whole context windows are kept). Returns
    (text, items written, items still open in the whole script).
    """
    script = read_script(script_text)
    open_items = sum(1 for _, paras in script.chapters for p in paras for line in p if line.needs_review)
    open_items += sum(1 for sid, g in script.speakers.items() if g == '?' or sid in script.unconfirmed)
    out = [
        f'# Speaker review: {script.meta.get("title", "")}',
        '',
        REVIEW_HELP.format(narrator=script.narrator, narrator_gender=script.speakers.get(script.narrator, 'male')),
        '',
        'Speakers:',
    ]
    for sid, gender in script.speakers.items():
        out.append(f'- {sid} ({gender}{", narrator" if sid == script.narrator else ""})')
    examples = defaultdict(list)
    for _, paras in script.chapters:
        for para in paras:
            for line in para:
                if line.speaker not in (NARRATION, UNKNOWN) and not line.needs_review:
                    examples[line.speaker].append(line.text)
    items = 0
    for sid, gender in script.speakers.items():
        if gender == '?' or sid in script.unconfirmed:
            out += ['', f'## SPEAKER {sid} (guess: {gender})', 'Says, for example:']
            out += [f'  "{t[:160]}"' for t in examples[sid][:3]]
            out.append(f'=> {gender}')
            items += 1
    for title, paras in script.chapters:
        targets = [pi for pi, para in enumerate(paras) if any(line.needs_review for line in para)]
        windows: list[list[int]] = []
        for pi in targets:
            if windows and pi - context <= windows[-1][1] + 1:
                windows[-1][1] = pi + 1
            else:
                windows.append([max(0, pi - context), pi + 1])
        for start, end in windows:
            if limit is not None and items >= limit:
                break
            out += ['', f'## {title}']
            answers = []
            for para in paras[start : end + 1]:
                for line in para:
                    if line.needs_review:
                        out.append(f'>>> L{line.number} [{line.label}] {line.text}')
                        answers.append(f'=> L{line.number}: {line.speaker}')
                        items += 1
                    else:
                        out.append(f'    L{line.number} [{line.label}] {line.text}')
                out.append('')
            out += answers
    return '\n'.join(out) + '\n', items, open_items


def apply_review(script_text, review_text):
    """Merge answers from an edited review file into the script. Returns (new_script, changes)."""
    lines = script_text.splitlines()
    targets, answers, speaker_answers, relabels, current_speaker = {}, [], [], [], None
    for raw in review_text.splitlines():
        line = raw.strip()
        m = re.match(r'^>>>\s*L(\d+)\s+(\[.*)$', line)
        if m:
            target_line = LINE.match(m[2])
            assert target_line is not None  # Review targets contain a complete [speaker] prefix.
            targets[int(m[1])] = target_line[2].strip()
            continue
        m = re.match(r'^(?:=>\s*)?L(\d+)\s*:\s*(.+)$', line)
        if m:
            answers.append((int(m[1]), m[2].strip()))
            continue
        m = re.match(r'^RELABEL\s+(.+?)\s*:\s*(.+)$', line)  # every line of one speaker -> another
        if m:
            relabels.append((m[1].strip(), m[2].strip()))
            continue
        m = re.match(r'^(?:=>\s*)?SPEAKER\s+(.+?)\s*:\s*(male|female)$', line)  # compact answers file
        if m:
            speaker_answers.append((m[1].strip(), m[2]))
            continue
        m = re.match(r'^##\s+SPEAKER\s+(.+?)(?:\s+\(guess:.*\))?$', line)
        if m:
            current_speaker = m[1].strip()
            continue
        if line.startswith('##'):
            current_speaker = None
        elif line.startswith('=>') and current_speaker:
            speaker_answers.append((current_speaker, line[2:].strip()))
            current_speaker = None
    speakers: dict[str, int | None] = {}
    for n, raw in enumerate(lines):
        if raw.startswith('@speaker '):
            words = raw.split()[1:]
            speakers[' '.join(words[:-2] if words[-1] == 'narrator' else words[:-1])] = n
    changes = 0
    for sid, answer in speaker_answers:
        position = speakers.get(sid)
        if answer in ('male', 'female') and position is not None:
            updated = re.sub(r' (male\??|female\??|\?)( narrator)?$', rf' {answer}\2', lines[position])
            changes += updated != lines[position]
            lines[position] = updated
    new_speakers: dict[str, str] = {}
    for old, new in relabels:
        declared = re.match(r'^new:\s*(.+?)\s*\|\s*(male|female)$', new)
        if declared:
            new = declared[1]
            new_speakers.setdefault(new, declared[2])
            speakers.setdefault(new, None)
        if old not in speakers:
            raise ValueError(f'RELABEL: unknown speaker "{old}"')
        if new not in speakers and new != NARRATION:
            raise ValueError(f'RELABEL: unknown target "{new}" (declare it with a "new:" answer or @speaker first)')
        for i, raw in enumerate(lines):
            m = LINE.match(raw)
            if m and m[1].rstrip('?') == old:
                mark = '?' if m[1].endswith('?') and m[1] != UNKNOWN else ''  # stays open for review
                lines[i] = f'[{new}{mark}] {m[2]}'
                changes += 1
    for number, answer in answers:
        index, text = number - 1, targets.get(number)
        current = LINE.match(lines[index]) if index < len(lines) else None
        if text is None and not current:
            raise ValueError(f'Answer L{number}: script line {number} is not a "[speaker] text" line')
        if not current or (text is not None and current[2].strip() != text):
            hits = [i for i, line in enumerate(lines) if (match := LINE.match(line)) and match[2].strip() == text]
            if len(hits) != 1:
                raise ValueError(f'Review answer L{number}: the script changed and the line was not found')
            index, current = hits[0], LINE.match(lines[hits[0]])
        assert current is not None  # Either the original line or the unique matching line was found.
        new = re.match(r'^new:\s*(.+?)\s*\|\s*(male|female)$', answer)
        if new:
            answer = new[1]
            new_speakers.setdefault(answer, new[2])
        elif answer not in speakers and answer not in new_speakers and answer not in (NARRATION, UNKNOWN):
            raise ValueError(f'Review answer L{number}: unknown speaker "{answer}" (use "new: Name | gender")')
        if f'[{answer}] {current[2]}' != lines[index]:
            changes += 1
        lines[index] = f'[{answer}] {current[2]}'
    insert_at = max((v for v in speakers.values() if v is not None), default=0) + 1
    for sid, gender in new_speakers.items():
        if speakers.get(sid) is None:
            lines.insert(insert_at, f'@speaker {sid} {gender}')
            insert_at += 1
    return '\n'.join(lines) + '\n', changes


# --- heuristic check of confident lines ------------------------------------------------------------
def check_script(script_text):
    """Lines worth a second look even though rules were confident. Returns [(line, message)]."""
    script = read_script(script_text)
    findings: list[tuple[int, str]] = []
    counts: Counter[str] = Counter()
    narrator = script.narrator
    for _, paras in script.chapters:
        for para in paras:
            for line in para:
                counts[line.speaker] += 1
                text = re.sub(r'(?i)nàng ta', '', line.text)
                if line.speaker == NARRATION:
                    if re.search(r'"[^"]{25,}"', line.text):
                        findings.append((line.number, 'narration contains a long quoted passage (missed dialogue?)'))
                    continue
                gender = script.speakers.get(line.speaker, '?') if line.speaker != narrator else 'male'
                if line.speaker in ('male', 'female'):
                    gender = line.speaker
                if gender == 'male' and contains(text, ['chàng', 'thiếp', 'phu quân', 'tướng công']):
                    findings.append((line.number, f'male speaker "{line.speaker}" uses words women say to men'))
                if gender == 'female' and contains(text, ['nàng', 'nương tử', 'tại hạ', 'lão phu']):
                    findings.append((line.number, f'female speaker "{line.speaker}" uses words men say'))
                if (
                    line.speaker == narrator
                    and narrator == 'ta'
                    and contains(text, ['huynh', 'sư huynh'])
                    and not contains(text, ['muội', 'sư muội'])
                ):
                    findings.append((line.number, 'narrator addresses someone as "huynh" (is this her line?)'))
    for sid, gender in script.speakers.items():
        if gender == '?':
            findings.append((0, f'speaker "{sid}" has unknown gender'))
        elif sid not in (narrator, 'male', 'female') and counts[sid] <= 2:
            findings.append((0, f'speaker "{sid}" has only {counts[sid]} line(s); a misread name?'))
    return sorted(findings)


if __name__ == '__main__':
    import sys

    print(write_script(build_book(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))), end='')
