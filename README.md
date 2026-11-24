# Vietnamese voices & audiobooks

Onboard Vietnamese voices and turn Markdown stories into reviewed, multi-voice **M4B audiobooks** for BookPlayer.

- **VieNeu:** fast preset voices, GGUF on audio.cpp Metal (ONNX CPU fallback).
- **Drama-3:** cloned voices and directed performances, MLX on Apple Silicon.

[Setup](docs/setup.md) · [Audiobooks](docs/audiobook.md) · [Voice onboarding](docs/voices.md) · [Engines & troubleshooting](docs/engines.md)

## Install

Install Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/), and FFmpeg (`ffmpeg` + `ffprobe`). URL onboarding also needs `yt-dlp`.

From this repository:

```sh
uv sync --locked --project engines/vieneu
uv sync --locked --project engines/drama3
uv sync --locked --project engines/sfx      # optional: sound effects (MOSS-SoundEffect v2, ~10 GB model)
```

The orchestration package uses only the standard library. Engine commands automatically launch Python in their isolated, locked uv environments. Drama-3 needs Apple Silicon and substantial RAM/disk; see [setup](docs/setup.md).

## Make an audiobook

```sh
python3 -m viettts audiobook parse /absolute/path/story_vn.md
python3 -m viettts audiobook review outputs/audiobooks/<slug>/script.txt --batch 40
# Review speaker assignments; apply answers or edit script.txt, then:
python3 -m viettts audiobook check outputs/audiobooks/<slug>/script.txt
python3 -m viettts audiobook build outputs/audiobooks/<slug>/script.txt --chapters 1
python3 -m viettts audiobook verify outputs/audiobooks/<slug>/script.txt --partial
```

Voices come from one cast JSON (`--cast`). Without it, builds use VieNeu for the narrator and men and an approved Drama-3 heroine (`casts/mixed.json`). Use `--cast casts/vieneu.json` for preset voices only, or copy a cast to pick the heroine, the MC (`"mc"`) or any speaker. Remove `--chapters 1` for the complete book; cached chunks are reused.

## Onboard a voice

```sh
python3 -m viettts voice candidates /absolute/path/source.mp4 --id my-voice
# Listen and select clean clips:
python3 -m viettts voice cut my-voice --candidate 1 --candidate 2
python3 -m viettts voice transcribe my-voice
# Review the exact spoken words before saving each transcript:
python3 -m viettts voice set-transcript my-voice --ref 1 --file /path/ref1.txt
python3 -m viettts voice set-transcript my-voice --ref 2 --file /path/ref2.txt
python3 -m viettts voice samples my-voice
# Approve only after listening:
python3 -m viettts voice approve my-voice --gender female
```

Transcription uses NanoGPT and needs `NANOGPT_API_KEY` or `--key-file`; never commit secrets. Existing approved voices: `python3 -m viettts voice list`.

## Add sound effects

```sh
python3 -m viettts sfx timeline outputs/voice-dramas/<slug>/script.txt --show
# Write sfx.txt beside the script ("L9-L14: bed-creak-medium", "L30: door-knock-soft at=end"), then:
python3 -m viettts sfx check outputs/voice-dramas/<slug>/script.txt
python3 -m viettts sfx mix outputs/voice-dramas/<slug>/script.txt
```

The mix is a second book, `<Title> (SFX).m4b`; the voice-only one is kept. Sounds come from `references/sfx/` (`python3 -m viettts sfx list`); add one with `sfx add` and render it with `sfx generate` (MOSS-SoundEffect v2 on the Apple GPU).

## Transcribe Japanese or Chinese voice dramas

```sh
python3 -m viettts subs transcribe /absolute/path/track01.mp3            # or a folder of tracks
python3 -m viettts subs transcribe /absolute/path/folder --speakers 2    # two voices: cues get <v S1>/<v S2>
```

A folder (or several files) becomes one book: `outputs/subtitles/<folder name>/source.md` has one chapter per file, in natural name order (`2` before `10`), titled with the file name without its track number (`track01_プロローグ.mp3` → `## プロローグ`). It is the input of the translate skill; one `.vtt` per file is written beside it. It runs locally on MLX in the Drama-3 environment: MOSS-Transcribe-Diarize finds every phrase (moaned ones included) and who says it, and [anime-whisper](https://huggingface.co/litagin/anime-whisper) transcribes each line, keeping moans and laughs. Chinese tracks (detected per track, or `--lang zh`) keep MOSS's own text, since anime-whisper only knows Japanese. `--speakers 2` also labels the cues. Names come out unevenly, so check them before translating. See [engines](docs/engines.md#subtitles).

## Test speech

```sh
python3 -m viettts speak --engine vieneu --text "Xin chào!" --voice "Hải Đăng"
python3 -m viettts speak --engine drama3 --text "Xin chào!"
python3 -m viettts --help
```

## Layout & development

`viettts/audiobook/` owns attribution, review, and builds; `viettts/voices/` owns onboarding and the registry; `viettts/engines/` owns synthesis runners and workers; `viettts/sfx/` owns the sound-effect library and mixing. `viettts/text.py` and `viettts/paths.py` hold shared helpers. `engines/` contains only the runtime environments (VieNeu, Drama-3, and SFX).

`references/` and `casts/` are reusable inputs. Model weights live in `models/` or `.cache/`; generated books and audio live in `outputs/` (ignored by Git). Cleanup does not remove these assets.

```sh
uv sync --locked --group dev
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked python -m unittest discover -s tests -v
```

To format code, use `uv run --locked ruff format .`. Ruff covers the package, scripts, and tests, excluding runtime environments, models, caches, and generated assets.

The root environment contains only development tools and NumPy for audio helper tests; neither engine SDK is installed there. Engine environments and lockfiles stay separate. Keep MLX synthesis tests sequential to avoid memory contention.

Typing is gradual: mypy checks bodies throughout `viettts/`, with required annotations on the shared text/path helpers, CLI entry point, and voice registry. Missing third-party typing is allowed only for the engine SDKs. Dynamic JSON metadata remains flexible; new typed APIs should use concrete types rather than blanket ignores.

**Migration:** the former top-level `run_*.py` / `onboard_voice.py` commands have been replaced by the command groups above. Existing scripts, casts, voice metadata, and cache formats remain supported; the repository and asset paths have not moved.
