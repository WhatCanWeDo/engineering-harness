"""Portable installation regression checks; all destinations are temporary homes.

Only the existing managed Python is used. No dependency installation, UI, native
agent session, or existing Knowledge database is accessed by these checks.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv/bin/python'
MANIFEST = json.loads((ROOT / 'scripts/skills-manifest.json').read_text())


@unittest.skipUnless(PYTHON.is_file(), 'requires the existing managed Python')
class PortableInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='harness-install-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'home with spaces'
        self.home.mkdir()
        self.env = dict(os.environ)
        for key in ('CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'HARNESS_KNOWLEDGE_DB',
                    'HARNESS_RUNTIME_PROFILE', 'HARNESS_KNOWLEDGE_PROFILE', 'PYTHONPATH'):
            self.env.pop(key, None)
        self.env['HOME'] = str(self.base / 'process-home')

    def install(self, *args, success=True):
        process = subprocess.run(
            [str(PYTHON), str(ROOT / 'scripts/install_skills.py'),
             '--home', str(self.home), *args],
            cwd=self.base, env=self.env, capture_output=True, text=True,
        )
        if success:
            self.assertEqual(process.returncode, 0, process.stderr)
            return json.loads(process.stdout)
        self.assertNotEqual(process.returncode, 0)
        return process

    def snapshot(self):
        return {str(path.relative_to(self.home)):
                ('link', os.readlink(path)) if path.is_symlink() else
                ('file', path.read_bytes(), path.stat().st_mode & 0o777)
                for path in self.home.rglob('*')
                if path.is_symlink() or path.is_file()}

    def test_all_native_adapters_and_repeat_install(self):
        result = self.install()
        self.assertEqual(result['knowledge_transfer'], 'none')
        for name in MANIFEST['skills']:
            link = self.home / '.agents/skills' / name
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), ROOT / 'skills' / name)
            wrapper = self.home / '.claude/skills' / name / 'SKILL.md'
            self.assertFalse(wrapper.is_symlink())
            content = wrapper.read_text()
            self.assertIn(str(ROOT / 'skills' / name / 'SKILL.md'), content)
            self.assertIn(str(PYTHON), content)
        for name in MANIFEST['claude_workers']:
            link = self.home / '.claude/agents' / (name + '.md')
            self.assertEqual(link.resolve(), ROOT / '.claude/agents' / (name + '.md'))
            self.assertTrue(link.is_file())
        before = self.snapshot()
        self.install()
        self.assertEqual(before, self.snapshot())
        self.assertFalse(any(self.home.rglob('*.sqlite3')))

    def test_user_instructions_and_unrelated_skills_survive(self):
        text = '# Personal instructions\n\nKeep answers concise.\n'
        profiles = [self.home / '.codex/AGENTS.md', self.home / '.claude/CLAUDE.md']
        for profile in profiles:
            profile.parent.mkdir(parents=True)
            profile.write_text(text)
        foreign = self.home / '.agents/skills/custom/SKILL.md'
        foreign.parent.mkdir(parents=True)
        foreign.write_text('user-owned skill\n')
        self.install()
        for profile in profiles:
            profile.write_text(profile.read_text() + '\nNew personal rule.\n')
        self.install()
        for profile in profiles:
            self.assertTrue(profile.read_text().startswith(text))
            self.assertTrue(profile.read_text().endswith('\nNew personal rule.\n'))
            self.assertEqual(profile.read_text().count('<!-- engineering-harness:start -->'), 1)
        self.assertEqual(foreign.read_text(), 'user-owned skill\n')

    def test_unmanaged_conflict_refuses_without_partial_installation(self):
        path = self.home / '.local/bin/harness'
        path.parent.mkdir(parents=True)
        path.write_text('my own harness command\n')
        before = self.snapshot()
        failed = self.install(success=False)
        self.assertIn('Refusing to replace', failed.stderr)
        self.assertEqual(before, self.snapshot())

    def test_edited_generated_wrapper_is_preserved(self):
        self.install()
        path = self.home / '.claude/skills/knowledge-cycle/SKILL.md'
        path.write_text(path.read_text() + '\nLocal edit.\n')
        before = self.snapshot()
        self.install(success=False)
        self.assertEqual(before, self.snapshot())

    def test_dry_run_does_not_create_files(self):
        self.assertEqual(self.install('--dry-run')['status'], 'planned')
        self.assertEqual(list(self.home.iterdir()), [])

    def test_malformed_instruction_block_has_no_partial_writes(self):
        path = self.home / '.codex/AGENTS.md'
        path.parent.mkdir(parents=True)
        path.write_text('Personal.\n<!-- engineering-harness:start -->\nMissing end.\n')
        before = self.snapshot()
        failed = self.install(success=False)
        self.assertIn('Malformed managed instruction block', failed.stderr)
        self.assertEqual(before, self.snapshot())

    def test_legacy_skill_and_launcher_links_are_migrated(self):
        name = 'fork-tab'
        legacy = self.home / '.codex/skills' / name
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(ROOT / 'skills' / name)
        claude = self.home / '.claude/skills' / name
        claude.parent.mkdir(parents=True)
        claude.symlink_to(ROOT / 'skills/fork-tab/adapters/claude')
        command = self.home / '.local/bin/fork-tab'
        command.parent.mkdir(parents=True)
        command.symlink_to(ROOT / 'skills/fork-tab/scripts/fork_tab.py')
        self.install()
        self.assertFalse(legacy.is_symlink())
        self.assertTrue((self.home / '.agents/skills/fork-tab').is_symlink())
        self.assertFalse(claude.is_symlink())
        self.assertTrue((claude / 'SKILL.md').is_file())
        self.assertFalse(command.is_symlink())
        self.assertTrue(os.access(command, os.X_OK))

    def test_agent_selection_and_sequential_installation(self):
        self.install('--agents', 'codex')
        self.assertFalse((self.home / '.claude').exists())
        self.install('--agents', 'claude')
        self.assertTrue((self.home / '.codex/AGENTS.md').is_file())
        self.assertTrue((self.home / '.claude/CLAUDE.md').is_file())
        self.install()
        before = self.snapshot()
        self.install()
        self.assertEqual(before, self.snapshot())

    def test_launchers_run_outside_repo_without_python_on_path(self):
        self.install()
        env = {**self.env, 'PATH': '/nonexistent'}
        for name in ('harness', 'fork-tab'):
            command = self.home / '.local/bin' / name
            process = subprocess.run([str(command), '--help'], cwd=self.base,
                                     env=env, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertIn('usage:', process.stdout.lower())
            self.assertIn(str(PYTHON), command.read_text())

    def test_launcher_initializes_an_empty_isolated_knowledge_core(self):
        self.install()
        database = self.home / '.local/share/engineering-harness/knowledge/knowledge.sqlite3'
        command = self.home / '.local/bin/harness'
        for _ in range(2):
            process = subprocess.run(
                [str(command), '--db', str(database), 'init'], cwd=self.base,
                env={**self.env, 'PATH': '/nonexistent'}, capture_output=True, text=True,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(result['status'], 'ready')
            self.assertEqual(Path(result['db']), database)
        # Only inspect the newly created test database, never an existing store.
        with sqlite3.connect(database) as connection:
            for table in ('tasks', 'evidence', 'entries', 'revisions', 'jobs', 'packets'):
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
