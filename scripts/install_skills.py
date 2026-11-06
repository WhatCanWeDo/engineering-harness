#!/usr/bin/env python3
"""Install all native adapters from a checkout without clobbering user files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import tempfile

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- engineering-harness:start -->'
END = '<!-- engineering-harness:end -->'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.harness-install-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, 0o755 if executable else 0o600)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def description(skill):
    content = (ROOT / 'skills' / skill / 'SKILL.md').read_text()
    match = re.search(r'^description: (.+)$', content, re.M)
    if not match: raise ValueError(f'Missing description: {skill}')
    return match.group(1)


def install(home, agents='both', dry_run=False):
    home = home.expanduser().resolve()
    python = ROOT / '.venv/bin/python'
    if not python.is_file(): raise ValueError('Run sh scripts/setup.sh first: managed Python is missing')
    manifest = json.loads((ROOT / 'scripts/skills-manifest.json').read_text())
    receipt_path = home / '.local/share/engineering-harness/install.json'
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    owned = previous.get('files', {})
    operations = []
    removed = set()
    recorded = dict(owned)
    real_home = home == Path.home().resolve()
    codex_home = Path(os.environ.get('CODEX_HOME', str(home / '.codex'))).expanduser() if real_home else home / '.codex'
    claude_home = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(home / '.claude'))).expanduser() if real_home else home / '.claude'
    codex_skills = (codex_home / 'skills') if real_home and os.environ.get('CODEX_HOME') else home / '.agents/skills'

    def exists(path):
        return path.exists() or path.is_symlink()

    def matches_owned(path):
        entry = owned.get(str(path), {})
        if path.is_symlink(): return entry.get('target') == os.readlink(path)
        return path.is_file() and entry.get('sha256') == digest(path.read_bytes())

    def remove_link(path, allowed_targets):
        if path.is_symlink() and (path.resolve() in allowed_targets or matches_owned(path)):
            operations.append(('remove', path, None)); removed.add(path)
            recorded.pop(str(path), None)
            return True
        return False

    def add_link(dest, source):
        if not source.exists(): raise ValueError(f'Missing checkout resource: {source}')
        if exists(dest) and not (dest.is_symlink() and dest.resolve() == source.resolve()) and not matches_owned(dest):
            raise ValueError(f'Refusing to replace unmanaged path: {dest}')
        operations.append(('link', dest, source))
        recorded[str(dest)] = {'target': str(source)}

    def add_file(dest, content, executable=False, legacy_target=None):
        data = content.encode()
        if legacy_target and dest.is_symlink() and dest.resolve() == legacy_target:
            remove_link(dest, {legacy_target})
        if not any(parent in removed for parent in (dest, *dest.parents)) and exists(dest):
            if dest.is_symlink() or not dest.is_file() or (dest.read_bytes() != data and not matches_owned(dest)):
                raise ValueError(f'Refusing to replace unmanaged/edited file: {dest}')
        operations.append(('executable' if executable else 'file', dest, data))
        recorded[str(dest)] = {'sha256': digest(data)}

    def add_profile(path):
        if path.is_symlink(): raise ValueError(f'Refusing to rewrite instruction symlink: {path}')
        text = path.read_text() if path.exists() else ''
        block = (f'{START}\nRead the installed [Engineering Harness profile](<{ROOT / "docs/installation-profile.md"}>).\n'
                 f'Canonical checkout: `{ROOT}`. Managed Python: `{python}`.\n'
                 f'Use this Python for all harness skill scripts, even when examples say python3.\n{END}')
        if START in text or END in text:
            if text.count(START) != 1 or text.count(END) != 1 or text.index(END) < text.index(START):
                raise ValueError(f'Malformed managed instruction block: {path}')
            text = text[:text.index(START)] + block + text[text.index(END) + len(END):]
        else:
            text = text.rstrip() + ('\n\n' if text.strip() else '') + block + '\n'
        operations.append(('file', path, text.encode()))
        # Only the marked block is managed; unrelated user instructions are preserved.

    for name in manifest['skills']:
        canonical = ROOT / 'skills' / name
        desc = description(name)
        if agents in ('codex', 'both'):
            legacy = home / '.codex/skills' / name
            if legacy != codex_skills / name:
                remove_link(legacy, {canonical})
            add_link(codex_skills / name, canonical)
        if agents in ('claude', 'both'):
            folder = claude_home / 'skills' / name
            if folder.is_symlink():
                allowed = {canonical, ROOT / 'skills/fork-tab/adapters/claude', ROOT / '.claude/skills' / name}
                if not remove_link(folder, allowed): raise ValueError(f'Unmanaged skill symlink: {folder}')
            wrapper = (f'---\nname: {name}\ndescription: {desc}\n' +
                       ('disable-model-invocation: true\n' if name in ('test-on-request', 'harness-ab') else '') +
                       f'---\n\nRead [{name}](<{canonical / "SKILL.md"}>) and follow the user request: $ARGUMENTS.\n'
                       f'Resolve resources against `{canonical}`; run Python scripts with `{python}`.\n')
            if name == 'fork-tab':
                invocation = shlex.join([str(python), str(canonical / 'scripts/fork_tab.py'), '--agent', 'claude'])
                wrapper += f"\nCurrent session ID (native skill substitution): `${{CLAUDE_SESSION_ID}}`.\nRun from the current project:\n```sh\n{invocation} --session '${{CLAUDE_SESSION_ID}}'\n```\n"
            if name in ('knowledge-cycle', 'spec-init'):
                wrapper += '\nUse a fresh non-fork harness-knowledge-worker for each Scout/Curator brief.\n'
            if name == 'test-on-request':
                wrapper += '\nUse a separate non-fork harness-test-generator for generation.\n'
            add_file(folder / 'SKILL.md', wrapper)
    if agents in ('claude', 'both'):
        for name in manifest['claude_workers']:
            add_link(claude_home / 'agents' / (name + '.md'), ROOT / '.claude/agents' / (name + '.md'))
        add_profile(claude_home / 'CLAUDE.md')
    if agents in ('codex', 'both'):
        add_profile(codex_home / 'AGENTS.md')
    for name, script in {
        'harness': ROOT / 'skills/knowledge-cycle/scripts/knowledge.py',
        'fork-tab': ROOT / 'skills/fork-tab/scripts/fork_tab.py',
    }.items():
        command = '#!/bin/sh\nexec ' + shlex.join([str(python), str(script)]) + ' "$@"\n'
        add_file(home / '.local/bin' / name, command, True, legacy_target=script)
    if not dry_run:
        for kind, dest, value in operations:
            if kind == 'remove': dest.unlink()
            elif kind == 'link':
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.is_symlink() and os.readlink(dest) == str(value): continue
                if exists(dest): dest.unlink()
                dest.symlink_to(value, target_is_directory=value.is_dir())
            else:
                atomic_write(dest, value, kind == 'executable')
        atomic_write(receipt_path, (json.dumps({'version': 1, 'root': str(ROOT), 'agents': agents,
                                               'skills': manifest['skills'], 'files': recorded}, indent=2) + '\n').encode())
    return {'status': 'planned' if dry_run else 'installed', 'skills': manifest['skills'],
            'agents': agents, 'home': str(home), 'receipt': str(receipt_path),
            'instruction_blocks': True, 'knowledge_transfer': 'none'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--agents', choices=('codex', 'claude', 'both'), default='both')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.home, args.agents, args.dry_run), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Install failed: {exc}\n')


if __name__ == '__main__':
    main()
