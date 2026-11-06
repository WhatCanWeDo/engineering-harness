#!/usr/bin/env python3
"""Run independently authored suites and save a source-bound, repeatable receipt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["mvp1", "mvp2", "all"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    patterns = ["test_knowledge_mvp.py", "test_knowledge_workflow.py", "test_knowledge_adversarial.py"]
    if args.stage in ("mvp2", "all"):
        patterns += ["test_knowledge_semantic.py", "test_knowledge_semantic_adversarial.py"]
    if args.stage == "all":
        patterns = ["test_*.py"]
    files = sorted(set(ROOT.glob("harness/*.py")) | set(ROOT.glob("tests/test_*.py")) |
                   set(ROOT.glob("skills/knowledge-cycle/**/*.*")) | set(ROOT.glob("scripts/*.py")) | {ROOT / "uv.lock", ROOT / "pyproject.toml"})
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in files if p.is_file() and "__pycache__" not in p.parts}
    results = []
    for pattern in patterns:
        if not list((ROOT / "tests").glob(pattern)):
            results.append({"suite": pattern, "status": "not_run", "reason": "missing_suite"})
            continue
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"]
        started = time.monotonic()
        try:
            process = subprocess.run(command, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                                     capture_output=True, text=True, timeout=180)
            status = "pass" if process.returncode == 0 else "fail"
            log = process.stdout + process.stderr
            code = process.returncode
        except subprocess.TimeoutExpired:
            status, log, code = "error", "Suite exceeded 180 seconds", None
        (args.output / (pattern + ".log")).write_text(log, encoding="utf-8")
        results.append({"suite": pattern, "status": status, "exit_code": code,
                        "elapsed_seconds": round(time.monotonic() - started, 3), "command": command})
    stable = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest for p, digest in hashes.items())
    passed = stable and all(r["status"] == "pass" for r in results)
    receipt = {"stage": args.stage, "status": "pass" if passed else "fail", "source_stable": stable,
               "source_sha256": hashes, "suites": results, "private": "unavailable",
               "python": sys.version, "platform": platform.platform(),
               "limitations": "Public and adaptive adversarial regressions; not a fresh private holdout."}
    (args.output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    (args.output / "summary.txt").write_text(
        f"Knowledge {args.stage}: gate {receipt['status']}; source_stable={stable}; private=unavailable.\n" +
        "\n".join(f"{r['suite']}: {r['status']}" for r in results) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "receipt": str((args.output / "receipt.json").absolute())}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
