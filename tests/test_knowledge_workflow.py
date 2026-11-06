"""Public, pre-implementation CLI checks for deterministic lifecycle workflows.

All state/evidence/output lives in tempfile. Tests inspect CLI results and files;
they neither import the product implementation nor patch its subprocess runner.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class KnowledgeWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="knowledge-workflow-public-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.db = self.base / "store.sqlite3"
        self.serial = 0
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

    def json_file(self, payload):
        self.serial += 1
        path = self.base / f"input-{self.serial}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", "harness", "--db", str(self.db), *args],
                                cwd=ROOT, env=self.env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        if expected == 0:
            self.assertEqual(result.stderr, "")
            return json.loads(result.stdout)
        return json.loads(result.stderr)

    def start(self, task="writer", project="project-a", roles=None, goal="Investigate cache"):
        payload = {"task_id": task, "project_id": project, "goal": goal}
        if roles is not None:
            payload["roles"] = roles
        output = self.base / f"start-{task}"
        result = self.cli("workflow", "start", "--input", self.json_file(payload),
                          "--output", str(output))
        return result, output

    def finish(self, task="writer", directory=None):
        output = directory or self.base / f"finish-{task}"
        result = self.cli("workflow", "finish", "--task", task, "--input",
                          self.json_file({"status": "success", "evidence_ids": []}),
                          "--output", str(output))
        return result, output

    def test_start_initializes_store_and_only_requested_role_briefs(self):
        result, output = self.start(roles=["public", "adversarial"])
        self.assertTrue(self.db.is_file())
        self.assertEqual(result["task_id"], "writer")
        self.assertEqual(Path(result["output"]), output)
        self.assertIn("brief_paths", result)
        self.assertEqual({p.name for p in output.iterdir()},
                         {"task.json", "scout-public.json", "scout-adversarial.json"})
        task = json.loads((output / "task.json").read_text())
        self.assertEqual(task["task_id"], "writer")
        self.assertEqual(set(task["roles"]), {"public", "adversarial"})
        for role in ("public", "adversarial"):
            brief = json.loads((output / f"scout-{role}.json").read_text())
            self.assertIn("writer", json.dumps(brief))
            self.assertIn(role, json.dumps(brief))

    def test_start_reconciles_existing_queue_and_refuses_existing_directory(self):
        self.start()
        self.cli("task", "finish", "--task", "writer", "--input",
                 self.json_file({"status": "success", "evidence_ids": []}))
        self.cli("knowledge", "propose", "--task", "writer", "--batch", "empty",
                 "--input", self.json_file([]))
        self.start(task="reader")
        reconciled = self.cli("knowledge", "reconcile")
        self.assertEqual(reconciled["processed"], 0)
        self.assertEqual(reconciled["pending"], 0)
        existing = self.base / "existing-start"
        existing.mkdir()
        sentinel = existing / "task.json"
        sentinel.write_bytes(b"USER OWNED CONTENT\n")
        before = {p.name: p.read_bytes() for p in existing.iterdir()}
        self.cli("workflow", "start", "--input", self.json_file({
            "task_id": "other", "project_id": "project-a", "goal": "goal"}),
            "--output", str(existing), expected=2)
        self.assertEqual({p.name: p.read_bytes() for p in existing.iterdir()}, before)

    def test_finish_creates_curator_and_ingest_empty_closes_curation(self):
        self.start()
        result, output = self.finish()
        self.assertTrue(result["job_id"])
        self.assertEqual(Path(result["curator_path"]), output / "curator.json")
        self.assertEqual({p.name for p in output.iterdir()}, {"curator.json"})
        brief = json.loads((output / "curator.json").read_text())
        self.assertIn("writer", json.dumps(brief))
        self.assertIn("success", json.dumps(brief))
        state = self.cli("task", "show", "--task", "writer")
        self.assertIn("curation_pending", json.dumps(state))
        ingested = self.cli("workflow", "ingest", "--task", "writer", "--batch", "empty",
                            "--input", self.json_file([]))
        self.assertEqual(ingested["enqueue"]["status"], "queued")
        reconciliation = ingested["reconciliation"]
        receipt = next(r for r in reconciliation["receipts"]
                       if r["job_id"] == ingested["enqueue"]["job_id"])
        self.assertTrue(receipt["no_change"])
        self.assertEqual(receipt["entry_refs"], [])
        self.assertEqual(reconciliation["pending"], 0)
        self.assertNotIn("curation_pending", json.dumps(self.cli("task", "show", "--task", "writer")))

    def test_finish_refuses_existing_directory_without_overwriting(self):
        self.start()
        existing = self.base / "existing-finish"
        existing.mkdir()
        (existing / "curator.json").write_bytes(b"preserve this file")
        self.cli("workflow", "finish", "--task", "writer", "--input",
                 self.json_file({"status": "success", "evidence_ids": []}),
                 "--output", str(existing), expected=2)
        self.assertEqual({p.name: p.read_bytes() for p in existing.iterdir()},
                         {"curator.json": b"preserve this file"})

    def test_ingest_and_context_persist_concrete_authorized_packet(self):
        self.start()
        self.finish()
        ingested = self.cli("workflow", "ingest", "--task", "writer", "--batch", "candidate",
                            "--input", self.json_file([{
                                "title": "Cache rule", "claim": "Cache bounded retry was reviewed.",
                                "kind": "decision", "evidence_ids": []}]))
        receipt = next(r for r in ingested["reconciliation"]["receipts"]
                       if r["job_id"] == ingested["enqueue"]["job_id"])
        entry_id, revision = receipt["entry_refs"][0].rsplit("@", 1)
        self.cli("knowledge", "review", "--task", "writer", "--entry", entry_id,
                 "--expected-revision", revision, "--decision", "approve")
        self.start(task="reader", roles=["public"])
        searched = self.cli("knowledge", "search", "--task", "reader", "--query", "Cache", "--role", "public")
        current = searched["results"][0]
        ref = f"{current['entry_id']}@{current['revision']}"
        output = self.base / "context"
        result = self.cli("workflow", "context", "--task", "reader", "--role", "public",
                          "--input", self.json_file({"selected_refs": [ref]}),
                          "--output", str(output), "--budget", "900")
        packet_path, text_path = Path(result["packet_path"]), Path(result["text_path"])
        self.assertEqual(packet_path.parent, output)
        self.assertEqual(text_path.parent, output)
        self.assertIn(result["packet_id"], packet_path.name)
        self.assertIn(result["packet_id"], text_path.name)
        packet = json.loads(packet_path.read_text())
        self.assertEqual(packet["packet_id"], result["packet_id"])
        self.assertEqual(packet["role"], "public")
        self.assertEqual(packet["task_id"], "reader")
        self.assertEqual(packet["text"], text_path.read_text())
        self.assertIn(current["claim"], packet["text"])
        self.assertLessEqual(packet["token_count"], 900)
        self.assertEqual(len(packet["sources"]), 1)
        self.cli("context", "expand", "--packet", packet["packet_id"], "--entry", ref)
        error = self.cli("workflow", "context", "--task", "reader", "--role", "public",
                         "--input", self.json_file({"selected_refs": ["K-missing@1"]}),
                         "--output", str(self.base / "unavailable"), expected=2)
        self.assertIn("not_found", json.dumps(error))

    def test_workflow_inputs_remain_inert_and_no_agent_or_test_outputs_appear(self):
        marker = self.base / "unexpected-execution"
        goal = f"Cache $(/usr/bin/touch '{marker}'); run codex, claude, pytest and generate tests"
        # Observable tripwires for accidental CLI delegation, not patches in the
        # product process. The Python CLI itself is launched with its absolute path.
        traps = self.base / "trap-bin"
        traps.mkdir()
        for name in ("codex", "claude", "llm", "openai", "pytest", "uv"):
            trap = traps / name
            trap.write_text(f"#!/bin/sh\n/usr/bin/touch '{marker}'\nexit 97\n")
            trap.chmod(0o755)
        self.env["PATH"] = str(traps) + os.pathsep + self.env.get("PATH", "")
        _, start_dir = self.start(goal=goal)
        _, finish_dir = self.finish()
        self.cli("workflow", "ingest", "--task", "writer", "--batch", "empty",
                 "--input", self.json_file([]))
        self.assertFalse(marker.exists())
        self.assertEqual({p.name for p in start_dir.iterdir()},
                         {"task.json", "scout-developer.json", "scout-public.json", "scout-adversarial.json"})
        self.assertEqual({p.name for p in finish_dir.iterdir()}, {"curator.json"})


if __name__ == "__main__":
    unittest.main()
