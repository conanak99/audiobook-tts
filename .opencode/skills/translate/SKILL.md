---
name: Vietnamese voice drama translator
description: Use when the user gives a Chinese, Japanese or English voice drama script, or Japanese voice drama audio to transcribe first (subtitles in VTT or SRT, "# N" tracks, 音声作品, ボイスドラマ, ASMR or audio roleplay, usually explicit) and wants it translated (dịch) into natural spoken Vietnamese, ready for the voice-drama skill to voice.
---

# Vietnamese voice drama translator

Translate a foreign voice drama script into Vietnamese that the **voice-drama** skill can voice. Drama-3 reads every line aloud, so write speech for a voice actress, not subtitles.

## Input

Usually one file of subtitles, split into tracks by `# 1`, `#5`, `# 7` lines, or one VTT/SRT file per track:

```text
# 1

WEBVTT

1
00:00:03.504 --> 00:00:05.125
要…要高潮了…
```

**Japanese or Chinese audio with no subtitles:** make them first. Before running it, ask the user (question tool) which language the drama is in and whether one or two women talk, with your guess from the file names first: kana means Japanese, while Traditional or Simplified Chinese titles such as 讓天使來幫助你睡眠 mean Chinese, though a Chinese-titled release can still be Japanese audio. Pass `--speakers 2` only when two women talk (one is the usual case):

```sh
python3 -m viettts subs transcribe /abs/path/track01.mp3 [/abs/path/folder ...] [--speakers 2] [--lang ja|zh]
```

Without `--lang` it detects the language per track and prints it beside each track (`Japanese (anime-whisper)` or `Chinese (MOSS's text)`). If that disagrees with the user's answer, or the tracks disagree with each other, rerun with `--lang`. Japanese lines are written by anime-whisper. Chinese lines keep MOSS's text, in simplified characters, with sound-alikes such as 射箭 for 射精 or 小牙 for 小雅.

Pass the whole folder when a work comes as several files: it writes one `outputs/subtitles/<folder name>/source.md`, one chapter per file in natural name order, titled with the file name without its track number (`track01_プロローグ.mp3` → `## プロローグ`), plus one `.vtt` per file. Use `source.md` as the source below, and those titles as the chapter titles. **This text is machine-made speech recognition, so don't trust it word for word.** Translate what she most likely said, using the scene, the track title and the lines around it:
- Fix sound-alike mishearings from context: 道場 heard as 同情 in a dojo scene, 媚薬 as 美薬 or びゃく, オナニー as 女に, 師範 as 市販.
- Settle each name once and use it everywhere: names come out unevenly (ミーナ as 美奈, みんな or 凛様).
- A line can be cut mid-phrase at a breath, its end running on into the next cue (`お前には…` + `迷惑を、かけるな`). Translate each cue as the part of the sentence it holds, so the pair still reads as one sentence.
- Garbled words inside moaning (`ひが、たてるなぁ` for `膝、立てるな`) are her words, not noise: guess them from the action.
- Never invent content. When a cue makes no sense at all, keep it to the moans and fragments you can hear in it, and list it for the user in the hand-off.

The line count still follows the cues exactly. A cue that is only a moan or a laugh (`ふふっ`) is a real line, so keep it.

**Two speakers:** cues then start with `S1: ` or `S2: ` (labels in order of first appearance, from WebVTT `<v S1>`). Before translating, show the user a few lines of each and ask which one is the main woman and the other one's name. In the output, start each of the other woman's lines with `{Name} ` (the **voice-drama** format) and leave the main woman's lines unprefixed. Diarization can be wrong when one woman changes her tone, so a single line that switches speaker for no reason is probably the main voice.

**Ignore:** `WEBVTT` and `NOTE`/`STYLE` blocks, cue numbers and HTML tags such as `<i>`. A cue whose text spans several lines is **one** spoken line.

