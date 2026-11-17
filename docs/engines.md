# Engines & troubleshooting

## VieNeu

- `vieneu==3.8.3`; v3 Turbo ONNX FP32, CPU.
- Environment: `engines/vieneu/`.
- Model: `pnnbao-ump/VieNeu-TTS-v3-Turbo`; codec: `OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX`.
- The model bundle is approximately 475 MB, plus codec and voices. Tested snapshots are recorded in `model-revisions.json`; retain the cache to reproduce those model assets.

### GGUF backend (default)

Audiobook builds and `speak` run VieNeu as GGUF on [audio.cpp](https://github.com/0xShug0/audio.cpp)'s Metal backend (`--vieneu-backend gguf`, the default). It is the same v3 Turbo model as the ONNX path: `gguf/vieneu-v3-turbo-q8_0.gguf` from the same pinned revision (`61b85e3`), built by the model's author from the `update/` weights that `onnx_update/` also uses.

- Install: `brew tap 0xShug0/audio-cpp && brew install audio-cpp` (provides `audiocpp_cli`).
- Files: `models/vieneu-gguf/vieneu-v3-turbo-q8_0.gguf` (188 MB, downloaded on first use) and `models/vieneu-gguf/voices/<voice>/{ref_codes.txt,speaker.emb.txt}`, written on first use from the SDK's own preset voices, so they match the ONNX presets exactly.
- The worker normalizes and phonemizes the text as `Vieneu.infer()` does, then runs one audio.cpp session per worker for its whole shard.
- Fallback to ONNX: the whole worker uses ONNX when `audiocpp_cli` is missing, the machine is not Apple Silicon (on the CPU, GGUF is slower than ONNX) or the model can't be downloaded; `build.log` says why. A chunk audio.cpp fails on is made with ONNX, and the session restarts for the rest (`GGUF failed … using ONNX` in `build.log`).
- `--vieneu-backend onnx` forces the CPU path. Both backends share `cache/vieneu/`, so switching reuses cached chunks.
- Checked on an M5 Pro: every chunk of a 3-chapter build is closest to its own preset voice (speaker-encoder similarity). The 0.98 similarity to ONNX output was measured on a 35 s passage, not on every chunk. The GGUF path has no audio watermark (the Python SDK adds one).

```sh
python3 -m viettts speak --engine vieneu --list-voices
python3 -m viettts speak --engine vieneu --voice "Hải Đăng" --text "Xin chào!"
python3 -m viettts speak --engine vieneu --runs 3 --warmup 1 --threads 4
python3 -m viettts speak --engine vieneu --runs 3 --backend onnx   # force the CPU path
```

`speak` uses the GGUF backend below by default, with the same ONNX fallback; one audio.cpp session serves the warm-up and every run. Each run writes WAV files and `results.json` under `outputs/vieneu-<timestamp>/`, including the backend of each run, load time, synthesis time, duration, and RTF (synthesis seconds/audio seconds; lower is faster). Measured on an M5 Pro with a 3.3 s sentence: RTF 0.079 on GGUF, 0.109 on ONNX. WAV checks reject empty, silent, or nonfinite audio; they do not establish pronunciation quality.

## Drama-3

- Model: `mlx-community/fish-audio-drama-3-4bit`, pinned revision `2b0c8028998533972e77359cce56b8bf1c5d6d4a` (V2).
- Mixed precision: routed experts INT4; dense projections and audio tower INT8.
- Runtime: MLX Metal, `mlx-audio==0.6.5`, environment `engines/drama3/`.
- Model directory: `models/drama3-4bit-v2`.
- Sampling remains temperature 0.7, top-p 0.7, top-k 30. A seed is not a cross-hardware reproducibility guarantee.

```sh
python3 -m viettts speak --engine drama3 --text "Xin chào!"
python3 -m viettts speak --engine drama3 --input /path/chapter.md
python3 -m viettts speak --engine drama3 --text "Xin chào!" \
  --ref-audio /path/reference.wav --ref-text "Exact words in the reference."
python3 -m viettts speak --engine drama3 --tagged-input /path/tagged.txt
```

The standalone default is the retained synthetic Mai Chi reference, `references/maichi-synthetic.wav`. It is a reference asset, not a model dependency or named Drama-3 preset.

Standalone story mode splits ordinary Markdown into at most 120-character chunks. Tagged mode preserves one chunk per nonempty line, at most 300 UTF-8 bytes, with balanced tags (currently `<whisper>` and bracketed directions/events). Audiobook enhancement supports additional scoped tags; see the [enhancement guide](../.opencode/skills/viet-audiobook/references/enhance.md).

Standalone outputs include `drama3.wav`, numbered chunks, `text.txt`, `performance.jsonl`, and `summary.json`. A failed run can resume with `--resume-dir outputs/<failed-run>` using the same text, model, seed, and reference. Generation at the frame cap is rejected; listening is still needed to detect missing or incorrect words.

## Troubleshooting

- **MLX/Metal unavailable:** use an Apple Silicon terminal with GPU access. This repository does not implement the NVIDIA runtime.
- **Memory pressure:** run Drama-3 sequentially; do not launch multiple cloned-voice builds at once.
- **Missing ONNX external data:** keep cache files together and rerun the download instead of moving individual files.
- **Wrong speaker:** review and correct `script.txt`; synthesis cannot repair attribution.
- **Long silences:** inspect `audiobook repair <script> --dry-run`. Run repair without `--dry-run` only when ready to delete affected cache chunks, then rebuild. Never repair during a build.
- **Stale auditions:** `voice list` warns when samples were generated with older Drama-3 weights. Regenerate and listen again; do not discard source references.
- **Quality checks:** finite/nonzero PCM and valid M4B metadata do not prove voice similarity, pronunciation, or spoken-word accuracy.

Historical local Drama-3 tests with the older V1 checkpoint produced valid chapter WAVs but did not validate pronunciation by listening; they are not performance claims for V2.

[Upstream runtime](https://blaizzy.github.io/mlx-audio/models/tts/fish-drama3.html) · [Model and license](https://huggingface.co/mlx-community/fish-audio-drama-3-4bit)
