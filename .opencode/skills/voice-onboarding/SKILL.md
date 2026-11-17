---
name: Voice onboarding (Drama-3)
description: Onboard a new voice for Drama-3 voice cloning from a video or audio file (or a YouTube/stream URL). It finds clean speech, cuts a reference clip, transcribes it with several NanoGPT speech-to-text models and judges, stores the reference and reviewed transcript, generates three ~5 s audition samples, and adds the voice to the audiobook voice list. Use when the user gives a video/audio/link and wants it as a voice, or asks to add, onboard, audition or re-transcribe a voice.
---

# Voice onboarding

Run everything from the vietTTS repository root with the system `python3`. The command is `python3 -m viettts voice`; its subcommands go in this order:

**candidates → cut → transcribe → set-transcript → samples → approve.**

Each voice ends up in `references/voices/<id>/`:
- `reference-1.wav`, `reference-2.wav`, …: the cleaned cuts
- `reference-N.txt`: the reviewed transcript of each cut
- `stt-N.json`: the transcription evidence for each cut
- `samples/`: three auditions
- `voice.json`: the source of truth

**Reference guidance** (Fish Audio's voice-cloning guide, the Drama-3 tech report, and the MLX runtime limits):
- 15–20 s per clip, ideally **2 clips that form one paragraph**. Drama-3 clones from all of them together; going from 1 to 3 references measurably raised speaker similarity.
- Together they may be **at most 30 s**, with up to 4 clips and 1,024 transcript characters (MLX). `cut` trims clips inside natural pauses to fit.
- One speaker, steady volume and tone, and about 0.5 s pauses between sentences. No music, laughter or whispering.

Only onboarded voices can be used for audiobooks.

`approve` regenerates the voice table in `.opencode/skills/viet-audiobook/references/voices.md`.
Notes, samples and source remain in `voice.json`; sample audio lives in `references/voices/<id>/samples/`.

What to get from the user (ask only for what is missing):
- the **file or link**, plus a time range if it is long, otherwise find clean speech yourself
- a **name** for the voice
- the **gender**
- optionally, what kind of character the voice should suit

## 1. Find clean speech, then let the user listen

```sh
python3 -m viettts voice candidates "<file or URL>" --id "<Name>" [--from 18:00 --to 21:00]
```

- Any audio or video format works. A URL is downloaded with yt-dlp; with `--from/--to`, only that range is downloaded.
- For long sources (streams, hours long), ask the user for an approximate range first.
- It analyses the waveform (speech vs. pauses) and prints **4 non-overlapping 15–20 s windows**. They are ranked by speech ratio, with no pause over 0.6 s inside. Each is cut, cleaned and saved to `outputs/voice-onboarding/<id>/candidate-N.wav`.
- **The user decides by ear, not you.** Give them the candidate paths in a table (start, length, speech %, longest pause), then stop and ask them to listen and pick **two**, or one if only one is good. They should check that it's the right person, there's no music or other voices, and the tone is what they want. The metrics only rank the windows; they can't tell a wrong speaker or a bad mood.
- If none is good, rerun with another range, `--max-pause 0.8`, or `--noise-db -35` for noisy sources.

## 2. Cut

```sh
python3 -m viettts voice cut <id> --candidate 1 --candidate 4      # or --start 18:42.5 --duration 16 [--media <file>]
```

This writes `reference-1.wav`, `reference-2.wav` (48 kHz mono, cleaned) and a draft `voice.json`. If the clips add up to more than 30 s (`--max-total`), each is shortened to its share, ending inside a natural pause. Pass on any warnings: a clip under 10 s, a long pause, or a low speech ratio. A new cut replaces the voice's old references.

## 3. Transcribe and review (your job)

The NanoGPT key comes from `NANOGPT_API_KEY` or `--key-file`. If neither is available, ask the user for the key with the secret tool, never in chat, and pass the saved file with `--key-file`. Never print the key.

```sh
python3 -m viettts voice transcribe <id> [--key-file <file>] [--ref N]
```

For each reference, this runs three STT models (Whisper-Large-V3, gpt-4o-mini-transcribe, Wizper). Then audio-listening judges (Qwen omni plus/flash, Perceptron) and a text judge (Claude) each produce a transcript, and Claude adds punctuation without changing any words. Everything is saved to `stt-N.json`, and a draft is printed for each reference.

**Review each draft yourself against all versions in `stt-N.json`, then save each final text:**
- **Hallucinations:** Whisper often invents "Hãy subscribe cho kênh Ghiền Mì Gõ…" or subtitle credits. Remove them.
- **Disputed words:** decide them by meaning and context. For example, "lên Steam tìm" (buying software) beats "lên stream tìm". "Số tiền đã ủng hộ" (money donated) beats "Số tin". Accent-specific forms like "hông" should be kept.
- **Fillers and code-switching:** the omni listeners and gpt-4o keep fillers ("á", "hả", "kiểu") and English words ("check"); Whisper-family models drop them. Trust the listeners when two or more agree.
- **Clip edges:** the clip may start or end mid-phrase. Transcribe exactly what is audible, including fillers.
- **Speaking rate:** it should be about 3.5–5 words/s. A much lower rate means the transcript is incomplete.

```sh
python3 -m viettts voice set-transcript <id> --ref 1 --text "<exact final transcript of reference 1>"
python3 -m viettts voice set-transcript <id> --ref 2 --text "<exact final transcript of reference 2>"
```

Tell the user briefly which disputed words you decided and why.

If a word stays truly uncertain, tell the user which one, with the alternatives.

## 4. Samples, then the user's verdict

```sh
python3 -m viettts voice samples <id> [<id2> ...]      # one Drama-3 run for all voices (~30 GB RAM, ~1–3 min)
```

This makes three ~5 s lines per voice, cloned from all of its references together: narration, playful xianxia dialogue and modern emotional dialogue. A line that fails four times is recorded as failed instead of stopping the run. They're saved to `references/voices/<id>/samples/sample-1..3.wav`, and the retry count and longest pause are reported.
- Run it in the background if several voices are queued.
- The first Drama-3 chunk occasionally stalls for many minutes under memory pressure. That's not an error; wait for the notification.
- Use `--line "<sentence>"` (repeatable) to audition lines closer to the user's book.

Give the user the sample paths, then **stop and wait**. Ask whether the voice sounds like the source, is clear, has no odd pauses or breaths, and fits the character. If they don't like it, go back to step 1 or 2 and pick another cut. Report the **retries** too: the number of takes Drama-3 rejected (it hit the length cap or had a pause over 1.5 s) and regenerated. 0 is very stable; 5 or more over 3 lines means slower builds and more repairs in a real book.

## 5. Approve

Do not run `approve` until the user has approved the auditions.

```sh
python3 -m viettts voice approve <id> --name "<Name>" --gender female --style "<timbre, pitch, tone>" \
  --fits "<characters it suits>" [--accent Southern]
```

This marks the voice `onboarded` and regenerates the voices table. Add anything noteworthy with `python3 -m viettts voice note <id> "<text>"`; notes stay in `voice.json` and are not included in the table. Use `python3 -m viettts voice list` to see every voice and its status.

Tell the user the id. They can use it with the viet-audiobook skill (`--female <id>`).

## After a Drama-3 model change

Samples record the weights that made them (`samples_model` = `viettts.engines.drama3.REVISION`). When the weights change, `list` and builds warn that the samples are stale. Regenerate all voices in one run (`python3 -m viettts voice samples <id> <id> ...`), report the new retry counts next to the old ones, and ask the user to listen again. Approval and transcripts stay valid; the references don't change.
