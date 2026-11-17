---
name: Vietnamese audiobook builder
description: Use when the user asks to make a Vietnamese audiobook / M4B / BookPlayer file from story_vn.md, review or fix who speaks which line, pick narrator/male/female voices (VieNeu or Drama-3), direct Drama-3 performances with enhance.txt tags, or check and verify an audiobook build.
---

# Vietnamese audiobook builder

Run every command from the vietTTS repository root (the directory containing `viettts/` and `engines/`), using the system `python3`. The entry point is `python3 -m viettts audiobook`. Pass stories by **absolute path**; images next to the story are used for the cover. Work products go to `outputs/audiobooks/<title-slug>/`.

Typical request: the user gives a story (`story_vn.md`) and a **female voice**: either an onboarded voice (see `references/voices.md`) or a new video/audio file. Drama-3 works only with **onboarded** voices, so onboard a new file first with the **voice-onboarding** skill. Everything else has a default; don't ask about engines or male voices unless the user brings them up.

Pipeline: **parse → you review speakers → check → voices → you enhance the Drama-3 lines → pilot: build chapter 1 → the user listens and approves → full volume (background) → verify.** The rules attribute ~93% of quotes; you, the agent, are the reviewer for the rest, and the director of the heroine's performance. Never hand either job to a local LLM: a 4B model scored 54% (chance) on speakers.

## 1. Parse

```sh
python3 -m viettts audiobook parse /abs/path/story_vn.md
```

It prints the script path, chapter/quote counts, speakers with genders, and the number of open review items. An existing `script.txt` is never overwritten without `--force`, which would discard earlier review work, so ask the user before using it. Options: `--narrator ta|tôi` if detection is wrong, `--narrator-gender female` for a female first-person narrator, `--no-cover`.

## 2. Review speakers (your job)

Loop until no items are open:

```sh
python3 -m viettts audiobook review <script.txt> --batch 40
```

Each batch shows numbered context windows.
- Lines to decide start with `>>> L<n> [guess?]`.
- `[?]` means unknown.
- `SPEAKER X (guess: …)` items ask you to confirm a gender. Genders learned from context are only guesses, so confirm each against the example lines. If the examples don't fit that person (for example, the heroine's words credited to her absent husband), the lines were credited to the wrong person; fix them as well.

Decide each item from context; read `references/attribution.md` once for the Vietnamese conventions. **Context lines can be wrong too**, so correct any you notice by line number. Then write a compact answers file and apply it:

```text
SPEAKER Mei: female
RELABEL female: new: Zinie | female   # the generic "female" id is really Zinie (open "?" marks are kept)
L32: Zinie
L40: tôi
L157: Zinie                 # a context line that was wrong
L901: narrator              # not spoken dialogue (a sign, a thought, a sound)
L955: new: Lão Cố | male    # a person not yet listed
```

```sh
python3 -m viettts audiobook apply-review <script.txt> answers.txt
```

- Answer every `>>>` item in the batch, including the guesses you agree with; that clears their `?`. The command prints how many items are still open.
- Use only ids from the speaker list, `narrator`, `new: Name | gender`, or a name declared by `RELABEL … new:` in the same file. `apply-review` rejects unknown ids and line numbers that don't point at a `[speaker] text` line. It backs up the script on every run.
- `RELABEL` is applied before the `L` answers, and it only renames speakers; it doesn't change voices. Use it when a generic `male`/`female` id is clearly one named person, so that cast overrides can target that name.
- For a long book (often 50–300 items), keep the batch size at 40 or less and process the batches one after another; `review` always shows the next open items.
- If you are unsure about a line, keep the guess and tell the user its line number rather than inventing a speaker.

## 3. Check

```sh
python3 -m viettts audiobook check <script.txt>
```

This flags confident lines that look suspicious: a female speaker using `nàng` or `nương tử`, a male speaker using `chàng` or `thiếp`, long quoted passages left in narration, and speakers with only one or two lines. Many findings are false positives, for example a woman describing another woman as `nàng`. Read each flagged line in `script.txt` with its neighbours. Fix real errors with the same `L<n>: speaker` answers file; `apply-review` works on any dialogue line. Exit code 1 means the script is not buildable yet: `[?]` lines or speakers of unknown gender remain.

You may also edit `script.txt` directly. Keep the `[speaker] text` format and never change the text itself. Performance tags go in `enhance.txt` (step 5), never in `script.txt`.

## 4. Voices

