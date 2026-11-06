#!/usr/bin/env python3
"""Describe a ready HTML artifact or explicitly request opening it in a browser."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import sys
from urllib.parse import quote
import uuid
import webbrowser


def default_output():
    """A unique persistent path; no mutable 'latest' pointer across tasks."""
    name = datetime.now().strftime('%Y-%m-%d-%H%M%S-') + uuid.uuid4().hex[:8]
    return Path.home() / '.local/share/engineering-harness/explainers' / name / 'explanation.html'


def artifact_path(path):
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in ('.html', '.htm'):
        raise ValueError('Expected an existing HTML file')
    if any(ord(c) < 32 or ord(c) == 127 for c in str(path)):
        raise ValueError('Artifact path must not contain control characters')
    return path


def describe(path):
    path = artifact_path(path)
    argv = [sys.executable, str(Path(__file__).resolve()), str(path), '--open']
    preview_argv = [sys.executable, str(Path(__file__).with_name('preview.py').resolve()), str(path)]
    if os.name == 'nt':
        command = '& ' + ' '.join("'" + value.replace("'", "''") + "'" for value in argv)
        shell = 'powershell'
    else:
        command, shell = shlex.join(argv), 'posix'
    # Angle brackets preserve spaces; reserved Markdown/URL characters are encoded.
    target = quote(path.as_posix(), safe='/: ')
    return {
        'file_path': str(path),
        'file_link': f'[Открыть объяснение и quiz](<{target}>)',
        'open_argv': argv,
        'preview_argv': preview_argv,
        'open_command': command,
        'command_shell': shell,
        'launch_requested': False,
        'remote_shell_detected': bool(os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_TTY')),
    }


def request_browser(path):
    if os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_TTY'):
        raise ValueError('Remote SSH session: transfer the HTML to the reader computer and open it there; a remote file path is not a local browser link')
    path = artifact_path(path)
    if not webbrowser.open(path.as_uri(), new=2):
        raise ValueError('No browser accepted the open request; the HTML remains available at its original path')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    parser.add_argument('--open', action='store_true', help='Explicitly request launch in the default browser on this computer')
    args = parser.parse_args()
    try:
        result = describe(args.html)
        if args.open:
            request_browser(args.html)
            result['launch_requested'] = True
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, webbrowser.Error) as exc:
        parser.exit(2, f'Delivery error: {exc}\n')


if __name__ == '__main__':
    main()
