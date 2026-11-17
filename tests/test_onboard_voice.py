import contextlib
import io
import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from viettts.paths import ROOT
from viettts.voices import onboarding as onboard_voice
from viettts.voices import registry


class RegistryTests(unittest.TestCase):
    def test_round_trip_and_reference_order_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            voices = Path(directory)
            meta = {'id': 'sample', 'status': 'draft', 'references': []}
            registry.save(meta, voices)
            self.assertEqual(registry.load('sample', voices)['status'], 'draft')
            self.assertEqual(registry.all_voices(voices)[0]['id'], 'sample')
            for n in (10, 2, 1):
                (voices / 'sample' / f'reference-{n}.wav').touch()
                (voices / 'sample' / f'reference-{n}.txt').write_text(f'Lời {n}\n', encoding='utf-8')
            self.assertEqual([n for n, _, _ in registry.refs_of('sample', voices)], [1, 2, 10])
            self.assertEqual(registry.voice_refs('sample', voices)['ref_text'], ['Lời 1', 'Lời 2', 'Lời 10'])

    def test_missing_transcript_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            voices = Path(directory)
            registry.save({'id': 'sample'}, voices)
            (voices / 'sample' / 'reference-1.wav').touch()
            with self.assertRaisesRegex(SystemExit, 'no reviewed transcript'):
                registry.voice_refs('sample', voices)


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg is required for onboarding smoke tests')
class OnboardingSmokeTests(unittest.TestCase):
    def test_cut_and_review_existing_reference_in_temporary_registry(self):
        source = ROOT / 'references' / 'voices' / 'shirone-mika' / 'reference-1.wav'
        transcript = source.with_suffix('.txt').read_text(encoding='utf-8')
        with wave.open(str(source)) as audio:
            duration = audio.getnframes() / audio.getframerate()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            voices = Path(directory) / 'voices'
            with (
                patch.object(onboard_voice, 'VOICES', voices),
                patch.object(onboard_voice, 'WORK', Path(directory) / 'work'),
            ):
                onboard_voice.main(
                    ['cut', 'smoke', '--media', str(source), '--start', '0', '--duration', str(duration)]
                )
                self.assertFalse(onboard_voice.load('smoke')['transcript_reviewed'])
                onboard_voice.main(['set-transcript', 'smoke', '--ref', '1', '--text', transcript])
                saved = onboard_voice.load('smoke')
                self.assertTrue(saved['transcript_reviewed'])
                self.assertEqual(saved['status'], 'draft')
                self.assertEqual(onboard_voice.voice_refs('smoke')['ref_text'], [' '.join(transcript.split())])
                with wave.open(str(voices / 'smoke' / 'reference-1.wav')) as audio:
                    self.assertEqual(audio.getframerate(), 48000)
                    self.assertEqual(audio.getnchannels(), 1)
                    self.assertGreater(audio.getnframes(), 0)

    def test_quiet_reference_is_leveled_to_the_target_without_clipping(self):
        source = ROOT / 'references' / 'voices' / 'shirone-mika' / 'reference-1.wav'
        with tempfile.TemporaryDirectory() as directory:
            quiet = Path(directory) / 'quiet.wav'
            onboard_voice.ffmpeg('-i', str(source), '-af', 'volume=-12dB', '-c:a', 'pcm_s16le', str(quiet))
            gain, before, after = onboard_voice.level(quiet)
            self.assertGreater(gain, 5)
            self.assertLess(before, onboard_voice.TARGET_LUFS - 5)
            self.assertAlmostEqual(after, onboard_voice.TARGET_LUFS, delta=1.0)
            self.assertLessEqual(onboard_voice.loudness(quiet)[1], onboard_voice.PEAK_CEILING_DB + 0.3)


class LevelGainTests(unittest.TestCase):
    def test_gain_reaches_target_but_stops_at_the_peak_ceiling(self):
        self.assertEqual(onboard_voice.level_gain(-26.0, -12.0), 6.0)
        self.assertEqual(onboard_voice.level_gain(-26.0, -4.0), 2.0)  # ceiling -2 dBTP wins
        self.assertEqual(onboard_voice.level_gain(-17.0, -1.0), -3.0)  # too loud is turned down
        self.assertEqual(onboard_voice.level_gain(None, None), 0.0)


class VoiceTableTests(unittest.TestCase):
    def test_table_uses_six_columns_and_keeps_notes_only_in_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voices = root / 'voices'
            voice = voices / 'example'
            voice.mkdir(parents=True)
            metadata = {
                'id': 'example',
                'status': 'onboarded',
                'name': 'Example',
                'gender': 'female',
                'style': 'Warm',
                'accent': 'Southern',
                'fits': 'Heroine',
                'references': [{'duration': 15.5}],
                'metrics': {'duration': 15.5},
                'notes': ['Clear | soft'],
                'contact': 'private contact',
                'source': {'input': 'private-source.wav'},
                'samples': [],
                'sample_retries': 0,
                'samples_model': 'example-revision',
            }
            metadata_file = voice / 'voice.json'
            original_metadata = json.dumps(metadata)
            metadata_file.write_text(original_metadata, encoding='utf-8')
            draft = voices / 'draft'
            draft.mkdir()
            (draft / 'voice.json').write_text(json.dumps({'id': 'draft', 'status': 'draft'}))
            document = root / 'voices.md'
            document.write_text(f'Intro\n{onboard_voice.BEGIN}\nold table\n{onboard_voice.END}\nOutro\n')

            with patch.object(onboard_voice, 'VOICES', voices), patch.object(onboard_voice, 'VOICES_MD', document):
                onboard_voice.write_table()

            self.assertEqual(
                document.read_text(),
                (
                    f'Intro\n{onboard_voice.BEGIN}\n'
                    '| id | Name | Gender | Style / accent | Fits | Reference |\n'
                    '| --- | --- | --- | --- | --- | --- |\n'
                    '| `example` | Example | female | Warm; Southern | Heroine | '
                    '1 × (15.5s) = 15.5s |\n'
                    f'{onboard_voice.END}\nOutro\n'
                ),
            )
            self.assertEqual(metadata_file.read_text(), original_metadata)
