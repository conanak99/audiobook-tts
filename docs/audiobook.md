# Story → multi-voice M4B audiobook

`python3 -m viettts audiobook` turns one `story_vn.md` into one audiobook volume: `<Series> vN - <Subtitle>.m4b`, with a chapter for each `##` heading, tags, cover art and three voices: the narrator (who is also the first-person MC), other men, and women. Play it in BookPlayer. The orchestrator uses only the Python standard library plus `ffmpeg`. Run commands from the repository root; engines launch automatically in their isolated uv environments.

## 1. Parse

```sh
python3 -m viettts audiobook parse /full/path/story_vn.md
```

This writes `outputs/audiobooks/<title-slug>/script.txt` and `review.md`.

- The first `#` heading is the title. Each `##` heading starts a chapter. Text before the first chapter (the "Kịch bản"/"Viễn cảnh" block) becomes the description tag and is not read aloud.
- The cover is the first image next to the story that exists. `--no-cover` turns it off.
- The narrator pronoun (`ta`/`tôi`) is detected; use `--narrator` to force it. The narrator is assumed male (`--narrator-gender` overrides).
- An existing `script.txt` is never overwritten without `--force`, so your edits are safe.

Speakers are decided by rules, no LLM involved. In order:

1. a speech tag after the quote (`"…," nàng đáp`)
2. the subject just before the quote (`Ta hé mở một mắt. "…"`)
3. action beats
4. the same paragraph
5. address words (`chàng`, `thiếp`, `nàng`, `tại hạ`…)
6. turn-taking in a back-and-forth exchange

Over 211 archived stories (83,332 quotes), rules decided 92.7% of the quotes. Historical hand-checked samples were about 96% correct; these are not guarantees for a new book. See the [original design](plans/2026-11-16-audiobook-design.md).

## 2. Review (optional, recommended)

`script.txt` is plain text and safe to edit:

```
@speaker ta male narrator
@speaker Sương Nguyệt female

## Chương 1: …
[narrator] Ta hé mở một mắt.
[ta] Mấy quả hàn qua đó là phần của các vị Đại trưởng lão.
[Sương Nguyệt?] …      ← a turn-taking guess, worth a look
[?] …                  ← unknown; build stops on these by default
```

The intended reviewer is an agent using the project skill `.opencode/skills/viet-audiobook` (ask: "make an audiobook from /path/story_vn.md"). It loops over `review --batch 40`, writes compact answers (`L123: ta`, `SPEAKER Mei: female`, `RELABEL female: new: Zinie | female`), runs `apply-review`, and then runs `check`. Genders learned from context are written as guesses (`@speaker Kenta female?`) and must be confirmed.

`review.md` holds only the uncertain lines with context and instructions. You can also give it to any LLM, or edit it yourself. Change only the `=> L<n>: answer` lines (and `=> male|female` for speakers of unknown gender). Then merge it back:

```sh
python3 -m viettts audiobook apply-review outputs/audiobooks/<slug>/script.txt edited-review.md
python3 -m viettts audiobook export-review outputs/audiobooks/<slug>/script.txt
```

`apply-review` saves a timestamped backup of the script. It also checks that every answered line still has the same text, so you can apply a stale review after editing the script. Answers can name a new person: `new: Lão Cố | male`.

## 3. Build

```sh
python3 -m viettts audiobook build outputs/audiobooks/<slug>/script.txt --author "…" --series "Sương Nguyệt" --volume 1
```

The volume number comes from the story's folder name (`meimei_v2/story_vn.md` → 2; `_vol3` also works), so `--volume` is only needed when the folder has none. The series is the part of the `@title` before the first dash, so `Mị Mị — Khi Ngọn Núi Biết Lắng Nghe` becomes the title and file name `Mị Mị v2 - Khi Ngọn Núi Biết Lắng Nghe`, with album `Mị Mị` and track 2. Without a volume, the title is kept as it is.

