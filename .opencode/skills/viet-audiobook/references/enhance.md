# Enhancing Drama-3 lines

You, the agent, direct the heroine's and the MC's performances by writing Drama-3 tags into `enhance.txt`. Tags are **optional**: most lines need none, and a line without an entry is read plain. Enhance only the lines where the scene calls for a specific delivery. No tool writes tags; `check` validates what you write, and `build` splits it into chunks without breaking a tag. VieNeu would read tags aloud, so the build uses `enhance.txt` only for lines that a Drama-3 voice reads.

## How Drama-3 takes direction

A plain-language direction in square brackets changes the delivery from that point on. A paired word tag changes only the words it wraps:

```text
[calm and inviting] Welcome back to the studio.
[leans in, conspiratorial] There is one trick nobody tells you about.
[light, playful] Ready? <whisper>It is all in the timing.</whisper> [bright, back to full voice] And that is the whole secret.
```

- **Directions** go before the words they apply to. Write them the way you would brief a voice actor: emotion, intent, pacing, or who the character is talking to (`[barely holding it together, forcing a smile]`, `[professional broadcast tone]`). A direction lasts until the next one, so several directions in one line shift the delivery within it.
- **Sounds and pauses** go in brackets where they happen: `Ta không sao. [shaky breath] Thật mà. [small laugh] Đi đi.`
- **Paired tags** change only the wrapped words: `<whisper>`, `<emphasis>`, `<soft>`, `<fast>`, `<slow>`, `<stress>`, `<forceful>`. Example: `Nó sắp <emphasis>nổ</emphasis> rồi.`

## The file

`enhance.txt` sits next to `script.txt`. Each line is `L<n>: <script line n with tags added>`. Lines starting with `#` are comments.

```text
L12: [bright, teasing] Sư huynh!
L14: [playful, mock-scolding] Mặt trời lên cao rồi mà huynh còn ngồi cứng đơ như bia mộ thế kia. [proud, lowering her voice] Xem muội lén tuồn được thứ gì <whisper>qua mắt mấy vị trưởng lão</whisper> thiện phòng này!
L19: [giggles] Triệu trưởng lão nốc cạn ba vò đào hoa tửu, giờ đang ngủ say khướt sau lò đan kìa,
```

- **Only add tags.** Every word and punctuation mark must stay exactly as it is in `script.txt` (quote marks and `~ * _` may be dropped, since the build drops them anyway). `check` rejects a line whose words differ.
- Lines that need nothing get no entry and are read plain. Leave most lines plain; there is no coverage target.
- If an entry's line moves, for example because `apply-review` inserted `@speaker` lines, it follows the nearest line with the same words. If you edit the words of a script line, update or delete its entry: `check` reports the entry as stale and the build stops.

## Which lines get Drama-3

With the default cast (`casts/mixed.json`), the women's lines (the `female` role and each female speaker) and the MC's dialogue (`mc`, default `thien-minh-drama`) use Drama-3. Any role or speaker the cast maps to an onboarded voice id uses it too. When every voice is a Drama-3 voice (`casts/drama3.json`), every line uses Drama-3, narration included. Entries for lines that VieNeu reads are ignored.

## Choosing tags (read the context)

Read each Drama-3 line together with the narration around it in `script.txt`. Vietnamese prose usually says how a line is spoken, so turn that into direction:

| The story says | Tag |
|---|---|
| `thì thầm`, `ghé tai`, `khẽ nói` | `[whispering]`, or `<whisper>…</whisper>` for a few words |
| `cười khúc khích`, `bật cười` | `[giggles]` / `[laughs]` where the laugh happens, `[laughing]` as a direction |
| `thở dài` | `[sighs]` |
| `nghẹn ngào`, `giọng run run`, `mắt đỏ hoe` | `[voice trembling, holding back tears]` |
| `giận dỗi`, `phụng phịu` | `[pouting, sulky]` |
| `lạnh lùng`, `hừ lạnh` | `[cold, curt]`, `[scoffs]` |
| `trêu chọc`, `nháy mắt` | `[teasing, playful]` |
| `hét`, `quát` | `[shouting angrily]`, `<forceful>…</forceful>` |
| `ngượng ngùng`, `đỏ mặt` | `[shy, flustered]` |

