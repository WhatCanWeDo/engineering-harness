#!/usr/bin/env python3
"""Read-only installation check; never reads knowledge contents or launches agents."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home())
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    errors, warnings = [], []
    manifest = json.loads((ROOT / 'scripts/skills-manifest.json').read_text())
    receipt = home / '.local/share/engineering-harness/install.json'
    try:
        installed = json.loads(receipt.read_text())
        if installed.get('root') != str(ROOT): errors.append('Installer receipt points to another checkout')
        for name, spec in installed['files'].items():
            path = Path(name)
            if not path.exists(): errors.append(f'Missing installed resource: {path}'); continue
            if 'target' in spec:
                if not path.is_symlink() or path.resolve() != Path(spec['target']).resolve():
                    errors.append(f'Changed installed symlink: {path}')
            elif hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
                errors.append(f'Changed managed file: {path}')
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f'Install receipt: {exc}')
    python = ROOT / '.venv/bin/python'
    try:
        check = subprocess.run([str(python), '-c', 'import harness, sqlite3, sys; c=sqlite3.connect(":memory:"); c.execute("create virtual table f using fts5(t)"); print(sys.version.split()[0])'],
                               cwd=ROOT, text=True, capture_output=True, timeout=30)
        if check.returncode: errors.append('Python/Core/FTS5 check failed: ' + check.stderr.strip())
        version = check.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        version = None; errors.append(f'Managed Python: {exc}')
    model = None
    try:
        profile = json.loads((ROOT / '.harness/knowledge.local.json').read_text())
        model = profile.get('semantic_model')
        if profile.get('mode') != 'lexical' and not (model and (Path(model) / 'manifest.json').is_file()):
            errors.append('Semantic model bundle missing; rerun setup')
    except (OSError, ValueError) as exc:
        errors.append(f'Runtime profile: {exc}')
    agents = {name: shutil.which(name) for name in ('codex', 'claude')}
    for name, binary in agents.items():
        if not binary: warnings.append(f'{name} CLI not installed/in PATH; install and sign in separately')
    if platform.system() != 'Darwin' or not Path('/Applications/Ghostty.app').exists():
        warnings.append('fork-tab requires macOS and Ghostty with AppleScript; other skills remain usable')
    result = {'status': 'error' if errors else 'ready', 'platform': platform.platform(),
              'python': version, 'skills': manifest['skills'], 'agents': agents,
              'semantic_model': model, 'errors': errors, 'warnings': warnings,
              'knowledge_contents_read': False, 'agent_sessions_started': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
