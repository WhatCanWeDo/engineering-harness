"""Post-hoc adversarial checks for the frozen Knowledge MVP1 contract.

HARNESS_CANDIDATE_ROOT points to a candidate tree; unset uses the working tree.
Only temporary databases/evidence files are modified. No private backend used.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(os.environ.get("HARNESS_CANDIDATE_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT))
from harness.knowledge import KnowledgeError, KnowledgeStore


class KnowledgeAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.dbpath = self.home / "knowledge.sqlite3"
        self.store = KnowledgeStore(self.dbpath)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def begin(self, task="author", project="project", **kwargs):
        return self.store.begin_task(task, project, "needle", **kwargs)

    def finish(self, task="author", evidence=()):
        return self.store.finish_task(task, {"status": "success", "evidence_ids": list(evidence)})

    def entry(self, kind="observation", claim="needle observed", **extra):
        self.begin()
        path = self.home / "evidence.txt"
        path.write_text(claim, encoding="utf-8")
        ev = self.store.add_evidence("author", path)["evidence_id"]
        self.finish(evidence=[ev])
        proposal = {"kind": kind, "claim": claim, "evidence_ids": [ev],
                    "basis": {"evidence_id": ev, "quote": claim}, **extra}
        self.store.propose("author", [proposal], "seed")
        receipts = self.store.reconcile()["receipts"]
        return next(r["entry_refs"][0] for r in receipts if r["entry_refs"])

    def assert_error(self, code, fn, *args, **kwargs):
        with self.assertRaises(KnowledgeError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def test_task_batch_tuple_has_no_delimiter_collision_same_payload(self):
        """propose: idempotency is scoped to the full (task_id, batch_id) pair."""
        self.begin("a:b", "one")
        self.begin("a", "two")
        self.finish("a:b")
        self.finish("a")
        payload = [{"kind": "decision", "claim": "needle decision"}]
        first = self.store.propose("a:b", payload, "c")
        second = self.store.propose("a", payload, "b:c")
        self.assertNotEqual(first["job_id"], second["job_id"],
                            "Distinct task/batch tuples must enqueue separate jobs")
        self.store.close()
        self.store = KnowledgeStore(self.dbpath)
        self.store.reconcile()
        for project in ("one", "two"):
            self.assertEqual(1, len(self.store.export_project(project)["entries"]))

    def test_task_batch_tuple_has_no_delimiter_collision_different_payload(self):
        self.begin("a:b", "one")
        self.begin("a", "two")
        self.finish("a:b")
        self.finish("a")
        self.store.propose("a:b", [], "c")
        result = self.store.propose("a", [{"kind": "decision", "claim": "needle"}], "b:c")
        self.assertFalse(result["idempotent"])

    def test_quote_and_kind_matrix_cannot_auto_publish_generalizations(self):
        self.begin()
        path = self.home / "evidence.txt"
        path.write_text("needle observed", encoding="utf-8")
        ev = self.store.add_evidence("author", path)["evidence_id"]
        self.finish(evidence=[ev])
        proposals = []
        for kind in ("observation", "decision", "hypothesis", "negative_result", "procedure", "preference"):
            for basis in (None, {"evidence_id": ev, "quote": "needle observed"}):
                for claim in ("needle observed", "needle universal"):
                    value = {"kind": kind, "claim": claim, "evidence_ids": [ev]}
                    if basis:
                        value["basis"] = basis
                    proposals.append(value)
        self.store.propose("author", proposals, "matrix")
        self.store.reconcile()
        records = self.store.export_project("project")["entries"]
        self.assertEqual(24, len(records))
        active = [r for r in records if r["state"] == "active"]
        self.assertEqual(1, len(active))
        self.assertEqual(("observation", "needle observed"), (active[0]["kind"], active[0]["claim"]))

    def test_queued_update_conflict_rolls_back_entire_batch_after_reopen(self):
        ref = self.entry()
        key = ref.split("@")[0]
        self.begin("updater")
        self.finish("updater")
        self.store.propose("updater", [
            {"kind": "decision", "claim": "must roll back"},
            {"kind": "decision", "claim": "update", "entry_id": key, "expected_revision": 1},
        ], "atomic")
        self.store.review("author", key, 1, "approve")
        self.store.close()
        self.store = KnowledgeStore(self.dbpath)
        receipts = self.store.reconcile()["receipts"]
        self.assertTrue(any(r.get("code") == "conflict" for r in receipts))
        self.assertEqual(1, len(self.store.export_project("project")["entries"]))
        self.assertEqual(0, self.store.reconcile()["processed"])

    def test_snapshot_applicability_scopes_and_explicit_refs(self):
        self.begin("early")
        ref = self.entry(applicability={"runtime": "v1"})
        self.begin("match", applicability={"runtime": "v1"})
        self.begin("missing")
        self.begin("wrong", applicability={"runtime": "v2"})
        self.begin("foreign", project="other", applicability={"runtime": "v1"})
        self.assertEqual(1, len(self.store.search("match", "needle")["results"]))
        for task in ("early", "missing", "wrong", "foreign"):
            with self.subTest(task=task):
                self.assertEqual([], self.store.search(task, "needle")["results"])
                self.assert_error("not_found", self.store.prepare_context, task, selected_refs=[ref])
                self.assert_error("required_context_unavailable", self.store.prepare_context, task, required_refs=[ref])

    def test_future_observation_excluded_even_when_recorded_before_snapshot(self):
        ref = self.entry(observed_at="2999-01-01T00:00:00Z")
        self.begin("reader")
        self.assertEqual([], self.store.search("reader", "needle")["results"])
        self.assert_error("not_found", self.store.prepare_context, "reader", selected_refs=[ref])

    def test_approved_hypothesis_still_requires_explicit_candidate_search(self):
        ref = self.entry(kind="hypothesis")
        key = ref.split("@")[0]
        reviewed = self.store.review("author", key, 1, "approve")
        self.begin("reader")
        self.assertEqual([], self.store.search("reader", "needle")["results"])
        result = self.store.search("reader", "needle", include_candidates=True)["results"]
        self.assertEqual(["hypothesis"], [r["kind"] for r in result])
        self.assert_error("not_found", self.store.prepare_context, "reader", selected_refs=[reviewed["entry_ref"]])

    def test_context_source_cap_cannot_silently_drop_required_refs(self):
        self.begin()
        path = self.home / "many.txt"
        path.write_text("needle", encoding="utf-8")
        ev = self.store.add_evidence("author", path)["evidence_id"]
        self.finish(evidence=[ev])
        proposals = [{"kind": "observation", "claim": "needle", "evidence_ids": [ev],
                      "basis": {"evidence_id": ev, "quote": "needle"}} for _ in range(9)]
        self.store.propose("author", proposals, "many")
        refs = self.store.reconcile()["receipts"][-1]["entry_refs"]
        self.begin("reader")
        packet = self.store.prepare_context("reader", selected_refs=refs, budget=100000)
        self.assertEqual(8, len(packet["sources"]))
        self.assertEqual(1, len(packet["omitted_by_budget"]))
        self.assert_error("required_context_overflow", self.store.prepare_context, "reader", required_refs=refs, budget=100000)
        packet = self.store.prepare_context("reader", required_refs=[refs[0]] * 9, selected_refs=[], budget=100000)
        self.assertEqual(1, len(packet["sources"]))

    def test_packet_rechecks_revision_revocation_and_role(self):
        ref = self.entry()
        key = ref.split("@")[0]
        self.begin("reader")
        packet = self.store.prepare_context("reader", selected_refs=[ref])
        self.assertEqual(key, self.store.expand(packet["packet_id"], ref)["entry_id"])
        self.store.set_task_roles("reader", ["public"])
        self.assert_error("not_found", self.store.expand, packet["packet_id"], ref)
        self.store.set_task_roles("reader", ["developer", "public"])
        self.store.review("author", key, 1, "approve")
        self.assert_error("not_found", self.store.expand, packet["packet_id"], ref)
        self.assertTrue(self.store.get_entry("reader", key, revision=1)["historical"])
        self.store.review("author", key, 2, "retract")
        self.assert_error("not_found", self.store.get_entry, "reader", key, revision=1)

    def test_promoted_general_projection_does_not_export_project_evidence(self):
        ref = self.entry(claim="needle SECRET_PROJECT_CLAIM")
        key = ref.split("@")[0]
        released = self.store.promote("author", key, 1, "needle release", "needle public claim")
        self.begin("foreign", project="other")
        projection = self.store.get_entry("foreign", released["entry_id"])
        public = json.dumps(projection)
        for secret in ("SECRET_PROJECT_CLAIM", key, "origin_task", "source_entry_ref", "evidence_id"):
            self.assertNotIn(secret, public)
        self.assertIn("release_ref", public)
        self.assertEqual(1, len(self.store.export_project("other")["entries"]))

    def test_budget_matrix_and_fts_metacharacters(self):
        ref = self.entry(claim="needle наблюдение 😀 café")
        self.begin("reader")
        for budget in (1, 2, 40, 99, 200, 500, 1200):
            with self.subTest(budget=budget):
                packet = self.store.prepare_context("reader", selected_refs=[ref], budget=budget)
                self.assertLessEqual(packet["token_count"], budget)
                self.assertEqual((len(packet["text"].encode("utf-8")) + 2) // 3, packet["token_count"])
                if not packet["sources"]:
                    self.assertIn(ref, packet["omitted_by_budget"])
                    self.assert_error("required_context_overflow", self.store.prepare_context,
                                      "reader", required_refs=[ref], budget=budget)
        for query in ('"', "' OR 1=1 --", "NEAR(needle, 2)", "needle:*", "(\"", "😀", "\x00", ""):
            with self.subTest(query=query):
                result = self.store.search("reader", query)
                self.assertIsInstance(result["results"], list)

    def test_evidence_snapshot_immutable_and_batches_task_bound(self):
        ref = self.entry()
        source = self.home / "evidence.txt"
        source.write_text("replaced", encoding="utf-8")
        self.assertEqual("needle observed", self.store.get_entry("author", ref.split("@")[0])["claim"])
        ev = self.store.curator_brief("author")["evidence"][0]
        self.assertEqual("needle observed", ev["excerpt"])
        self.begin("other")
        self.finish("other")
        self.assert_error("not_found", self.store.propose, "other", [
            {"kind": "decision", "claim": "would be valid"},
            {"kind": "observation", "claim": "needle", "evidence_ids": [ev["evidence_id"]]},
        ], "invalid")
        self.assertEqual([], self.store.reconcile()["receipts"][-1]["entry_refs"])
        self.assertEqual(1, len(self.store.export_project("project")["entries"]))

    def cli(self, *args, expected=0):
        env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-m", "harness", "--db", str(self.dbpath), *args],
                                cwd=self.home, env=env, capture_output=True, text=True)
        self.assertEqual(expected, result.returncode, result.stderr)
        return json.loads(result.stdout if expected == 0 else result.stderr)

    def test_cli_lifecycle_reopen_retry_and_existing_directory(self):
        binding = self.home / "binding.json"
        binding.write_text(json.dumps({"task_id": "cli", "project_id": "p", "goal": "needle", "roles": ["public"]}))
        output = self.home / "start"
        started = self.cli("workflow", "start", "--input", str(binding), "--output", str(output))
        self.assertEqual(["public"], list(started["brief_paths"]))
        initial = (output / "task.json").read_bytes()
        self.assertEqual("output_exists", self.cli("workflow", "start", "--input", str(binding), "--output", str(output), expected=2)["code"])
        self.assertEqual(initial, (output / "task.json").read_bytes())
        outcome = self.home / "outcome.json"
        outcome.write_text('{"status":"interrupted","evidence_ids":[]}')
        completed = self.cli("workflow", "finish", "--task", "cli", "--input", str(outcome), "--output", str(self.home / "finish"))
        retried = self.cli("task", "finish", "--task", "cli", "--input", str(outcome))
        self.assertEqual(completed["job_id"], retried["job_id"])
        proposals = self.home / "proposals.json"
        proposals.write_text("[]")
        self.cli("workflow", "ingest", "--task", "cli", "--batch", "empty", "--input", str(proposals))
        self.assertEqual("complete", self.cli("task", "show", "--task", "cli")["curation_status"])


if __name__ == "__main__":
    unittest.main()