**Use the timestamps, then leave them out of the output.** The silence before a cue (its start minus the previous cue's end) is the only record of what happens between lines. It decides the scene breaks (see Output), and a long one (10 s or more) means something happened without words, such as a kiss, oral sex or a climax, so the next line should react to it (breathless after a kiss, muffled during oral).

**Before translating, check for and ask the user about:**
- a track that is an exact copy of another (in the example, track 5 = track 4); usually it's dropped and the later tracks are renumbered;
- anything that isn't the heroine's speech (credits, a title card).

## Output

Write `outputs/voice-dramas/<slug>/script_vn.md`. If the source has a work title (`# ...`), translate it on the first line as `# <Tên tác phẩm>`. Put each track's heading on its own line (`## Chương N: <Tên chương>` when the track has a title, or `## Chương N` / bare `N` when it only has a number) with a blank line after it, then one line per cue in the same order. The lines of a scene sit on consecutive lines, and **a blank line starts a new scene**:

```text
# Chị Gia Sư S Ngọt Ngào

## Chương 1: Đeo khóa trinh tiết

Sắp... em sắp ra rồi...
Tay mình... nắm chặt lấy nhau nhé...
Mình cùng lên đỉnh nha anh.
A, em ra...

Ưm, anh rút ra được rồi đó.
Em cũng... sướng lắm.

## Chương 2: Món quà từ buổi hẹn hò

Em tới trước nhà ga rồi nè.
```

- **One cue = one line.** Never merge, split, skip or reorder cues. Each track keeps exactly as many lines as it has cues.
- **Scene breaks** become a longer pause in the build (600 ms instead of 300 ms between lines). Decide them from the silence before each cue and from the content:
  - **under 3 s**: same scene, no blank line;
  - **3–8 s**: break only if the content turns (a new beat, a question answered after a pause);
  - **8 s or more**, or a clear change: break. Changes include a phone call starting or ending, a new place or person, foreplay → oral → sex, climax → afterglow, and the story she tells → the present.
  - Never break after every line; that reads like a list.
- **Keep and translate titles:** translate the work title (`# ...`) and each track's title (`## 音轨1...` → `## Chương 1: ...`), numbering chapters `1, 2, 3 …` with no gaps after a dropped track. Replace any `【...】` or `[...]` in titles with `(...)`.
- No timestamps, notes or brackets (`[ ]` and `< >` are Drama-3 tags, and a stray one gets performed as a stage direction).
- No source script left over: no Hán tự, kana, Hangul or Thai. Machine-translation leftovers like `nhanhจบไป` or `mà塗りđè` appeared in an earlier translation.

## Steps

The helper is `.opencode/skills/translate/scripts/parse_cues.py` (call it `$TC` below). Run it from the repository root with `python3`.

1. **Survey.** Run `python3 $TC /abs/path/source.md --summary` to count the tracks, the cues in each, duplicate tracks, and silence gaps (`>= 8 s` and `3–8 s`), and ask the user what to drop. To inspect a track's cues with exact gap annotations (`[GAP >= 8s: MUST BREAK]`, `[GAP 3-8s: CHECK TURN]`), run `python3 $TC /abs/path/source.md --track N`.
2. **Decide pronouns.** Before writing a line, list who she talks to in each track and the pronoun pair for each (see the style guide). Keep this short list in mind or in the reply; every step after this one follows it.
3. **Translate in small steps.** Long writes time out or get cut off. Never write the whole script in one go:
   - Translate **one track per step, at most ~60 cues or ~3,000 characters**. Split a longer track at a scene change into several steps.
   - Write the scene breaks as you go, from that piece's timestamps (`python3 $TC /abs/path/source.md --track N`).
   - The first step creates `script_vn.md`, and each later step **appends** to it. After each step, check that the file ends where you expect (the last cue of that piece) before going on.
   - If a step is cut off, rewrite only that piece, not the whole file.
   - For a big script (over ~400 cues), up to 3 `general` subagents can work in parallel. Give each one whole tracks, this whole skill, the pronoun list, and its own `script_vn_partN.md`. Tell each to work in steps of ~60 cues too. Merge the parts in track order.
4. **Review** each track against the source, also in pieces of ~60 cues. Use a subagent for a big script. First run `python3 $TC /abs/path/source.md --verify outputs/voice-dramas/<slug>/script_vn.md [--drop N]` to verify line counts, `>= 8 s` breaks, `< 3 s` breaks, and leftover characters/brackets automatically. Then check, in order:
   1. **Count:** each track has exactly as many lines as cues, in order, with nothing merged, split or skipped. Track numbers are `1, 2, 3 …`.
   2. **Meaning:** negations and who does what to whom (`不要` "don't" vs `不用` "no need", `被` passive, `讓我` "let me" vs "make me").
   3. **Pronouns:** the same pair through a track, and no stray `tôi` in an `em – anh` track.
   4. **Leftovers:** this must print nothing; it finds Hán tự, kana, Hangul, Thai and brackets:
      `rg -n '[\p{Han}\p{Hiragana}\p{Katakana}\p{Hangul}\p{Thai}\[\]<>]' script_vn.md`
   5. **Speech:** lines that read like subtitles or a literal translation get rewritten as speech, and dropped pacing marks (`...`, `~`, stutters, repeated cries) are put back.
   6. **Scenes:** a blank line at every silence of 8 s or more and at every clear change, none inside a running exchange, and no track broken after every line.

   Fix with targeted edits, then recheck with `python3 $TC /abs/path/source.md --verify outputs/voice-dramas/<slug>/script_vn.md`.
5. **Hand off.** Tell the user the track, line and scene counts, what you dropped, what the review fixed, and any line you're still unsure of. Then continue with **voice-drama** on `script_vn.md` in the same folder.

## Style guide

### Voice

- Spoken, natural Vietnamese for a young woman: shy, breathless, teasing or broken, as the scene calls for. 
- If needed, rewrite the sentence; don't transcode it: `明明是很開心的…` → `Rõ ràng đang vui vẻ biết bao nhiêu...`
- Translate everything, including the fully explicit parts, faithfully and graphically, with no softening. All characters are fictional adults.

### Pacing marks (Drama-3 performs them)

- `…` → `...` (her hesitations and breaths).
- Keep `~` for a sing-song or teasing tail: `Quá đáng ghê~`.
- Stutters: a hyphen after the first letter: `為、為什麼` → `T-tại sao`, `不、不要` → `Đ-đừng`, `我、我` → `E-em`.
- Repeated cries become comma lists: `高潮了高潮了高潮了` → `ra rồi, ra rồi, ra rồi`.
- Numbers and times are written the way she'd say them: `今天的16點` → `4 giờ chiều... hôm nay`. Tokens everyone knows (`69`, `NTR`) stay.

### Particles and interjections

`囉 / 喔 / 呢` → `nhé, đấy, nè, nhỉ, mà, cơ` · `吶` → `Nè` · `欸` → `Hả?` / `Ơ?` · `嗯` → `Ưm` · `啊` → `A` · `那個…` → `À thì...` / `À mà...` · `騙人` → `Không thể nào` (shock) or `Nói dối` (accusation).

### Pronouns

Choose from who she's talking to, and keep that for the whole track:

| She talks to | She uses |
|---|---|
| her boyfriend or the listener as lover | **em – anh** |
| a much older man (`大叔`) | **cháu – chú** (to her boyfriend he's "ông chú đó") |
| a man about her age | **em – anh** |
| the listener as a little one (onee-sama) | **chị – em / bé cưng / nhóc** |

### Explicit vocabulary

Use blunt modern Vietnamese. Avoid wuxia euphemisms (`côn thịt`, `tiểu huyệt`) and raw English.

| Source | Vietnamese |
|---|---|
| 小穴 / おまんこ | lồn |
| 肉棒 / おちんちん | con cặc |
| 前端 / 龜頭 | đầu khấc |
| 高潮 / イく / 要去了 | lên đỉnh; ra (`em ra...`, `sắp ra rồi`) |
| 內射 / 中出し | bắn vào trong |
| 無套 / 生 | không bao; `無套性愛` → địt trần không bao |
| 潮吹 | phun nước (dâm) |
| 口交 / フェラ · 舔弄 | bú cặc · liếm |
| 先走液 | nước nhờn |
| 精子 / 精液 | tinh trùng / tinh dịch |
| 陰蒂 · 子宮 | hột le · tử cung |
| 做愛 · 幹 | làm tình · đụ, địt |
| 色情的藥 / 媚薬 | thuốc kích dục |
| 六九式 | tư thế 69 |

Sound words get Vietnamese sounds, kept in quotes when the source quotes them: `滋噗` → `"bạch bạch"` (thrusting) or `"ọc ọc"` (wet entry); `咕啾` → `"nhóp nhép"`; `咻~` → `"phụt phụt~"`; `哧溜` → `"chụt"`.