Use the **mixed** preset, which is the CLI default (no `--engine` flag). The men run on fast VieNeu and the heroine is cloned with Drama-3. A **VieNeu voice name** runs on VieNeu, and an **onboarded voice id** (`lynasa`) runs on Drama-3; the builder resamples and levels so the two blend. Raw audio files are refused: every Drama-3 voice must be onboarded, meaning it has a clean cut, a reviewed transcript and auditioned samples. That is what keeps retries and odd pauses low.

| Role | Default | Notes |
|---|---|---|
| `narrator` | VieNeu **Thiện Minh** | Narration **and** the first-person MC (`ta`/`tôi`): one person, one voice. **Hải Đăng** is the alternative if the user asks. |
| `male` | VieNeu **Hải Đăng** | Other men only. Use Thiện Minh if Hải Đăng is the narrator. |
| `female` | the user's choice → `--female <voice id>` | See below. |

The female voice:
- **An onboarded voice** (the user names it, e.g. "Lynasa"): use its id from the table in `references/voices.md`, e.g. `--female lynasa`. Check that its status is onboarded with `python3 -m viettts voice list`.
- **A new file or link** (video, audio, YouTube, stream): run the **voice-onboarding** skill first. That means cutting a clean clip, transcribing and reviewing it, auditioning samples with the user, and approving. Then use the new id. Never pass a raw file to `--female`; the build refuses it.
- **Nothing given:** suggest 2–3 onboarded voices whose `fits`/`style` suit the heroine, give the user their `samples/` paths to listen to, and let them pick. If they don't care, use the default (`shirone-mika`).

Only when the user asks for it:
- `--separate-mc`: the MC's dialogue sounds different from the narration.
- `--cast <json>`: per-speaker voices, for example a second woman with her own voice (`"Bạch Thanh Thanh": "nika-linh-lan"`, with onboarded ids only). `casts/mixed-example.json` is a template.
- `--engine vieneu`: everyone on VieNeu, Ngọc Huyền for women. Fastest: with the default 4 parallel workers (`--workers`, ~2 GB RAM each), about 1 minute of compute per 18 minutes of audio.
- `--engine drama3`: everyone on Drama-3, using male references made with `make-ref`.

**Drama-3 costs:** about 30 GB of RAM and roughly 40 minutes per 100k characters it voices. In mixed mode it voices only the women's lines, so a full book takes about 15–30 minutes.

## 5. Enhance the Drama-3 lines (your job)

Drama-3 takes direction from the text itself: `[a direction]` before words, `[sounds]` where they happen, and paired `<whisper>`/`<emphasis>`/`<soft>`/`<fast>`/`<slow>`/`<stress>`/`<forceful>` tags around a few words. Fitting tags make the heroine sound like she does in the scene, instead of reading every line in one tone. **Read `references/enhance.md` before the first entry**; it has the tag rules, a table of Vietnamese cues and the pitfalls.

Tags are **optional**. Most lines read well plain and get no entry; enhance only the lines where the scene calls for a specific delivery: an emotion shift, a whisper, a laugh or sigh the story mentions, a shout, a tease. There is no coverage target, and an empty or missing `enhance.txt` is fine.

You write the tags; no tool writes them. Put them in `enhance.txt` next to `script.txt`, one entry per line you enhance, using the line number from `script.txt`:

```text
L12: [bright, teasing] Sư huynh!
L14: [playful, mock-scolding] Mặt trời lên cao rồi mà huynh còn ngồi cứng đơ như bia mộ thế kia. [proud, lowering her voice] Xem muội lén tuồn được thứ gì <whisper>qua mắt mấy vị trưởng lão</whisper> thiện phòng này!
```

