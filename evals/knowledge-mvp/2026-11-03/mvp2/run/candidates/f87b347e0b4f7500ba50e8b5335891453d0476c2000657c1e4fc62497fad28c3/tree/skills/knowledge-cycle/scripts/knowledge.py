#!/usr/bin/env python3
"""Thin portable entrypoint; all domain logic lives in the installed core."""
from pathlib import Path
import json
import os
import sys

repository = Path(__file__).resolve().parents[3]
if (repository / 'harness' / '__init__.py').is_file():
    local_python = repository / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if local_python.is_file() and Path(sys.prefix).resolve() != (repository / '.venv').resolve():
        os.execv(str(local_python), [str(local_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    profile = repository / '.harness' / 'knowledge.local.json'
    if profile.exists():
        settings = json.loads(profile.read_text(encoding='utf-8'))
        for key, variable in [('semantic_model', 'HARNESS_SEMANTIC_MODEL'), ('mode', 'HARNESS_RETRIEVAL_MODE')]:
            if key in settings:
                if not isinstance(settings[key], str):
                    raise SystemExit('Invalid local knowledge profile: ' + key)
                os.environ.setdefault(variable, settings[key])
    sys.path.insert(0, str(repository))
try:
    from harness.cli import main
except ImportError:
    raise SystemExit('Install the engineering-harness package in this Python environment first.')
raise SystemExit(main())
