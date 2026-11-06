#!/usr/bin/env python3
"""Repeatable project setup. Invoked by setup.sh using a managed Python."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'faf4aa4225822f3bc6376869cb1164e8e3feedd0'
DEFAULT_MODEL = Path.home() / '.local/share/engineering-harness/models' / ('minilm-' + REVISION[:12] + '-fe0.9.1')


def run(argv, env, capture=False):
    print('+ ' + ' '.join(str(a) for a in argv), file=sys.stderr, flush=True)
    process = subprocess.run([str(a) for a in argv], cwd=ROOT, env=env, text=True,
                             stdout=subprocess.PIPE if capture else None, check=True)
    return json.loads(process.stdout) if capture else None


def atomic_json(path, value):
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temp.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def install(args):
    env = dict(os.environ)
    env.pop('VIRTUAL_ENV', None)
    env['UV_PROJECT_ENVIRONMENT'] = str(ROOT / '.venv')
    env['HF_HUB_DISABLE_TELEMETRY'] = '1'
    env['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
    profile_path = ROOT / '.harness/knowledge.local.json'
    previous = profile_path.read_bytes() if profile_path.exists() else None
    profile = json.loads(previous) if previous else {}
    if not isinstance(profile, dict):
        raise ValueError('Local profile must be a JSON object; no changes made')
    chosen = args.model_dir
    if not chosen and profile.get('semantic_model') and Path(profile['semantic_model']).is_dir():
        chosen = Path(profile['semantic_model'])
    model_default = args.home / '.local/share/engineering-harness/models' / DEFAULT_MODEL.name
    model = (chosen or model_default).expanduser().absolute()
    if not args.lexical_only:
        parent = model.parent
        while not parent.exists(): parent = parent.parent
        if not model.exists() and shutil.disk_usage(parent).free < 2 * 1024**3:
            raise ValueError('Keep at least 2 GiB free for model download/staging and caches; 3 GiB recommended.')
        if args.offline and not (model / 'manifest.json').is_file():
            raise ValueError('Offline semantic setup needs an existing bundle: use --model-dir PATH or run online once.')
    command = [args.uv, 'sync', '--locked', '--python', sys.executable]
    if not args.lexical_only: command += ['--extra', 'semantic']
    if args.offline: command += ['--offline']
    run(command, env)
    python = ROOT / '.venv/bin/python'
    stage = None
    try:
        if not args.lexical_only and not model.exists():
            model.parent.mkdir(parents=True, exist_ok=True)
            stage = model.with_name('.' + model.name + '.setup-' + uuid.uuid4().hex)
            # Publish only after both model-setup and the separate resource probe succeed.
            run([python, '-m', 'harness', 'model-setup', '--output', stage, '--revision', REVISION], env, capture=True)
        probe = [python, ROOT / 'scripts/knowledge_resources.py']
        if not args.lexical_only: probe += ['--model', stage or model]
        offline_env = {**env, 'HF_HUB_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1'}
        readiness = run(probe, offline_env, capture=True)
        if stage is not None:
            if model.exists(): raise ValueError('Model destination appeared concurrently; refusing to overwrite it')
            stage.rename(model); stage = None
        default_db = args.home / '.local/share/engineering-harness/knowledge/knowledge.sqlite3'
        override_db = os.environ.get('HARNESS_KNOWLEDGE_DB') if args.home == Path.home().resolve() else None
        db = Path(override_db or default_db).expanduser()
        initialized = run([python, '-m', 'harness', '--db', db, 'init'], offline_env, capture=True)
        # Preserve unrelated settings and any concurrently edited profile.
        if (profile_path.read_bytes() if profile_path.exists() else None) != previous:
            raise ValueError('Profile changed during setup; rerun to reconcile it')
        profile['mode'] = 'lexical' if args.lexical_only else (args.mode or profile.get('mode', 'semantic'))
        if profile['mode'] not in {'lexical', 'semantic', 'hybrid'}: raise ValueError('Invalid existing mode; pass --mode explicitly')
        if args.lexical_only: profile.pop('semantic_model', None)
        else: profile['semantic_model'] = str(model)
        atomic_json(profile_path, profile)
        adapters = None
        if not args.skip_skills:
            adapters = run([python, ROOT / 'scripts/install_skills.py', '--home', args.home, '--agents', args.agents], env, capture=True)
        receipt = {'status': 'ready', 'at': datetime.now(timezone.utc).isoformat(),
                   'mode': profile['mode'], 'model_dir': str(model) if not args.lexical_only else None,
                   'profile': str(profile_path), 'database': initialized['db'], 'resources': readiness,
                   'offline': args.offline, 'adapters': adapters, 'knowledge_transfer': 'none',
                   'suite_execution': 'not_requested_not_run'}
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
        path = ROOT / '.harness/setup' / (stamp + '.json')
        atomic_json(path, receipt)
        atomic_json(ROOT / '.harness/setup/latest.json', receipt)
        print(json.dumps({'status': 'ready', 'mode': profile['mode'], 'receipt': str(path), 'profile': str(profile_path)}, ensure_ascii=False))
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)  # Only the unique directory created by this invocation.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uv', required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--lexical-only', action='store_true')
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--mode', choices=['lexical', 'semantic', 'hybrid'])
    parser.add_argument('--home', type=Path, default=Path.home(), help='Target user home; useful for isolated installation checks')
    parser.add_argument('--agents', choices=['codex', 'claude', 'both'], default='both')
    parser.add_argument('--skip-skills', action='store_true', help='Install only Knowledge runtime')
    args = parser.parse_args()
    args.home = args.home.expanduser().resolve()
    state = ROOT / '.harness/setup'
    state.mkdir(parents=True, exist_ok=True)
    try:
        with (state / 'setup.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            install(args)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'status': 'setup_failed', 'message': str(exc),
                          'recovery': 'Inspect the failed step, then rerun. Existing model/profile are not silently replaced; use a new --model-dir for a damaged or incompatible bundle.'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
