#!/usr/bin/env python3
"""Thin entrypoint; installed package or canonical repository, no extra dependencies."""
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[3]
if (root / 'harness').is_dir(): sys.path.insert(0, str(root))
from harness.cli import main
raise SystemExit(main(['ab', *sys.argv[1:]]))