```sh
python3 -m viettts audiobook build … --chapters 2
python3 -m viettts audiobook build … --only 6
python3 -m viettts audiobook build … --narrator "Thiện Minh" --male "Hải Đăng" --female "Ngọc Huyền"
python3 -m viettts audiobook build … --female lynasa
python3 -m viettts audiobook build … --cast casts/mixed-example.json
python3 -m viettts audiobook build … --engine vieneu
```

Each voice picks its engine: a VieNeu voice name runs on VieNeu, and a reference `.wav` runs on Drama-3 (voice cloning). The default preset is **mixed**:

| Role | Voice |
|---|---|
| Narration and the first-person MC | VieNeu Thiện Minh |
| Other men | VieNeu Hải Đăng |
| Women | Drama-3 cloned from the onboarded voice `shirone-mika` |

- Change the heroine with `--female <voice id>`. The onboarded voices are listed in `.opencode/skills/viet-audiobook/references/voices.md`, or run `python3 -m viettts voice list`. Raw audio files are refused; onboard them first (see below).
- Mixed chunks are resampled to one rate (VieNeu 48 kHz) and leveled to the same loudness.
- `--engine vieneu` puts everyone on VieNeu (Ngọc Huyền for women); `--engine drama3` puts everyone on Drama-3.
- The MC's own dialogue (`[ta]`/`[tôi]`) uses the narrator voice, since they are one person. `--separate-mc` gives the MC the male voice instead. A cast JSON can also give one speaker their own voice: `{"voices": {"Sương Nguyệt": "Trúc Ly"}}`.

Each segment is split into one sentence per chunk and cached as `cache/<engine>/<sha1>.wav`. Chunks from both engines can sit side by side in one build. A crashed build resumes, and editing one line re-synthesizes only that line. The narrator reads the book title once, before chapter 1.

**Splitting.** A sentence over the engine's limit is cut at commas, semicolons, colons or dashes. It becomes as few, evenly sized chunks as possible. Only a clause that doesn't fit on its own is cut between words, near its middle.
- VieNeu: at most 225 characters.
- Drama-3: at most 200 characters and 300 UTF-8 bytes. 300 bytes is mlx-audio's own generation unit (`CHUNK_BYTES`), so the runtime never splits a chunk again.

On Sương Nguyệt (1,145 sentences), this removed every mid-phrase cut. The old limit of 120 characters with word-filling made 267 mid-phrase cuts for Drama-3; now there are 19 cuts, all at commas.

**Pauses.** When a chapter is assembled, each chunk's own leading and trailing silence is trimmed to 30 ms (10 ms windows under −40 dBFS). Then a fixed pause is added, so every join gets its planned length:
- inside a script line: 250 ms between sentences, 100 ms at a comma cut;
- after a line: 300 ms at a speaker change, 600 ms at a paragraph end, 1.2 s after a title, 1.7 s at a chapter end.

Before trimming, the gaps were whatever silence each chunk happened to have: VieNeu chunks end with 150–340 ms, Drama-3 chunks with 100–180 ms. Trimming happens at assembly, so cached chunks stay valid.

Drama-3 sometimes copies long pauses from its reference clip. A take with more than 1.5 s of silence is regenerated, up to four tries; after that the take with the least silence is kept. Pauses over 0.8 s inside any chunk are shortened to 0.5 s. Every chunk is leveled to the same speech loudness (−20 dBFS RMS, gain limited to ±12 dB, peak −1 dB), so voices from different references sound equally loud.

Progress goes to the terminal and to `build.log`. It shows the four stages (plan, synthesize, assemble, encode) with elapsed time, and during synthesis one line per chunk with percent done, ETA, and minutes of audio so far. With several VieNeu workers, their progress is merged into one line every 5 s.

VieNeu runs as `--workers 4` parallel processes of `--threads 2` each, about 2 GB of RAM per worker. VieNeu generates one small audio frame at a time, so extra threads in a single process don't help: measured on this M5 Pro, RTF stayed at 0.11 from 2 to 8 threads. Separate processes do help: 2× faster with 4 workers, 2.3× with 6, and about 2.5× at most. Metal (PyTorch MPS) is not an option: one chunk at a time it was 8× slower than the CPU, and VieNeu's batched mode produced NaNs on MPS. int8 was only about 10% faster. Drama-3 always uses one worker (~26 GB).

