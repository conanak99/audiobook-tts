---
name: Vietnamese voice drama builder
description: Use when the user gives a Vietnamese script that is spoken straight to the listener by one woman (sometimes two), with no narrator and no "quoted" dialogue (a voice drama, ボイスドラマ, 音声作品, ASMR or audio roleplay, girlfriend, onee-sama or NTR monologue), and wants it voiced with an onboarded voice (pong-kyubi, lynasa ...), acted with Drama-3 tags and moans or other lewd sounds, and built into an M4B for BookPlayer.
---

# Vietnamese voice drama builder

A **voice drama** is the companion format to an audiobook (see the **audiobook** skill): no narrator and no speaker attribution. One woman, or now and then two, speaks every line to the listener ("anh", "em", "bé cưng"), and the whole performance comes from Drama-3 tags. 

So this pipeline skips `parse` and the speaker review; you write one **directed copy** of the script, and a helper turns it into the same `script.txt` + `enhance.txt` + `cast.json` that the audiobook builder uses. Build, verify and repair are the audiobook commands.

Run everything from the repository root with the system `python3`. The helper is `.opencode/skills/voice-drama/scripts/make_drama.py` (call it `$VD` below). Work products go to `outputs/voice-dramas/<slug>/`.

Use the audiobook skill instead when the text has a narrator, quoted dialogue, or several characters to tell apart. A script that isn't in Vietnamese yet (Chinese, Japanese or English subtitles) goes through **translate** first; it leaves `script_vn.md` in the work folder.

Pipeline: **scan → init → you direct (`directed.txt`: review scene breaks, add tags) → make → check → build (background) → verify.**

## 1. Scan the source

```sh
python3 $VD scan /abs/path/script.md
```

Chapters can be `## Chương N: Tên chương` headings (which become the M4B chapter titles in BookPlayer), bare numbers (`1`, `2` …), or `Chương N`/`Track N`/`Part N` lines; an optional `# Tên tác phẩm` line at the very top sets the default work title. Every other non-empty line is one spoken line. Within a chapter, consecutive lines form a scene and a blank line starts the next one. `scan` prints the work title (if present), each chapter's title, lines, scenes and characters, and the rough Drama-3 time. If it reports `identical to chapter N` (a pasted-twice chapter), ask the user whether to drop it (`--drop`); they usually agree. The script is taken as final: wording, leftovers and pronoun slips are the **translate** skill's review, not this one's.

## 2. Init

```sh
python3 $VD init /abs/path/script.md --out outputs/voice-dramas/<slug> \
  --voice lynasa --title "Bạn Gái Của Anh" --author "Lynasa" \
  [--voice "Mika=shirone-mika"] [--drop 5] [--cover /abs/cover.jpg]
```

- `--voice ID` is the main woman (an onboarded Drama-3 id from `../audiobook/references/voices.md`; check `python3 -m viettts voice list`). If the user names no voice, suggest 2–3 whose `fits` match the script (onee-sama → `pong-kyubi`, `tam-nee`; girlfriend → `lynasa`, `nyan-mikuru`; brat → `shirone-mika`) and let them pick. A second woman is `--voice "Name=id"`.
- The title defaults to the `# Tên tác phẩm` heading in `script.md` if present; otherwise pass `--title` with the user's title or a short one from the script. The cover defaults to the first image next to the source (`.webp` is converted to JPEG at `make`); with none, make a placeholder: `ffmpeg -f lavfi -i "color=c=#2b0f1c:s=1000x1000:d=1" -frames:v 1 <dir>/cover.jpg` and pass `--cover`.
- A dropped chapter renumbers the rest (`Chương 6: …` becomes `Chương 5: …`).
- Settings go to `drama.json`, so `make` needs only the folder. `init` won't overwrite `directed.txt` (your tags) without `--force`.

## 3. Direct `directed.txt` (your job)

