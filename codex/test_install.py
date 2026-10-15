import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('install.py')

class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='codex install ')
        self.home = Path(self.tmp.name)
        self.other = {'hooks': [{'type': 'command', 'command': 'echo existing-user-hook'}]}
        (self.home / 'hooks.json').write_text(json.dumps({'hooks': {'Stop': [self.other]}}))

    def tearDown(self):
        self.tmp.cleanup()

    def install(self):
        return subprocess.run([sys.executable, str(SCRIPT), '--codex-home', str(self.home)], capture_output=True, text=True)

    def test_install_update_preserves_unrelated_hooks_and_skills(self):
        unrelated = self.home / 'skills' / 'brandkit'
        unrelated.mkdir(parents=True)
        (unrelated / 'SKILL.md').write_text('user skill')
        for _ in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads((self.home / 'hooks.json').read_text())
            self.assertIn(self.other, config['hooks']['Stop'])
            self.assertEqual(len(config['hooks']['Stop']), 2)
            self.assertEqual(len(config['hooks']['PreToolUse']), 1)
        skills = list((self.home / 'skills').glob('ux-ui-*/SKILL.md'))
        self.assertEqual(len(skills), 25)
        self.assertEqual((unrelated / 'SKILL.md').read_text(), 'user skill')
        for file in skills:
            content = file.read_text()
            self.assertNotIn('${CLAUDE_SKILL_DIR}', content)
            self.assertIn('name: ' + file.parent.name, content)
        self.assertTrue(list((self.home / 'backups').iterdir()))

    def test_foreign_name_collision_does_not_mutate_config(self):
        file = self.home / 'skills' / 'ux-ui-design-screen' / 'SKILL.md'
        file.parent.mkdir(parents=True)
        file.write_text('foreign skill')
        before = (self.home / 'hooks.json').read_bytes()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(file.read_text(), 'foreign skill')
        self.assertEqual((self.home / 'hooks.json').read_bytes(), before)

    def test_malformed_config_not_overwritten(self):
        (self.home / 'hooks.json').write_text('{broken')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual((self.home / 'hooks.json').read_text(), '{broken')

if __name__ == '__main__':
    unittest.main()