- Read through the lines a Drama-3 voice reads with the step 4 voices (in mixed mode, the women's lines), together with the narration around them. The story usually says how she speaks (`thì thầm`, `cười khúc khích`, `nghẹn ngào` …); those are the lines worth an entry. Flirting and intimate scenes need tags the most; `references/enhance.md` has a section on them.
- **Only add tags.** Never change a word or punctuation mark. When in doubt, leave the line plain: a wrong tag sounds worse than none.
- Directions are short English (1–5 words, at most 60 characters). Use sounds only where the story implies them, and paired tags only around a few words, never nested.
- Go through chapter 1 before the pilot, and the remaining chapters before the full volume (step 7), a chapter or two at a time.
- Validate after every round of edits:
  ```sh
  python3 -m viettts audiobook check <script.txt>
  ```
  `enhance:` findings name the line and the problem: changed words, an unsupported, unclosed or nested tag, an empty or overlong direction, a chunk over 300 bytes, or a stale entry whose script line was edited. Exit code 1 means not buildable, and the build refuses the same problems. Fix the entry and run `check` again.

The build uses an entry only for a line that Drama-3 voices (VieNeu would read the tags aloud). It never cuts inside a tag, closes and reopens a paired tag at a cut, and repeats the current direction (not a sound) on every later chunk of a long line. Changing an entry re-synthesizes only that line. If every take of a tagged chunk is rejected, the worker reads that chunk without tags and logs `trying without tags` in `build.log`. After a build, run `grep "without tags" <audiobook dir>/build.log`, then simplify or delete those entries.

## 6. Pilot chapter before a full volume (optional)

> This step is only used when creating a new volume of a new series and user need to pilot for character fit. Skip this unless user ask for pilot chapter

Build only chapter 1 first, verify it, and **ask the user to listen before going further**:

```sh
python3 -m viettts audiobook build <script.txt> --female <voice id> --author "…" --chapters 1
python3 -m viettts audiobook verify <script.txt> --partial
```

The pilot is saved as `… (thử 1 chương).m4b`, so it never overwrites the full volume. Give the user its path (they can AirDrop it to BookPlayer) and ask them to check:
- the heroine's voice and how it fits the character
- the narrator/MC voice
- the pacing, and any mispronounced names or words
- the heroine's acting: emotions that fit the scene, and any tag that sounds wrong (a misplaced laugh or sigh, an odd whisper, or a tag spoken as words)
- any line read by the wrong person (ask for the sentence; you can find its line number in `script.txt`)

Then **stop and wait for their answer.** Apply what they say: fix speakers with an answers file, change voices, or fix `enhance.txt` entries (then `check`). Run another pilot if voices or tags changed; only the changed lines are synthesized again. Start the full build only after an explicit OK. Chunks from the pilot are cached, so chapter 1 costs nothing again in the full build.

## 7. Full volume

Before starting, go through the remaining chapters for lines worth enhancing (step 5), then run `check`. Then run the same command without `--chapters` as a **background** command, and do not poll it; you will be notified when it finishes.

```sh
python3 -m viettts audiobook build <script.txt> --female <voice id> --author "…"
```

- The volume comes from the story's folder name (`meimei_v2` → 2), and the series from the `@title` part before the first dash. So the book is named `<Series> vN - <Subtitle>.m4b`, e.g. `Mị Mị v2 - Khi Ngọn Núi Biết Lắng Nghe.m4b`. Pass `--volume N` only when the folder has no `_vN`, and `--series "…"` only to override the album tag.
- Right after starting it, give the user both progress commands in `bash` blocks, using the real script path, so they can check on it themselves:
  ```sh
  python3 -m viettts audiobook status <script.txt>      # cache counts, % done, ETA, outputs
  tail -f <audiobook dir>/build.log                 # live log
  ```
- To see progress yourself, run `python3 -m viettts audiobook status <script.txt>` once. It shows cache counts, the last lines of `build.log` (percent, ETA, minutes of audio) and existing outputs.
- A failed or interrupted build resumes from the cache: rerun the same command. Editing script lines only re-synthesizes those lines.
- The build stops on `[?]` lines. Use `--unknown narrator` only if the user accepts reading them in the narrator's voice.
- Afterwards, record what you learned about the female voice (retries, repairs, how it fits) with `python3 -m viettts voice note <id> "<note>"`; notes stay in voice.json, not the compact voices table.

## 8. Verify and report

```sh
python3 -m viettts audiobook verify <script.txt>        # add --partial after a --chapters or --only build
```

It checks the codec, that the chapters match the script, the tags, `media_type=2`, the cover, and that no silence is longer than 2.5 s. If the silence check fails (usually Drama-3 copying pauses from a breathy reference), run `python3 -m viettts audiobook repair <script.txt> --dry-run` first. Without `--dry-run`, it deletes the cached chunks that contain a pause over 1.5 s. **After it finishes**, rerun the build; never run repair and build in parallel. The worker retries such takes up to four times and shortens pauses inside chunks, so a second repair is rarely needed. If one reference voice keeps causing this, suggest a cleaner reference to the user, for example `make-ref` from a VieNeu voice. Report the M4B path, its duration and size, the voices used, how many review answers you changed from the rules' guesses, and how many Drama-3 lines you enhanced. Remind the user they can AirDrop the file to BookPlayer.