The output is AAC 64 kbps mono (`aac_at` on macOS), brand `M4B`, with a QuickTime chapter track, title/artist/album (series)/track (volume)/genre tags, `media_type=2` (audiobook) and the cover as an attached picture. `summary.json` records voices, timings and chapter marks.

Measured here:
- VieNeu built chapters 1–2 of Sương Nguyệt (10.4 min of audio, 167 chunks) in 76 s with one worker.
- VieNeu, chapters 1–3 (16.3 min of audio, 247 chunks): synthesis took 1 min 49 s with 1 worker × 4 threads and 54 s with 4 workers × 2 threads.
- Drama-3 built the full book: 1,406 chunks and 91.8 min of audio in 66 min, plus 4.5 min to repair 25 chunks that had long pauses (all in the Shirone Mika voice).

## Drama-3 performance tags (enhance.txt)

Optionally, an agent (or you) can direct chosen Drama-3 lines (most lines need nothing) with `[directions]`, `[sounds]` and paired `<whisper>`, `<emphasis>`, `<soft>`, `<fast>`, `<slow>`, `<stress>`, `<forceful>` tags. Write them in `enhance.txt` next to `script.txt`, one `L<n>: <script line n with tags>` per line; `script.txt` stays plain. Nothing generates tags: `check` validates the entries (same words as the script line, supported, closed and not nested tags, directions ≤ 60 characters, chunks ≤ 300 bytes, no stale entries), and the build refuses invalid ones. The build applies an entry only to a line voiced by Drama-3, since VieNeu would read the tags aloud. It splits a tagged line without cutting a tag, closes and reopens a paired tag at a cut, and repeats the current direction (never a sound) on each later chunk. If all four takes of a tagged chunk are rejected, the worker reads its words without tags and logs `trying without tags` in `build.log`. Guidelines: `.opencode/skills/viet-audiobook/references/enhance.md`.

## Pilot first

Build `--chapters 1` before a full volume and listen to it. A pilot is saved as `… vN - … (thử 1 chương).m4b`, so it never overwrites the full file, and its chunks are cached for the full build.

## Drama-3 voices (onboarding)

Every Drama-3 voice is **onboarded** into `references/voices/<id>/` with `python3 -m viettts voice`, which the **voice-onboarding** skill drives:

```sh
python3 -m viettts voice candidates "<video/audio file or URL>" --id "Name"
python3 -m viettts voice cut <id> --candidate 1 --candidate 4
python3 -m viettts voice transcribe <id>
python3 -m viettts voice set-transcript <id> --ref N --text "…"
python3 -m viettts voice samples <id>
python3 -m viettts voice approve <id> --gender female --style "…" --fits "…"
python3 -m viettts voice list
python3 -m viettts voice note <id> "…"
```

The NanoGPT key comes from `NANOGPT_API_KEY` or `--key-file`. The male voices are VieNeu; for an all-Drama-3 build, make synthetic male references with:

```sh
python3 -m viettts audiobook make-ref --voice "Thiện Minh"
```

`casts/drama3-example.json` uses Thiện Minh as the narrator and MC, Hải Đăng for other men and `shirone-mika` for women. Drama-3 needs about 30 GB of RAM and is much slower than VieNeu.

## Agent helpers

```sh
python3 -m viettts audiobook review <script.txt> --batch 40
python3 -m viettts audiobook check <script.txt>
python3 -m viettts audiobook status <script.txt>
python3 -m viettts audiobook verify <script.txt> [--partial]
python3 -m viettts audiobook repair <script.txt> --dry-run
```

`repair` without `--dry-run` deletes the affected cached chunks. Never run it concurrently with a build.

## Accuracy tools

```sh
python3 scripts/attribution_report.py /path/to/stories              # coverage per story and per rule
python3 scripts/attribution_report.py /path/to/stories --samples 30 --rule turn-taking --brief
python3 -m unittest tests.test_audiobook
```
