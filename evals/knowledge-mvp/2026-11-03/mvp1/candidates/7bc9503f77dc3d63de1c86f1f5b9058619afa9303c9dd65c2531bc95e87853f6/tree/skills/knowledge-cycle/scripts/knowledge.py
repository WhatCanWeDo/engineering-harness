#!/usr/bin/env python3
"""Thin portable entrypoint; all domain logic lives in the installed core."""
from pathlib import Path
import sys

repository = Path(__file__).resolve().parents[3]
if (repository / 'harness' / '__init__.py').is_file():
    sys.path.insert(0, str(repository))
try:
    from harness.cli import main
except ImportError:
    raise SystemExit('Install the engineering-harness package in this Python environment first.')
raise SystemExit(main())
