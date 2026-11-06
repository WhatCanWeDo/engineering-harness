#!/usr/bin/env python3
"""Explicit fresh-Git-clone installation check in an isolated target home."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='New directory; never overwrites')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--model-dir', type=Path, help='Reuse an existing compatible model bundle')
    parser.add_argument('--lexical-only', action='store_true')
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    clone, home = output / 'checkout with spaces', output / 'empty home'
    home.mkdir()
    env = dict(os.environ)
    for key in ('VIRTUAL_ENV', 'HARNESS_KNOWLEDGE_DB', 'HARNESS_RUNTIME_PROFILE', 'UV_PROJECT_ENVIRONMENT'):
        env.pop(key, None)
    checks = []

    def run(label, command, cwd):
        result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (output / (label + '.log')).write_text(result.stdout + '\n' + result.stderr)
        if result.returncode: raise RuntimeError(f'{label} failed; inspect {output / (label + ".log")}')
        checks.append(label)
        print(label + ': passed', flush=True)
        return result.stdout

    try:
        run('clone', ['git', 'clone', '--quiet', '--no-local', ROOT, clone], output)
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=clone, text=True).strip()
        setup = ['sh', 'scripts/setup.sh', '--home', home]
        if args.offline: setup.append('--offline')
        if args.lexical_only: setup.append('--lexical-only')
        else: setup += ['--model-dir', (args.model_dir.expanduser().resolve() if args.model_dir else output / 'model')]
        run('setup', setup, clone)
        run('setup-repeat', setup, clone)
        doctor = json.loads(run('doctor', [clone / '.venv/bin/python', 'scripts/doctor.py', '--home', home], clone))
        project = output / 'new project'; project.mkdir()
        run('project-init', [home / '.local/bin/harness', 'project', 'init', '--root', project,
                             '--id', 'portable-check', '--mode', 'lexical' if args.lexical_only else 'semantic'], output)
        counts = {}
        for name, db in [('global', home / '.local/share/engineering-harness/knowledge/knowledge.sqlite3'),
                         ('project', project / '.harness/knowledge/knowledge.sqlite3')]:
            with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
                counts[name] = {table: conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                                for table in ('tasks', 'entries', 'evidence', 'revisions', 'jobs', 'packets')}
                if any(counts[name].values()): raise RuntimeError(f'{name} database is not empty')
        result = {'status': 'pass', 'commit': commit, 'checks': checks, 'doctor': doctor,
                  'empty_databases': counts, 'knowledge_transferred': False,
                  'physical_second_device': False, 'cache_reuse_possible': True}
        (output / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'status': 'pass', 'report': str(output / 'report.json')}))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'Portability check failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
