"""VieNeu v3 Turbo as GGUF on audio.cpp's Metal backend: the default VieNeu backend for audiobook builds.

It runs the same pinned model snapshot as the ONNX engine. The text is normalized and phonemized here as
Vieneu.infer() does it, and audio.cpp synthesizes it in one long session per worker. The worker
(viettts.engines.worker) uses ONNX instead when this backend is unavailable, and for any chunk it fails on.
Runs inside the VieNeu environment.
"""

import json
import os
import platform
import pty
import shutil
import subprocess
import zlib
from collections import deque
from pathlib import Path

from viettts.paths import ROOT
from viettts.text import slugify

REPO = 'pnnbao-ump/VieNeu-TTS-v3-Turbo'
REVISION = '61b85e3d937fbbacb387714180e8182823512523'  # the ONNX engine's snapshot (model-revisions.json)
FILENAME = 'gguf/vieneu-v3-turbo-q8_0.gguf'
MODEL_DIR = ROOT / 'models' / 'vieneu-gguf'
MODEL = MODEL_DIR / Path(FILENAME).name
VOICES = MODEL_DIR / 'voices'
CLI = 'audiocpp_cli'
RESTARTS = 3  # audio.cpp sessions restarted after a crash, each skipping the chunk it died on


def unavailable():
    """Why this machine can't use the GGUF backend, or None."""
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        return 'needs Apple Silicon: on the CPU, GGUF is slower than ONNX'
    if not shutil.which(CLI):
        return f'{CLI} not found (brew tap 0xShug0/audio-cpp && brew install audio-cpp)'
    return None


def ensure_model():
    if not MODEL.is_file():
        from huggingface_hub import hf_hub_download

        path = Path(hf_hub_download(REPO, FILENAME, revision=REVISION, local_dir=MODEL_DIR))
        path.replace(MODEL)
        path.parent.rmdir()
    return MODEL


def voice_files(name):
    """(ref_codes.txt, speaker.emb.txt) of a VieNeu preset voice, written from the SDK's own presets on first use."""
    folder = VOICES / slugify(name)
    codes, emb = folder / 'ref_codes.txt', folder / 'speaker.emb.txt'
    if codes.is_file() and emb.is_file():
        return codes, emb
    import numpy as np
    import vieneu
    from vieneu_utils.core_utils import strip_encoder_pad_frame

    presets = json.loads((Path(vieneu.__file__).parent / 'assets' / 'voices_v3_turbo.json').read_text('utf-8'))
    presets = presets['presets']
    aliases = {alias: key for key, v in presets.items() for alias in v.get('aliases') or []}
    preset = presets.get(name) or presets.get(aliases.get(name, ''))
    if not preset or preset.get('codes') is None or preset.get('speaker_emb') is None:
        raise RuntimeError(f'no VieNeu preset voice "{name}"')
    folder.mkdir(parents=True, exist_ok=True)
    # Written to a temporary name first: parallel workers may prepare the same voice.
    tmp = folder / f'.ref_codes.{os.getpid()}.txt'
    np.savetxt(tmp, strip_encoder_pad_frame(np.asarray(preset['codes'], dtype=np.int64).reshape(-1, 16)), fmt='%d')
    tmp.replace(codes)
    tmp = folder / f'.speaker.emb.{os.getpid()}.txt'
    tmp.write_text(','.join(f'{x:.8f}' for x in np.asarray(preset['speaker_emb'], dtype=np.float32).reshape(-1)))
    tmp.replace(emb)
    return codes, emb


def requests_for(index, job, phonemes, codes, emb):
    """audio.cpp requests for one job: one per normalized piece, seeded from the job id so retakes repeat."""
    options = {
        'reference_codes_file': str(codes),
        'speaker_embedding_file': str(emb),
        'seed': str(zlib.crc32(job['id'].encode('utf-8'))),
        'text_chunk_size': '100000',  # the pieces are already cut as Vieneu.infer() cuts them
    }
    return [{'id': f'{index:06d}-{k}', 'text': text, 'options': options} for k, text in enumerate(phonemes)]


def lines(command, status):
    """Stream a command's output lines. audio.cpp buffers a pipe, so it gets a pseudo-terminal."""
    master, slave = pty.openpty()
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=slave, stderr=slave)
    os.close(slave)
    buffer = b''
    try:
        while True:
            try:
                data = os.read(master, 65536)
            except OSError:  # Linux reports the closed terminal as EIO
                break
            if not data:
                break
            *complete, buffer = (buffer + data).split(b'\n')
            for raw in complete:
                yield raw.decode('utf-8', 'replace').rstrip('\r')
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
        status['code'] = process.wait()


def synthesize(jobs, threads, scratch):
    """Yield (job, samples, rate, error) for every job, in order; samples is None where GGUF failed."""
    import soundfile as sf
    from vieneu_utils.core_utils import gaps_to_silence, join_audio_chunks
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps, phonemize_text_with_emotions

    plans: list[tuple[dict, list[dict], list[str], str | None]] = []  # (job, requests, gaps, error)
    for index, job in enumerate(jobs):
        try:
            codes, emb = voice_files(job['voice'])
            pieces, gaps = normalize_to_chunks_v3_with_gaps(job['text'])
            if not pieces:
                raise RuntimeError('nothing to read after normalization')
            phonemes = [phonemize_text_with_emotions(piece) for piece in pieces]
            plans.append((job, requests_for(index, job, phonemes, codes, emb), gaps, None))
        except Exception as error:
            plans.append((job, [], [], str(error)))

    def result(plan):
        job, requests, gaps, error = plan
        if error:
            return job, None, None, error
        waves, rate = [], 0
        for request in requests:
            path = scratch / f'{request["id"]}.wav'
            samples, rate = sf.read(path, dtype='float32', always_2d=True)
            path.unlink()
            waves.append(samples[:, 0])
        audio = waves[0] if len(waves) == 1 else join_audio_chunks(waves, rate, silence_ps=gaps_to_silence(gaps))
        return job, audio, rate, None

    model = ensure_model()
    finished: set[str] = set()
    position, restarts = 0, 0
    while position < len(plans):
        sequence = scratch / 'requests.json'
        requests = [r for plan in plans[position:] for r in plan[1]]
        sequence.write_text(json.dumps({'requests': requests}, ensure_ascii=False), encoding='utf-8')
        command = [CLI, '--task', 'tts', '--family', 'vieneu_v3_turbo', '--model', str(model), '--backend', 'metal']
        command += ['--threads', str(threads), '--request-sequence', str(sequence), '--out-dir', str(scratch)]
        status: dict[str, int] = {}
        tail: deque[str] = deque(maxlen=3)
        for line in lines(command, status) if requests else ():
            if line.startswith('audio_out='):
                finished.add(Path(line[len('audio_out=') :]).stem)
            elif line.strip():
                tail.append(line.strip())
            while position < len(plans) and all(r['id'] in finished for r in plans[position][1]):
                yield result(plans[position])
                position += 1
        while position < len(plans) and all(r['id'] in finished for r in plans[position][1]):
            yield result(plans[position])  # jobs that failed before synthesis, at the end
            position += 1
        if position < len(plans):  # the session stopped early: the chunk it was on goes to ONNX
            job = plans[position][0]
            yield job, None, None, f'audio.cpp exited with {status.get("code")}: {" | ".join(tail)[-200:]}'
            position += 1
            restarts += 1
            if restarts > RESTARTS:
                for job, *_ in plans[position:]:
                    yield job, None, None, f'audio.cpp crashed {restarts} times'
                return
