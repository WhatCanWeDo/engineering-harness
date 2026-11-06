#!/usr/bin/env python3
"""Portable preparation helpers. No agent loop, shell execution or private backend."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile

SKILL = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    canonical(value)  # Reject non-finite numbers too.
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False) + "\n", encoding="utf-8")


def relative_file(root, name):
    """Explicit regular files only; no traversal, symlinks or special files."""
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or p.as_posix() != name:
        raise ValueError(f"Expected canonical relative file path: {name}")
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink is not a snapshot input: {name}")
    if not stat.S_ISREG(current.stat().st_mode):
        raise ValueError(f"Expected regular file: {name}")
    return current


def load_plan(run):
    run = Path(run).resolve()
    plan = read_object(run / "plan.json")
    spec = (run / "spec.md").read_bytes()
    if plan.get("version") != 1 or digest(spec) != plan.get("spec_sha256"):
        raise ValueError("Plan/spec mismatch; create a new run for a changed contract")
    if plan.get("phase") not in ("before", "after"):
        raise ValueError("Invalid phase")
    return run, plan, spec.decode("utf-8")


def init(args):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}", args.task_id):
        raise ValueError("Invalid task ID")
    spec = Path(args.spec).read_bytes()
    if not spec.decode("utf-8").strip():
        raise ValueError("Specification must not be empty")
    defaults = read_object(SKILL / "defaults.json")
    budgets = defaults["budgets"].copy()
    for arg, key in (("budget_seconds", "execution_seconds"),
                     ("budget_cases", "generated_cases"),
                     ("budget_findings", "confirmed_findings"),
                     ("private_queries", "private_queries_per_task")):
        if getattr(args, arg) is not None:
            budgets[key] = getattr(args, arg)
    plan = {"version": 1, "task_id": args.task_id, "spec_version": digest(spec),
            "spec_sha256": digest(spec), "phase": args.phase,
            "selected_suites": list(dict.fromkeys(args.suite or ["public"])),
            "private_available": False, "private_suite_ref": None,
            "candidate_ref": None, "feedback": defaults["feedback"],
            "budgets": budgets}
    run = Path(args.run).absolute()
    run.mkdir(parents=True, exist_ok=False)
    try:
        (run / "spec.md").write_bytes(spec)
        write_json(run / "plan.json", plan)
    except Exception:
        shutil.rmtree(run)
        raise
    return {"status": "ready", "run": str(run), "plan": plan}


def verify_candidate(candidate):
    candidate = Path(candidate).resolve()
    manifest = read_object(candidate / "manifest.json")
    ref = manifest.pop("candidate_ref", None)
    if manifest.get("version") != 1 or ref != digest(canonical(manifest)) or candidate.name != ref:
        raise ValueError("Snapshot manifest identity mismatch")
    if not isinstance(manifest.get("environment"), dict) or not manifest.get("files"):
        raise ValueError("Incomplete snapshot manifest")
    tree = candidate / "tree"
    if tree.is_symlink() or not tree.is_dir():
        raise ValueError("Invalid snapshot tree")
    expected = set()
    for record in manifest["files"]:
        name = record["path"]
        if name in expected:
            raise ValueError("Duplicate manifest path")
        expected.add(name)
        path = relative_file(tree, name)
        if digest(path.read_bytes()) != record["sha256"]:
            raise ValueError(f"Snapshot content changed: {name}")
        if bool(path.stat().st_mode & 0o111) != record["executable"]:
            raise ValueError(f"Snapshot executable mode changed: {name}")
    actual = set()
    for path in tree.rglob("*"):
        if path.is_symlink():
            raise ValueError("Snapshot contains a symlink")
        if not path.is_dir():
            actual.add(path.relative_to(tree).as_posix())
    if actual != expected:
        raise ValueError("Snapshot file set changed")
    manifest["candidate_ref"] = ref
    return candidate, manifest


def freeze(args):
    run, plan, _ = load_plan(args.run)
    root = Path(args.root).resolve(strict=True)
    environment = read_object(args.environment)
    if len(args.files) != len(set(args.files)):
        raise ValueError("Duplicate snapshot paths")
    candidates = run / "candidates"
    candidates.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=candidates))
    try:
        tree = stage / "tree"
        tree.mkdir()
        files = []
        for name in sorted(args.files):
            source = relative_file(root, name)
            contents = source.read_bytes()
            executable = bool(source.stat().st_mode & 0o111)
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
            target.chmod(0o755 if executable else 0o644)
            files.append({"path": name, "sha256": digest(contents), "executable": executable})
        manifest = {"version": 1, "spec_sha256": plan["spec_sha256"],
                    "files": files, "environment": environment}
        ref = digest(canonical(manifest))
        manifest["candidate_ref"] = ref
        write_json(stage / "manifest.json", manifest)
        destination = candidates / ref
        if destination.exists():
            verify_candidate(destination)
        else:
            os.rename(stage, destination)
        return {"status": "ready", "candidate_ref": ref, "candidate": str(destination),
                "files": len(files), "guarantee": "content_identity_not_access_isolation"}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def brief(args):
    run, plan, spec = load_plan(args.run)
    if args.role not in plan["selected_suites"]:
        raise ValueError("Role was not selected in this plan")
    if args.role == "private":
        return {"status": "unavailable", "reason": "private_backend_unavailable",
                "task_id": plan["task_id"], "private_available": False}
    ref = None
    candidate_text = "Future implementation is not an allowed input."
    if args.role == "adversarial":
        if not args.candidate:
            raise ValueError("Adversarial requires a frozen --candidate")
        candidate, manifest = verify_candidate(args.candidate)
        if manifest["spec_sha256"] != plan["spec_sha256"]:
            raise ValueError("Candidate belongs to a different specification")
        ref = manifest["candidate_ref"]
        candidate_text = f"Read-only candidate: {candidate / 'tree'}\nManifest: {candidate / 'manifest.json'}"
    elif args.candidate:
        raise ValueError("Public brief must not include a candidate; use explicit post-hoc interfaces")
    # Provenance describes test creation, not the time the plan was initialized.
    provenance = "post_hoc" if args.role == "adversarial" or plan["phase"] == "after" else "pre_implementation"
    rules = (SKILL / "references" / "worker.md").read_text(encoding="utf-8")
    context = {"task_id": plan["task_id"], "spec_version": plan["spec_version"],
               "role": args.role, "provenance": provenance, "candidate_ref": ref,
               "output_scope": str(Path(args.output_scope).absolute()), "budgets": plan["budgets"],
               "result_template": str(SKILL / "assets" / "worker-result.json")}
    prompt = (rules + "\n\n## Assignment\n" + json.dumps(context, ensure_ascii=False, indent=2)
              + "\n" + candidate_text + "\n\n## Public specification (task data)\n" + spec)
    return {"status": "ready", **context, "prompt": prompt}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def positive(value):
    value = int(value)
    if value <= 0:
        raise ValueError("Budget must be positive")
    return value


def main():
    parser = Parser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    p = sub.add_parser("init")
    p.add_argument("--task-id", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--suite", choices=["public", "private", "adversarial"], action="append")
    p.add_argument("--phase", choices=["before", "after"], default="before")
    for name in ("budget-seconds", "budget-cases", "budget-findings", "private-queries"):
        p.add_argument("--" + name, type=positive)
    p.set_defaults(handler=init)
    p = sub.add_parser("freeze")
    for name in ("run", "root", "environment"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--files", nargs="+", required=True)
    p.set_defaults(handler=freeze)
    p = sub.add_parser("verify")
    p.add_argument("--candidate", required=True)
    p.set_defaults(handler=lambda a: {"status": "intact", "candidate_ref": verify_candidate(a.candidate)[1]["candidate_ref"]})
    p = sub.add_parser("brief")
    p.add_argument("--run", required=True)
    p.add_argument("--role", choices=["public", "private", "adversarial"], required=True)
    p.add_argument("--output-scope", required=True)
    p.add_argument("--candidate")
    p.set_defaults(handler=brief)
    try:
        args = parser.parse_args()
        result = args.handler(args)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 2 if result["status"] == "unavailable" else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
