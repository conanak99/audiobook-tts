import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def cli(self, *args, cwd=ROOT):
        env = {**os.environ, 'PYTHONPATH': str(ROOT)}
        return subprocess.run(
            [sys.executable, '-m', 'viettts', *args], cwd=cwd, env=env, capture_output=True, text=True
        )

    def write_check_book(self, directory, cast=None, speaker='Khả Khả', gender='female'):
        script = directory / 'script.txt'
        script.write_text(
            f'@title T\n@speaker ta male narrator\n@speaker {speaker} {gender}\n## C\n[{speaker}] Xin chào.\n',
            encoding='utf-8',
        )
        if cast is not None:
            (directory / 'cast.json').write_text(json.dumps(cast, ensure_ascii=False), encoding='utf-8')
        return script

    def test_command_groups_have_help_without_engine_dependencies(self):
        for args in [
            (),
            ('audiobook',),
            ('voice',),
            ('subs',),
            ('subs', 'transcribe'),
            ('speak',),
            ('speak', '--engine', 'vieneu'),
            ('speak', '--engine', 'drama3'),
        ]:
            with self.subTest(args=args):
                result = self.cli(*args, '--help')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('usage:', result.stdout)

    def test_imports_do_not_load_engine_sdks(self):
        result = subprocess.run(
            [
                sys.executable,
                '-c',
                'import viettts.cli, viettts.audiobook.cli, viettts.sfx.cli, viettts.subs.cli, viettts.voices.onboarding; '
                'import sys; assert not '
                '({"numpy", "soundfile", "torch", "vieneu", "mlx", "mlx_audio"} & sys.modules.keys())',
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_only_supported_engines_are_accepted(self):
        result = self.cli('speak', '--engine', 'unsupported')
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid choice', result.stderr)

    def test_worker_launch_uses_package_in_correct_environment(self):
        from viettts.paths import ROOT as package_root
        from viettts.paths import uv_command

        command, env = uv_command('drama3', '-m', 'viettts', 'audiobook', 'worker', 'drama3', '/jobs.jsonl', '/cache')
        self.assertEqual(package_root, ROOT)
        self.assertEqual(
            command[:6], ['uv', 'run', '--locked', '--project', str(ROOT / 'engines' / 'drama3'), 'python']
        )
        self.assertEqual(command[6:10], ['-m', 'viettts', 'audiobook', 'worker'])
        self.assertIn(str(ROOT), env['PYTHONPATH'].split(os.pathsep))
        with self.assertRaises(ValueError):
            uv_command('unsupported')

    def test_parse_review_and_paths_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            story = work / 'story_vn.md'
            story.write_text('# Một câu chuyện\n\n## Chương 1\n\nTa nhìn trời.\n', encoding='utf-8')
            out = work / 'book'
            parsed = self.cli('audiobook', 'parse', str(story), '--output', str(out), cwd=work)
            self.assertEqual(parsed.returncode, 0, parsed.stderr)
            script = out / 'script.txt'
            original = script.read_bytes()
            repeated = self.cli('audiobook', 'parse', str(story), '--output', str(out), cwd=work)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(script.read_bytes(), original)
            for action in ('review', 'check', 'status'):
                result = self.cli('audiobook', action, str(script), cwd=work)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_discovers_adjacent_cast(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            script = self.write_check_book(work, {'voices': {'mc': 'Thiện Minh', 'female': 'Ngọc Huyền'}})

            result = self.cli('audiobook', 'check', str(script), cwd=work)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('cast.json: valid', result.stdout)

    def test_check_explicit_cast_overrides_adjacent(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            script = self.write_check_book(work, {'voices': {'female': 'Not A Voice'}})
            override = work / 'chosen.json'
            override.write_text('{"voices": {"mc": "Thiện Minh", "female": "Ngọc Huyền"}}', encoding='utf-8')

            result = self.cli('audiobook', 'check', str(script), '--cast', str(override), cwd=work)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('chosen.json: valid', result.stdout)
            self.assertNotIn('Not A Voice', result.stdout)

    def test_check_accepts_named_speaker_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            script = self.write_check_book(work, {'voices': {'Khả Khả': 'lynasa'}})

            result = self.cli('audiobook', 'check', str(script), cwd=work)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Khả Khả=lynasa (drama3', result.stdout)

    def test_check_without_cast_skips_cast_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            script = self.write_check_book(work)

            result = self.cli('audiobook', 'check', str(script), cwd=work)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('cast.json', result.stdout)
            self.assertNotIn('cast:', result.stdout)

    def test_check_rejects_unknown_cast_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            script = self.write_check_book(work, {'voices': {'Khả Khả': 'Not A Voice'}})

            result = self.cli('audiobook', 'check', str(script), cwd=work)

            self.assertEqual(result.returncode, 1)
            self.assertIn('cast: Unknown voice "Not A Voice"', result.stdout)
            self.assertIn('Not buildable yet: fix the cast errors above.', result.stdout)

    def test_check_rejects_unmatched_cast_key(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            script = self.write_check_book(work, {'voices': {'Kha Kha': 'lynasa'}})

            result = self.cli('audiobook', 'check', str(script), cwd=work)

            self.assertEqual(result.returncode, 1)
            self.assertIn('cast: key "Kha Kha" is not a role or a speaker in script.txt', result.stdout)

    def test_check_rejects_unresolved_speaker_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            script = self.write_check_book(work, {'voices': {'mc': 'Thiện Minh', 'female': 'Ngọc Huyền'}}, speaker='Bí Ẩn', gender='?')

            result = self.cli('audiobook', 'check', str(script), cwd=work)

            self.assertEqual(result.returncode, 1)
            self.assertIn('cast: Speaker "Bí Ẩn" has no voice', result.stdout)

    def test_existing_voice_registry_and_cast_are_readable(self):
        result = self.cli('voice', 'list')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('shirone-mika', result.stdout)
        from viettts.audiobook.cast import load_cast

        for path in (ROOT / 'casts').glob('*.json'):
            self.assertNotIn('engine', json.loads(path.read_text()))  # each voice picks its own engine
            mix, voices = load_cast(path)
            self.assertEqual(mix, path.stem)  # casts/<mix>.json
            self.assertEqual(set(voices), set(json.loads(path.read_text())['voices']))

    def test_active_guides_use_current_commands(self):
        paths = list((ROOT / '.opencode' / 'skills').rglob('*.md'))
        paths += list(ROOT.glob('README*.md'))
        paths += list((ROOT / 'docs').glob('*.md'))
        for path in paths:
            with self.subTest(path=path):
                text = path.read_text(encoding='utf-8')
                for old in (
                    'python3 run_audiobook.py',
                    'python3 onboard_voice.py',
                    'python3 run_drama3.py',
                    'python3 run_story.py',
                ):
                    self.assertNotIn(old, text)


if __name__ == '__main__':
    unittest.main()
