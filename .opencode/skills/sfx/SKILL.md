---
name: Sound effects for audiobooks and voice dramas
description: Use when the user wants sound effects (SFX, tiếng động, hiệu ứng âm thanh) added to an audiobook or voice drama that is already built (bed creaking, kisses, wet or skin sounds, zippers, doors, phones, rain, room tone ...), wants a sound added to or regenerated in the SFX library, or asks for the "(SFX)" version of a book. Covers timing script lines, picking sounds into sfx.txt, generating missing sounds with MOSS-SoundEffect v2, and mixing a second M4B while keeping the voice-only one.
---

# Sound effects for audiobooks and voice dramas

Adds a layer of sound effects under a **finished** build from the **audiobook** or **voice-drama** skill. The voice-only `.m4b` is never touched; the mix is a second file, `<Title> (SFX).m4b`, with the same chapters and cover.

Run everything from the repository root with the system `python3`. The book folder is the one with `script.txt`, `chapters/` and the `.m4b` (`outputs/voice-dramas/<slug>/` or `outputs/audiobooks/<slug>/`).

Pipeline: **timeline → you pick the cues (`sfx.txt`) → add and generate any missing sounds → check → mix → the user listens.**

## 1. Timeline

```sh
python3 -m viettts sfx timeline <dir>/script.txt --show [--chapter 2]
```

This replays the build's chunk, trim and pause arithmetic, checks it against `chapters/NN.wav` to the exact frame, and writes `timeline.json`. It prints every spoken line as `L<n>  <start in chapter>  <length>  <text with its enhance.txt tags>`, with a blank line at each scene break. Builds from now on write `timeline.json` themselves; the command still works for older books.

- It needs a full build (not `--chapters`/`--only`), with every chunk cached and the same cast (`cast.json` beside the script by default, `--cast` otherwise).
- It refuses when `script.txt`, `enhance.txt` or the cast changed after the build: the times would be wrong. Rebuild first.

## 2. Pick the cues (your job)

Write `<dir>/sfx.txt`, one cue per line, using the script's line numbers:

```text
# ch1: the end of sex in his room
L9-L12: bed-creak-medium
L9-L11: skin-slap-slow gain=-18
L13: sheets-rustle
L59: phone-ringtone at=-1.5          # "có tiếng chuông gì đang reo kìa"
L75: call-end-beep at=end
L291: door-knock-soft at=end clear    # plays alone; L293 waits for it
```

- `L<a>-L<b>` is a span on one chapter. A **loop** fills it from the start of L<a> to the end of L<b>, including the pauses between the lines. It's repeated with crossfades or cut, with a 0.3 s fade in and a 0.5 s fade out. A **one-shot** plays whole from its anchor.
- Options: `at=start` (default) | `at=end` (one-shots: as the last line ends, in the pause) | `at=<±seconds>` from the first line's start. `len=<seconds>` shortens it. `gain=<dB>` against the library level. `take=<n>` pins one take. `clear` puts a one-shot in the foreground (below).
- **`clear`: a sound in the foreground.** Her lines sit only 0.3 s apart (0.6 s at a scene break), so a one-shot at a line's end would play over the next line. Add `clear` to a one-shot at `at=end` (in the pause after the line) or `at=start` (in the pause before it). The mix then inserts silence, so the sound plays alone and the next line waits until 0.25 s after it ends. Clear sounds default to `gain=-5`.
  - Use it for a sound the next line **reacts to** ("nó phụt ra mất rồi", "Tự dưng anh làm gì thế…", "vị nó hơi đắng"), and for a sound that opens a scene (a knock, a door, a call ending). Typically 10–20 per book, adding 20–40 s.
  - Keep everything else under the voice: zippers and belts while she talks, kisses inside a line, and all loops. Loops that run across a clear gap keep going through it.
  - At most one `clear` cue per pause. The pause after L291 is the same pause as the one before L293.
  - Only the `(SFX)` book gets longer. `timeline.json` keeps the voice-only times; the mix writes `timeline-sfx.json` and `chapters-sfx.ffmeta` with the shifted ones.