`init` wrote every line plain under `## Chương N` (keeping each chapter's full title if it has one) and keeping the source's scene breaks: the **translate** skill sets them from the subtitle timestamps. A source with a blank line after every line has no scene information, so its chapters start as one scene. Rewrite the file in place, with the same chapter headings and lines in the same order:

```text
## Chương 1
[breathless, close to climax] Sắp... [soft moan] em sắp ra rồi...
[trembling, loving] Mình cùng lên đỉnh nha anh.
[panting softly] Ưm, anh rút ra được rồi đó.

[soft, hesitant] À mà...
Anh có chuyện muốn nói sao?
{Mika} [bright, teasing] Chị lại bắt nạt anh ấy rồi~
```

- **Blank line = scene break.** Lines next to each other get the `segment` pause (300 ms), a blank line gives a `paragraph` pause (600 ms), and a chapter ends with 1.7 s.
- **Review the breaks, don't redo them.** The translator placed them from the real silences, so keep them unless one is clearly wrong: a break inside a running exchange, or a missing one where the scene obviously changes (a phone call starts or ends, a new place or person, foreplay → oral → sex, climax → afterglow). Without breaks from the source (`scan` shows `1 scenes` for every chapter), add them yourself with those same changes, typically 6–12 per chapter, never after every line.
- A break usually follows an action without words, so let the next line react: `[breathless]` after sex, `[wet kiss]` around a kiss, `[slurp]` during oral.
- **Tags** follow `../audiobook/references/enhance.md`; read it once, especially "Intimate and spicy scenes". In this format almost every line is performance, so most lines get one short direction (80–90% is normal). 
- Keep the same person: a resisting girlfriend says `[breathy, denying]`, not `[seductive]`, until the script turns.
- **Sounds the user often asks for:** `[soft moan]`, `[moans]`, `[gasps]`, `[whimpers]`, `[pants]`, `[shaky breath]`, `[giggles]`, `[soft chuckle]`, `[purrs]`, `[sniffles]`, `[coughs]`, `[shudders]`, `[wet kiss]`, `[smooch]`, `[slurp]`, `[slurp kiss]`. 
- Put a moan **after the first comma or sentence**, not at the very start (starting moans got retried), and use no more than two sounds per line. 
- Put `[slurp]` only in oral scenes and kisses only where a kiss happens. Directions such as `[moaning]`, `[climaxing, crying out]` or `[sobbing, begging]` carry the mood without being sounds.
- **Paired tags** wrap a few key words: `<emphasis>KHÔNG</emphasis>`, `<forceful>DỪNG LẠI.</forceful>`, `<whisper>…</whisper>`, `<soft>`, `<slow>`, `<fast>`. Never nest them, and never wrap a whole line.
- **Only add tags.** Never change a word, and don't drop or merge lines; `make` compares every line with the source and refuses to write anything if one differs.
- **Two women:** start the second woman's lines with `{Name} ` (the name from `--voice Name=id`). Lines without a prefix belong to the main voice.
- **Long scripts:** write the file in pieces (a chapter or two per edit, appending), so a single write is never cut off. If a write is cut off anyway, rewrite that part.

## 4. Make and check

```sh
python3 $VD make outputs/voice-dramas/<slug>
python3 -m viettts audiobook check outputs/voice-dramas/<slug>/script.txt
```

`make` prints `N problems; nothing written.` with each mismatch (chapter, line number, directed words vs source words). 
Fix `directed.txt` and run it again; the previous `script.txt` and `enhance.txt` are kept as `.bak`. `check` must show `0 with problems` for `enhance.txt`. `narration contains a long quoted passage` findings are expected here (she quotes someone, or an app name) and need no fix: the same voice reads them.

## 5. Build and verify

```sh
python3 -m viettts audiobook build <dir>/script.txt --cast <dir>/cast.json --author "…"
python3 -m viettts audiobook verify <dir>/script.txt
```

- Start the build as a **background** command and don't poll it. Give the user the `status` and `tail -f <dir>/build.log` commands in `bash` blocks.
- Drama-3 voices every line: about 4 minutes per 5k characters, plus about 15–30 s for each retried chunk. A few frame-cap retries per 70 chunks is normal.
- Afterwards, `grep -c "without tags" <dir>/build.log` counts the chunks that fell back to plain words; simplify those entries in `directed.txt` (a shorter direction, one sound fewer), run `make`, and rebuild. Only the changed lines are synthesized again.
- A changed cover, title or blank lines re-encodes from the cache in seconds.
- Report the M4B path, duration, size, voice, the number of tagged lines, the dropped chapters. 
- Record what you learned about the voice with `python3 -m viettts voice note <id> "…"`.

**Optional step**
- Confirm with user to add sound effects (bed, kisses, doors, phone …). It goes on top of the finished build with the **sfx** skill, as a second `(SFX)` M4B.

## Lessons from earlier builds

- Short lines (most under 60 characters) take tags well; long lines with several sounds are the ones that hit the frame cap.
- On a very short line (one or two words), avoid an `-ing` moan direction plus a sound: `[whimpering] Không được...` and `[moaning, ecstatic] … [moans] …` never ended. `[weak, pleading]` and `[ecstatic, breathy]` passed on the first take.
- Identical chapters share cache entries, so a duplicate costs no synthesis, only listening time.