Rules of thumb:
- **Write directions in English**: short and concrete, 1–5 words, at most 60 characters. Long or abstract directions made Drama-3 hit its frame cap (`[firm but quiet]` failed until it became `[serious]`).
- **Open each line with a direction** when the delivery matters. Use more directions in a line only when the mood changes. Don't tag every line: an unremarkable line reads well plain, fewer tags mean fewer surprises, and a wrong tag sounds worse than none.
- **Add sounds only where the story implies them** (a written laugh, sigh or gasp). Put no more than one or two in a line.
- **Paired tags wrap a few words, never a whole line.** For a whole line, use a direction such as `[whispering]`. Don't nest paired tags, and close each one on the same line. A paired `<whisper>` on a short line kept hitting the frame cap with the older weights, so listen for it in the pilot.
- **Stay in character.** Keep each heroine's tags consistent with her personality (a cold sư tỷ doesn't giggle) and with the onboarded voice's style.

## The MC

With the default cast, the first-person MC's dialogue (`[ta]`/`[tôi]`) runs on `thien-minh-drama`, the Drama-3 clone of the VieNeu narrator, while his narration stays on VieNeu. So his lines can be directed too, but the listener hears one man switching between telling and speaking, so the direction must not turn him into someone else:
- **Match his personality across the book.** A stoic master stays dry and level (`[dry, deadpan]`, `[calm, matter-of-fact]`, `[flat]`); his warmth and heat show by dropping the voice (`[quiet, warm]`, `[low, firm]`, `[low, husky]`, `[low, commanding]`), not by getting bright or loud.
- **Take cues from the narration around his line**: `ta nói, giọng khô khan` → `[dry, flat]`; `ta nói sát tai nàng` → `[low, close to her ear]`; `ta nâng cằm nàng lên` before a warning → `[low, serious]`.
- **Lighter than the heroine.** Prefer one short direction at the start; sounds (`[sighs]`, `[small laugh]`) only where the prose has them; a paired tag at most around one key phrase (`ngươi phải <emphasis>chạy ngay</emphasis>.`).
- **Check misattributed lines first.** The MC's id often catches lines that are really the heroine's (her boasts quoted inside his narration). Fix those with `apply-review` before tagging, or they will be read in his Drama-3 voice.
- In `meimei_v3`, 116 MC lines with directions only from this list rendered with 0 rejected takes.

## Intimate and spicy scenes

These are the scenes where tags matter most: read plain, a flirt or a love scene sounds like the evening news. Direct them like the rest, from what the prose says, and let the delivery follow how the scene builds: teasing → tension → heat → afterglow.

| The story says | Tag |
|---|---|
| `nũng nịu`, `làm nũng` | `[coy, pleading]`, `[sweet, needy]` |
| `liếc mắt đưa tình`, `khiêu khích`, `trêu ghẹo` | `[sultry, teasing]`, `[low, seductive]` |
| `giọng khàn khàn`, `giọng ngọt lịm` | `[low, husky]`, `[honeyed, intimate]` |
| `thì thầm bên tai`, `ghé sát tai` | `[whispering into his ear]`, or `<whisper>…</whisper>` around the words |
| `e thẹn`, `đỏ mặt`, `cắn môi` | `[shy, breathy]`, `[biting her lip, flustered]` |
| `thở dốc`, `hơi thở gấp gáp` | `[breathless]`, `[panting]`, `<fast>…</fast>` for a rushed phrase |
| `rên khẽ`, `rên rỉ`, `khẽ ưm một tiếng` | `[soft moan]`, `[moans]`, `[whimpers]` where the sound happens |
| `run rẩy`, `giọng run run` | `[trembling, breathless]` |
| `hổn hển`, `đứt quãng` | `[breathing heavily]`, with `[gasps]` between the broken words |
| `mê man`, `lả đi`, `thỏa mãn` | `[drowsy, content]`, `[soft, dreamy]` |
| `giận dỗi đẩy ra`, `cự tuyệt yếu ớt` | `[half-protesting, flustered]` |