- **Takes vary by themselves.** A sound with several takes plays them in turn: its 1st cue in the book gets take 1, the 2nd take 2, and so on (book order, not `sfx.txt` order). A loop strings its takes together as it repeats. So write `squirt-splash` three times and three different splashes play; pin with `take=` only to repeat one on purpose.
- The default gains fit Drama-3 voices (about −21 dBFS speech): loops −14 dB, one-shots −8 dB. Go to −18…−22 for a texture that runs a long time or sits under quiet lines, and −4…−6 for a sound the line reacts to (a slap, a knock).
- **Only sounds that happen now.** When she *tells* what happened ("em bị ép phải liếm…", a report to the boyfriend), add nothing. In her own scene, follow the text: `nhóp nhép`, `bạch bạch`, `phụt`, a phone ringing, a door, tea, a kiss.
- **Follow the pace the text gives.** "nhấp rất chậm" is a slow loop, "dập nhanh", "mãnh liệt quá" a fast one. Change the loop at the line where the pace changes, rather than running one loop through a whole scene.
- **Place.** Add a bed only where there is one (a bed, "lên giường", a bedroom). Standing against a wall gets skin sounds and no creak. Use at most two loops at the same moment: one texture (the bed) and one contact sound (skin or wet).
- **Spans:** a loop can run as long as the scene needs. The mixer builds it from its takes in shuffled order, cuts every seam in a quiet moment (between two slaps or creaks), and adds a slow ±1.5 dB drift, so a minute of the same loop doesn't sound repeated. Still break a scene where the text changes pace (slow → medium → fast → afterglow), since a bed doesn't speed up by itself. A loop's lines must hold at least 0.25 s of sound.
- **Doubling Drama-3 sounds.** Lines with `[slurp]`, `[wet kiss]` or `[moans]` already carry the voice's own sound. A quiet loop under them (`gain=-18`) is fine, but don't add a one-shot of the same thing at the same moment.
- **Before a line, not after it.** A sound the line reacts to ("Tự dưng anh làm gì thế…" after a kiss) starts just before it: `at=-0.6`. A one-shot never starts before 0 in its chapter.
- **No voices in the library.** Moans, panting and groans come from the Drama-3 voice tags (`[moans]`, `[pants]` …), not from sound effects; the men in a voice drama stay silent. Don't add vocal sounds to the library.
- **Cum and squirts.** `cum-spurt` only when it lands outside ("bắn ra", on skin or sheets), not for "bắn vào trong". `squirt-splash` (short), `squirt-gush` (strong, "phụt ra") and `squirt-drip` (a quiet loop after) cover squirting; each has several takes.
- See what's available: `python3 -m viettts sfx list [--category body]`. Ids are in `references/sfx/library.json`, by category: `bed`, `undress`, `body`, `props`, `scene`.

## 3. Missing sounds

If a scene needs a sound the library lacks, add it, render it, and listen before using it:

```sh
python3 -m viettts sfx add phone-ringtone --category props --kind loop --seconds 10 \
  --prompt "A smartphone ringing with a classic electronic ringtone on a table, no voice."
python3 -m viettts sfx generate                 # renders every take still missing
python3 -m viettts sfx takes squirt-splash 4    # more variants of a sound heard often; generate renders them
python3 -m viettts sfx generate phone-ringtone --force --seeds 3,4,5   # every take again, from new seeds
```

- **takes** (`--takes`, default 3): the take as listed plus two variants, each with its own seed and its own length (take 2 is 0.6×, take 3 is 1.5× the listed seconds), so no sound plays the same twice in a row. Use 4–5 for a sound that repeats a lot in one book. Every take is gated on its own. Remove a sound with `python3 -m viettts sfx remove <id>`.
- **kind:** `loop` for a steady texture that can be cut anywhere (creaking, slapping, rain, a ringtone). `oneshot` for one event (a knock, a zipper, a slap, a beep).
- **Length:** 2 s for one-shots (half of all Drama-3 lines are under 2 s). **10 s for loops**, so their takes are 10/6/15 s: long scenes then need few seams.
- **Prompt:** one concrete English sentence (what, how, where, close or far), ending in `no voice, no music.` (drop "no music" only for a ringtone or a melody). English prompts came out about 16× louder and more on-topic than the same prompt in Chinese.
- `generate` runs MOSS-SoundEffect v2 in `engines/sfx` on the Apple GPU. It takes about 45 s per take (50 steps), whatever its length up to 30 s, plus the first-time model load. MOSS always denoises a 30 s window; never shrink it with `max_inference_seconds` to go faster, because a smaller window gives loud, broken audio. Takes are at least 2 s, since MOSS mostly renders silence for shorter lengths. The first run downloads about 10 GB to `models/moss-soundeffect-v2/`.
- Each take must have enough level and sound in most of it (a near-silent take is common). Otherwise the next seed is tried. A take that fails on all three seeds is kept but listed as `weak <n>` (`sfx list`): listen to it, try `--seeds 3,4,5`, or reword the prompt (`--force`).
- Start `generate` as a **background** command when it renders more than a few sounds, and don't poll it.

## 4. Check and mix

```sh
python3 -m viettts sfx check <dir>/script.txt
python3 -m viettts sfx mix <dir>/script.txt --only 4      # one chapter as "<Title> (SFX chương 4).m4a"
python3 -m viettts sfx mix <dir>/script.txt               # the whole book: "<Title> (SFX).m4b"
```

- `check` reports how many clear cues there are and how many seconds they add, and names each problem by its `sfx.txt` row: an unknown or unrendered sound, a line that isn't spoken, a span across chapters, a loop that is too short. `mix` runs the same checks and mixes nothing while any problem is left.
- `mix` writes `chapters-sfx/NN.wav` and encodes with the voice-only book's chapter marks and cover. A soft limiter keeps peaks under −1 dBFS; it reports how many samples it touched, which should be few or none. Many touched samples mean a gain is too high.
- A changed `sfx.txt` needs only another `mix` (about a minute for a 35-minute book). Nothing is synthesized again.

## 5. Listen and report

Ask the user to listen to a chapter with a sex scene and one with doors or a phone. Have them check that:
- the sounds sit under her words and don't cover them
- the loops follow the pace
- no sound plays in a memory scene
- no one-shot lands late

Adjust with `gain=`, `at=` or a different id, then `mix` again. Report the M4B path, the number of cues and sounds used, and any new sounds you added to the library.
