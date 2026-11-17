# Setup

Run commands from the repository root. Python 3.11+ runs the stdlib-only orchestrator; each engine's `.python-version`, `pyproject.toml`, and `uv.lock` select its own runtime.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/).
- `ffmpeg` and `ffprobe` on `PATH` for reference preparation and M4B packaging.
- `yt-dlp` on `PATH` if importing audio from a URL.
- VieNeu (audiobook builds and `speak --engine vieneu`) runs on GGUF with audio.cpp on Apple Silicon (`brew tap 0xShug0/audio-cpp && brew install audio-cpp`) and falls back to ONNX CPU without it. Drama-3's MLX runner requires macOS on Apple Silicon with Metal available.

```sh
uv sync --locked --project engines/vieneu
uv sync --locked --project engines/drama3
python3 -m viettts --help
python3 -m viettts voice list
```

Drama-3 downloads about 23.8 GB into `models/drama3-4bit-v2`. Upstream reports around 26 GB peak allocation; longer inputs/references can require more memory. The development machine has 48 GiB RAM. Plan additional space for environments, the VieNeu model/codec cache, reference audio, and generated books.

```sh
python3 -m viettts speak --engine drama3 --download-only
```

VieNeu downloads its model and codec on first use. Models are cached under `.cache/huggingface` unless `HF_HOME` is already set. Launchers also default uv cache/download paths to `.uv/`. Keep ONNX external-data files beside their graphs; do not rearrange downloaded model bundles.

## Credentials

Local synthesis normally needs no API key. If Hugging Face requires authentication, authenticate its SDK using your chosen `HF_HOME`; never commit a token.

Voice transcription and reconciliation call NanoGPT. Supply `NANOGPT_API_KEY` in the environment, or:

```sh
python3 -m viettts voice transcribe <voice-id> --key-file /private/path/nanogpt-key
```

The key file must stay outside the repository. Transcription sends reference audio to external providers and can incur charges; run it only for voices you intend to transcribe.

## Paths and existing data

Use absolute story paths. Output defaults and relative cast reference paths resolve against the repository, not the caller's working directory. User-supplied input/output paths otherwise follow the caller's directory.

`python3 -m viettts` is a repository-local command, not an installed global executable. From another directory, set `PYTHONPATH=/absolute/path/to/vietTTS` before invoking it. Workers automatically receive this path.

The cleanup leaves `references/`, `casts/`, `outputs/`, `models/`, `.cache/`, and `.uv/` intact. Obsolete local environment/cache directories may still occupy disk; deleting them is a separate, explicitly scoped operation.

## Development tools

The root `pyproject.toml`, `.python-version`, and `uv.lock` define a separate Python 3.11 development environment:

```sh
uv sync --locked --group dev
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked python -m unittest discover -s tests -v
```

Use `uv run --locked ruff format .` to apply formatting. The development dependencies do not install the TTS models or engine SDKs. NumPy is included so the audio helper tests run without loading an engine.
