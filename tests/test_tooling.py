import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('ruff'), 'Ruff is installed in the root dev environment')
class RuffScopeTests(unittest.TestCase):
    def test_all_project_python_files_are_included(self):
        result = subprocess.run(
            [sys.executable, '-m', 'ruff', 'check', '.', '--show-files'],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        included = {Path(line) for line in result.stdout.splitlines()}
        for folder in ('viettts', 'tests', 'scripts'):
            for path in (ROOT / folder).rglob('*.py'):
                with self.subTest(path=path):
                    self.assertIn(path, included)
        self.assertFalse(any('.venv' in path.parts for path in included))
