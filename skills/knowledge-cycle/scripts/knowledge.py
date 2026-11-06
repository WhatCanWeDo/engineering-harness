#!/usr/bin/env python3
"""Thin portable entrypoint; all domain logic lives in the installed core."""
from pathlib import Path
import os
import sys

repository = Path(__file__).resolve().parents[3]
if (repository / 'harness' / '__init__.py').is_file():
    local_python = repository / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if local_python.is_file() and Path(sys.prefix).resolve() != (repository / '.venv').resolve():
        os.execv(str(local_python), [str(local_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    # Runtime model bundle may be shared; project DB/mode are resolved from caller cwd in Core.
    profile = repository / '.harness' / 'knowledge.local.json'
    if profile.exists():
        os.environ.setdefault('HARNESS_RUNTIME_PROFILE', str(profile))
    sys.path.insert(0, str(repository))
try:
    from harness.cli import main
except ImportError:
    raise SystemExit('Install the engineering-harness package in this Python environment first.')
raise SystemExit(main())
