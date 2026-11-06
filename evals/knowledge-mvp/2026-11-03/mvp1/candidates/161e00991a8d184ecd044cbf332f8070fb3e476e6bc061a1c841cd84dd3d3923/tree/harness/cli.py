"""JSON CLI over the same Core API used by native adapters."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from .knowledge import KnowledgeError, KnowledgeStore, fail


def load(path):
    path = Path(path)
    if path.stat().st_size > 4 * 1024 * 1024:
        fail("validation", "JSON input exceeds 4 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


class Parser(argparse.ArgumentParser):
    def error(self, message):
        fail("arguments", message)


def parser():
    root = Parser(description="Portable engineering harness; local cooperative knowledge profile")
    root.add_argument("--db", type=Path, default=Path(os.environ.get("HARNESS_KNOWLEDGE_DB", str(Path.home() / ".local/share/engineering-harness/knowledge/knowledge.sqlite3"))))
    commands = root.add_subparsers(dest="command", required=True, parser_class=Parser)
    commands.add_parser("init")
    task = commands.add_parser("task").add_subparsers(dest="action", required=True, parser_class=Parser)
    p = task.add_parser("begin"); p.add_argument("--input", required=True)
    p = task.add_parser("finish"); p.add_argument("--task", required=True); p.add_argument("--input", required=True)
    p = task.add_parser("show"); p.add_argument("--task", required=True)
    evidence = commands.add_parser("evidence").add_subparsers(dest="action", required=True, parser_class=Parser)
    p = evidence.add_parser("add"); p.add_argument("--task", required=True); p.add_argument("--path", required=True); p.add_argument("--label", default="")
    p = evidence.add_parser("read"); p.add_argument("--task", required=True); p.add_argument("--id", required=True); p.add_argument("--offset", type=int, default=0); p.add_argument("--limit", type=int, default=4000)
    knowledge = commands.add_parser("knowledge").add_subparsers(dest="action", required=True, parser_class=Parser)
    p = knowledge.add_parser("propose"); p.add_argument("--task", required=True); p.add_argument("--batch", required=True); p.add_argument("--input", required=True)
    p = knowledge.add_parser("reconcile"); p.add_argument("--limit", type=int, default=100)
    p = knowledge.add_parser("review"); p.add_argument("--task", required=True); p.add_argument("--entry", required=True); p.add_argument("--expected-revision", type=int, required=True); p.add_argument("--decision", required=True); p.add_argument("--claim"); p.add_argument("--kind")
    p = knowledge.add_parser("promote"); p.add_argument("--task", required=True); p.add_argument("--entry", required=True); p.add_argument("--expected-revision", type=int, required=True); p.add_argument("--title", required=True); p.add_argument("--claim", required=True)
    p = knowledge.add_parser("search"); p.add_argument("--task", required=True); p.add_argument("--query", required=True); p.add_argument("--role", default="developer"); p.add_argument("--include-candidates", action="store_true"); p.add_argument("--limit", type=int, default=30)
    p = knowledge.add_parser("export"); p.add_argument("--project", required=True)
    p = knowledge.add_parser("pending"); p.add_argument("--project", required=True)
    context = commands.add_parser("context").add_subparsers(dest="action", required=True, parser_class=Parser)
    for name in ("prepare", "scout"):
        p = context.add_parser(name); p.add_argument("--task", required=True); p.add_argument("--role", default="developer"); p.add_argument("--budget", type=int, default=1200)
        if name == "prepare":
            p.add_argument("--query"); p.add_argument("--required", action="append", default=[]); p.add_argument("--selection", help="Scout JSON with selected_refs")
    p = context.add_parser("expand"); p.add_argument("--packet", required=True); p.add_argument("--entry", required=True)
    p = context.add_parser("curator"); p.add_argument("--task", required=True)
    workflow = commands.add_parser("workflow").add_subparsers(dest="action", required=True, parser_class=Parser)
    for name in ("start", "context", "finish", "ingest"):
        p = workflow.add_parser(name); p.add_argument("--input", required=True)
        if name != "start": p.add_argument("--task", required=True)
        if name != "ingest": p.add_argument("--output", required=True)
        if name == "ingest": p.add_argument("--batch", required=True)
        if name == "context":
            p.add_argument("--role", default="developer"); p.add_argument("--budget", type=int, default=1200)
    return root


def dispatch(store, args):
    if args.command == "workflow":
        from . import workflow
        data = load(args.input)
        if args.action == "start": return workflow.start(store, data, args.output)
        if args.action == "context": return workflow.context(store, args.task, args.role, data, args.output, args.budget)
        if args.action == "finish": return workflow.finish(store, args.task, data, args.output)
        return workflow.ingest(store, args.task, data, args.batch)
    if args.command == "init":
        return {"status": "ready", "db": str(store.path), "schema_version": 1, "private_backend": "unavailable", "trust_profile": "local_cooperative"}
    if args.command == "task":
        if args.action == "begin":
            value = load(args.input)
            if not isinstance(value, dict):
                fail("validation", "Task input must be an object")
            return store.begin_task(**value)
        if args.action == "finish":
            return store.finish_task(args.task, load(args.input))
        return store.get_task(args.task)
    if args.command == "evidence":
        if args.action == "read":
            return store.read_evidence(args.task, args.id, args.offset, args.limit)
        return store.add_evidence(args.task, args.path, args.label)
    if args.command == "knowledge":
        if args.action == "propose":
            return store.propose(args.task, load(args.input), args.batch)
        if args.action == "reconcile":
            return store.reconcile(args.limit)
        if args.action == "review":
            return store.review(args.task, args.entry, args.expected_revision, args.decision, args.claim, args.kind)
        if args.action == "promote":
            return store.promote(args.task, args.entry, args.expected_revision, args.title, args.claim)
        if args.action == "search":
            return store.search(args.task, args.query, args.role, args.limit, args.include_candidates)
        if args.action == "export":
            return store.export_project(args.project)
        if args.action == "pending":
            tasks = [store.get_task(row[0]) for row in store.db.execute("SELECT task_id FROM tasks WHERE curation_status IN ('queued','curation_pending','error')")]
            return {"tasks": [t for t in tasks if t["project_id"] == args.project]}
    if args.command == "context":
        if args.action == "prepare":
            selection = None
            if args.selection:
                data = load(args.selection)
                if not isinstance(data, dict) or "selected_refs" not in data:
                    fail("validation", "Scout output must contain selected_refs")
                selection = data["selected_refs"]
            return store.prepare_context(args.task, args.query, args.role, args.budget, args.required, selection)
        if args.action == "scout":
            return store.scout_brief(args.task, args.role, args.budget)
        if args.action == "curator":
            return store.curator_brief(args.task)
        return store.expand(args.packet, args.entry)
    fail("arguments", "Unknown command")


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        if args.command != "init" and not (args.command == "workflow" and args.action == "start") and not args.db.expanduser().exists():
            fail("not_initialized", "Run harness --db PATH init first")
        with KnowledgeStore(args.db) as store:
            result = dispatch(store, args)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except KnowledgeError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        print(json.dumps({"status": "error", "code": "input_or_storage_error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