```text
L210: [low, sultry] Huynh nhìn đủ chưa? [small laugh] <soft>Lại gần đây.</soft>
L214: [breathless, trembling] Huynh… [soft moan] đừng dừng lại…
L231: [drowsy, content] Ở lại với muội thêm chút nữa nhé.
```

- **The heat lives in the directions**: `[breathless]`, `[husky]`, `[sultry]`, `[trembling]`. Use `<soft>`, `<slow>` and `<whisper>` on the few words that should land closest.
- **Sounds sparingly.** Write `[soft moan]`, `[gasps]`, `[whimpers]` or `[pants]` only where the prose has the sound, one or two per line. A string of sounds sounds fake, makes a take longer, and is the most likely to hit the frame cap. If a tagged chunk keeps failing, the build reads it plain; check `build.log`.
- **Breathy takes and pauses.** Breathy deliveries can leave long silences. The worker retries takes with a pause over 1.5 s and shortens long pauses, so don't add `[pause]` here; `…` in the text already slows her down.
- **Narration stays with the narrator.** In mixed mode, only her spoken lines are Drama-3. Don't wrap a whole line in a paired tag: give it a direction, then wrap a few words.
- **Keep it hers.** A shy heroine stays shy when it gets hot (`[shy, breathless]`), and a cold sư tỷ melts slowly (`[cool, then softening]`). Match the onboarded voice: a soft, breathy voice such as `azu-livyatan` or `nina-meowmeow` needs lighter tags than a bright one.
- **The pilot**: if chapter 1 has no such scene, offer the user a pilot of just that chapter (`--only N`, saved as `… (thử chương N).m4b`), so they can judge these tags before the full build. Use `--chapters N` only if they want every chapter up to N.

## What the build does with it

Drama-3 voices each chunk separately, so the build (`split_tagged`):
- never cuts inside a tag, and keeps a tag-only piece (`… kìa. [laughs]`) with its words;
- closes a paired tag at a cut and reopens it in the next chunk;
- **repeats the current direction** at the start of every later chunk of a long line. The current direction is the last bracket that opens a sentence and isn't a sound. A sound is a short bracket (up to 3 words, no comma, no `-ing` word) naming one, such as `[sighs]`, `[small laugh]`, `[shaky breath]`, `[soft moan]`, `[gasps]`, `[pants]` or `[pause]`; sounds are never repeated. A list or an `-ing` form, such as `[breathless, intimate]`, `[laughing]` or `[breathing heavily]`, is a direction and carries over. So write a sound when it happens once and a direction when it should last.

Each tagged chunk has its own cache entry, so changing one entry re-synthesizes only that line. If all four takes of a tagged chunk are rejected (usually the frame cap), the worker **falls back to the same words without tags** and logs `every tagged take was rejected; trying without tags: …` in `build.log`. The build keeps going, but that chunk is read plain. After the build, look for these lines with `grep "without tags" <audiobook dir>/build.log`. Simplify those entries (usually a shorter direction, or remove the paired tag), run `check`, and rebuild: the changed entry gets a new cache key, so only that chunk is synthesized again. To keep the line plain, delete its entry.

The plain take is cached under the tagged entry's key and marked with a `<id>.plain` file. To retry those tags unchanged (for example after a worker change), run `python3 -m viettts audiobook repair <script.txt> --fallbacks` (add `--dry-run` to only list them), then rebuild.

The frame cap: a take that never ends (it runs on with breaths, babble or repeats) is rejected when it reaches its frame budget (~21.5 frames per second). The budget is ~3 frames per character plus room for pauses, at least 128 (~6 s), already 2–3× a normal reading. Keep the check: without it, such takes would go into the book with seconds of noise, or cut off mid-word. A larger budget for tagged chunks was tried and doesn't help: with `nina-meowmeow`, `[panting]`/`[breathless]` takes of a 3.5 s line still hadn't ended at 16 s, so it only made each failed attempt slower. Fix such a line by lightening its direction instead (`[soft, intimate]` rather than `[panting]`). One-off sounds are fine: in a 12-line pilot with `nina-meowmeow`, `[gasps]`, `[pants]`, `[whimpers]` and `[shaky breath]` passed first time, and the two retried chunks both opened with a moan (`[soft moan]`/`[moans]` at the very start), so place a moan after the line's first comma or sentence where there is one.
