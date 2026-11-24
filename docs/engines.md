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

Standalone story mode splits ordinary Markdown into at most 120-character chunks. Tagged mode preserves one chunk per nonempty line, at most 300 UTF-8 bytes, with balanced tags (currently `<whisper>` and bracketed directions/events). Audiobook enhancement supports additional scoped tags; see the [enhancement guide](../.opencode/skills/audiobook/references/enhance.md).

Standalone outputs include `drama3.wav`, numbered chunks, `text.txt`, `performance.jsonl`, and `summary.json`. A failed run can resume with `--resume-dir outputs/<failed-run>` using the same text, model, seed, and reference. Generation at the frame cap is rejected; listening is still needed to detect missing or incorrect words.

## Subtitles

`python3 -m viettts subs transcribe` runs `viettts.subs.worker` in `engines/drama3/` (`mlx-audio==0.6.5`, nothing extra to install). Models are downloaded to the Hugging Face cache on first use, at the revisions pinned in `model-revisions.json`:

1. **Turns:** `OpenMOSS-Team/MOSS-Transcribe-Diarize` (0.9B, Apache-2.0) finds every phrase in one pass, with speaker labels.
2. **Pauses:** its turns run end to end, so each is trimmed to the frames louder than 35% of the way from the track's quiet floor to its loud speech. That brings back the pauses the translate skill reads as scene breaks.
3. **Lines:** one speaker's phrases less than 0.6 s apart are merged, up to 8 s per line. A speaker change always starts a new line; with the default `--speakers 1` the labels are ignored.
4. **Text:** `litagin/anime-whisper` (3 GB, MIT, kotoba-whisper fine-tuned on 5,300 h of galgame voices) transcribes each line. Never feed it a whole track: its long-form output was gibberish. Never give it a prompt either (its model card says prompts cause hallucinations). MOSS's text is the fallback when it returns nothing or loops. Cues that are only punctuation (`…`) are dropped; moans and laughs stay.
5. **Chinese:** anime-whisper only knows Japanese, so a track whose MOSS transcript has (almost) no kana keeps MOSS's own text (simplified characters). `--lang ja|zh` overrides the detection.

On a Mandarin two-angel drama (Nov 2026), MOSS split the two women correctly and its text was the best: in whispered ear-licking lines Qwen3-ASR 1.7B made up whole sentences (我也要舔了 → 我也要点歌, 要稍微加快速度哦 → 要成为家庭主妇了), and Whisper large-v3-turbo misheard 小雅, 双马尾 and 肉棒. MOSS's own slips are sound-alikes for the translator to fix from context: 射箭 for 射精, 小牙 for 小雅, 搜索 for 色色, 肉包 for 肉棒. 48 min of audio took 2 min.

Silero VAD was the first line cutter and was dropped. It treats moaning and breathy speech as silence: in a 15-minute 手マン track it found 20 lines and left 10 minutes empty, where MOSS found 134 lines.

Measured on an M5 Pro with two DLsite tracks (Nov 2026):

| Model | Result |
| --- | --- |
| anime-whisper + VAD | Best text: 道場, 不埒者, 視姦, ご奉仕, and keeps ふふっ. Names drift (ミーナ came out as 美奈). 3 min of audio in 7 s |
| Whisper large-v3-turbo | Clean, but 道場 became 同情, it skips moans, and timestamps slip over SFX |
| Qwen3-ASR 1.7B | Good text, timestamps only per 30 s chunk |
| MOSS-Transcribe-Diarize | 2 women: correct turns, best names, 5 min in 13 s. 1 woman: split her into two speakers when her tone turned cold |
| VibeVoice-ASR 7B | Correct speakers on both tracks and tags `[Human Sounds]`, but weaker text, 17 GB, 106 s for 5 min |
| Sortformer 4spk v2.1 | Heard both women as one speaker |

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
