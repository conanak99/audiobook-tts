"""The cast: which voice reads each role or speaker, and so which engine."""

import json
import sys
from pathlib import Path

from viettts.engines.drama3 import REVISION as DRAMA3_REVISION
from viettts.paths import ROOT
from viettts.text import slugify
from viettts.voices import registry

from .script import NARRATION

# The cast picks every voice, and each voice picks its engine: a VieNeu voice name runs on VieNeu; an onboarded
# voice id (references/voices/<id>/, see viettts.voices.onboarding) runs on Drama-3. Roles a cast leaves out get
# these defaults (casts/mixed.json): fast VieNeu narration and men, a Drama-3 cloned heroine, and the MC's
# dialogue on DEFAULT_MC, the Drama-3 clone of the narrator voice, so it takes enhance.txt tags. The MC default
# applies only with the default narrator; a cast with another narrator keeps the MC on that narrator's voice
# unless it sets "mc" itself. A cast may also give any speaker a voice.
VOICES_DIR = ROOT / 'references' / 'voices'


DEFAULT_FEMALE = 'shirone-mika'


DEFAULT_VOICES = {'narrator': 'Thiện Minh', 'male': 'Hải Đăng', 'female': DEFAULT_FEMALE}


DEFAULT_MC = 'thien-minh-drama'


# Manual picked
VIENEU_VOICES = [
    # male voices
    'Adam bựa',
    'Thiện Minh',
    'Hải Đăng',
    'Đức Trí',
    'Thái Sơn',
    # female voices
    'Thùy Dung',
    'Ngọc Huyền',
    'Kim Thanh',
    'Mỹ Duyên',
    'Thục Đoan',
]


ROLES = ('narrator', 'mc', 'male', 'female')


def load_cast(cast_path=None):
    """Returns (mix, {role or speaker: (engine, voice)}) from a cast JSON (--cast), the only place voices are
    chosen; None gives the defaults.

    Roles: narrator, mc, male, female; any other key is a speaker id from the script. A voice is a VieNeu
    name or an onboarded Drama-3 voice id, and that alone decides its engine. mix is "vieneu" or "drama3"
    when every voice runs on that engine, else "mixed"."""
    cast = json.loads(cast_path.read_text(encoding='utf-8')) if cast_path else {}
    if 'engine' in cast:
        raise SystemExit(
            f'{cast_path}: remove "engine"; each voice picks its own engine '
            '(a VieNeu name runs on VieNeu, an onboarded voice id on Drama-3).'
        )
    specs = {**DEFAULT_VOICES, **cast.get('voices', {})}
    if 'mc' not in specs and specs['narrator'] == DEFAULT_VOICES['narrator']:
        specs['mc'] = DEFAULT_MC
    voices = {key: resolve_voice(spec) for key, spec in specs.items()}
    return cast_mix(voices), voices


def cast_mix(voices):
    engines = {engine for engine, _ in voices.values()}
    return engines.pop() if len(engines) == 1 else 'mixed'


def unmatched_cast_keys(voices, script):
    """Cast keys that are neither a role nor a speaker id in the script (a typo keeps the default voice)."""
    return [key for key in voices if key not in ROLES and key not in script.speakers]


def onboarded_voices():
    return {info['id']: info for info in registry.all_voices(VOICES_DIR)}


def resolve_voice(spec):
    """'Thiện Minh' -> VieNeu; an onboarded voice id ('lynasa') -> Drama-3 with its reviewed reference.

    Raw audio files are refused: onboard them first (python3 -m viettts voice), so every Drama-3 voice has a clean
    cut, a reviewed transcript and auditioned samples. The VieNeu-made male references
    (references/vieneu-*.wav, from make-ref) are the only files accepted directly.
    """
    if isinstance(spec, dict) and spec.get('engine') == 'vieneu':
        return 'vieneu', spec['voice']
    onboarded = onboarded_voices()
    key = slugify(str(spec)) if isinstance(spec, str) else None
    if key is not None and key in onboarded:
        info = onboarded[key]
        if info.get('status') != 'onboarded':
            raise SystemExit(
                f'Voice "{key}" is still a draft; finish onboarding it (python3 -m viettts voice approve).'
            )
        if info.get('samples') and info.get('samples_model') != DRAMA3_REVISION:
            print(
                f'warning: the samples of "{key}" were made with older Drama-3 weights; '
                f'regenerate them (python3 -m viettts voice samples {key}) and listen again',
                file=sys.stderr,
            )
        return 'drama3', registry.voice_refs(key, VOICES_DIR)
    if isinstance(spec, dict) or str(spec).lower().endswith('.wav'):
        path = Path(spec['ref_audio'] if isinstance(spec, dict) else spec)
        path = path if path.is_absolute() else ROOT / path
        if path.parent == ROOT / 'references' and path.name.startswith('vieneu-'):
            return 'drama3', drama3_voice(spec)
        raise SystemExit(
            f'{spec}: not an onboarded voice. Onboard it first (voice-onboarding skill / '
            f'python3 -m viettts voice), then use its id. Onboarded: {", ".join(onboarded) or "none"}.'
        )
    if spec in VIENEU_VOICES:
        return 'vieneu', spec
    raise SystemExit(
        f'Unknown voice "{spec}". Use an onboarded id ({", ".join(onboarded) or "none"}) or a VieNeu '
        f'voice ({", ".join(VIENEU_VOICES)}).'
    )


def voice_label(engine, voice):
    if isinstance(voice, str):
        return f'{voice} ({engine})'
    refs = voice['ref_audio'] if isinstance(voice['ref_audio'], list) else [voice['ref_audio']]
    return (
        f'{Path(refs[0]).parent.name if len(refs) > 1 or "voices" in refs[0] else Path(refs[0]).name}'
        f' ({engine}, {len(refs)} ref{"s" if len(refs) > 1 else ""})'
    )


def drama3_voice(spec):
    """A Drama-3 voice is a reference WAV plus its exact transcript."""
    if isinstance(spec, dict):
        audio, text = Path(spec['ref_audio']), spec.get('ref_text')
    else:
        audio, text = Path(spec), None
    audio = audio if audio.is_absolute() else ROOT / audio
    if not text and audio.with_suffix('.txt').is_file():
        text = audio.with_suffix('.txt').read_text(encoding='utf-8').strip()
    if not audio.is_file() or not text:
        raise SystemExit(f'Drama-3 voice needs a reference WAV and its transcript: {audio}')
    return {'ref_audio': str(audio), 'ref_text': text}


def voice_for(label, speakers, voices, unknown, narrator=None):
    """Voice key for a script label. The first-person MC (the narrator's own id) speaks with the cast's
    "mc" voice (or a voice mapped to the MC's id), else with the narrator voice: usually one person."""
    if label == NARRATION:
        return 'narrator'
    if label in voices:
        return label
    if label == narrator:
        return 'mc' if 'mc' in voices else 'narrator'
    gender = speakers.get(label, 'male' if label == 'male' else 'female' if label == 'female' else '?')
    if gender in ('male', 'female'):
        return gender
    if unknown == 'narrator':
        return 'narrator'
    raise SystemExit(
        f'Speaker "{label}" has no voice: set "@speaker {label} male|female" in the script, '
        f'map it in --cast, or pass --unknown narrator.'
    )
