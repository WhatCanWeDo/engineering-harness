#!/usr/bin/env python3
"""Resolve or explicitly persist understanding preferences; Python stdlib only."""
import argparse
import json
import os
from pathlib import Path
import tempfile

DEFAULTS = Path(__file__).resolve().parents[1] / 'defaults.json'
CHOICES = {'frequency': ('task_end', 'milestone', 'on_request'),
           'depth': ('brief', 'medium', 'deep')}


def resolve(path, overrides):
    result = json.loads(DEFAULTS.read_text(encoding='utf-8'))
    personal = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(personal, dict) or set(personal) - set(CHOICES):
        raise ValueError('Personal preferences must contain only frequency and/or depth')
    for key, value in {**personal, **overrides}.items():
        if value not in CHOICES[key]:
            raise ValueError(f'Invalid {key}: {value!r}')
    # Validate stored values even when a task override would hide them.
    for key, value in personal.items():
        if value not in CHOICES[key]:
            raise ValueError(f'Invalid stored {key}: {value!r}')
    result.update(personal)
    result.update(overrides)
    return result, personal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', type=Path, default=Path.home() / '.config/engineering-harness/understand-changes.json')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('show', 'set'):
        p = sub.add_parser(command)
        for key, choices in CHOICES.items():
            p.add_argument('--' + key, choices=choices)
    args = parser.parse_args()
    overrides = {key: getattr(args, key) for key in CHOICES if getattr(args, key) is not None}
    try:
        result, personal = resolve(args.path, overrides)
        if args.command == 'set':
            if not overrides:
                raise ValueError('set requires --frequency or --depth')
            personal.update(overrides)
            args.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.path.parent, delete=False) as f:
                    temp_path = Path(f.name)
                    json.dump(personal, f, ensure_ascii=False, indent=2)
                    f.write('\n')
                os.replace(temp_path, args.path)
            finally:
                if temp_path and temp_path.exists():
                    temp_path.unlink()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Preferences error: {exc}\n')


if __name__ == '__main__':
    main()
