"""MVP2 public contract tests frozen before semantic implementation.

Synthetic vectors exercise mechanics, never semantic quality. Run from repo root:
python3 -m unittest discover -s tests -p 'test_knowledge_semantic.py' -v
"""

import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from harness.knowledge import KnowledgeError, KnowledgeStore


class SyntheticProvider:
    """Explicit deterministic vectors; document formatting is not prescribed."""

    def __init__(self, model_id="public-synthetic/v1", dimensions=3):
        self.model_id = model_id
        self.dimensions = dimensions
        self.documents = {}
        self.queries = {}
        self.calls = []
        self.failure = None

    def embed(self, texts, kind="document"):
        texts = list(texts)
        self.calls.append((kind, texts))
        if self.failure == "exception":
            raise RuntimeError("intentional local provider failure")
        vectors = []
        for text in texts:
            vector = [1.0] + [0.0] * (self.dimensions - 1)
            if kind == "query":
                vector = self.queries.get(text, vector)
            else:
                matches = [v for marker, v in self.documents.items() if marker in text]
                if len(matches) > 1:
                    raise AssertionError("ambiguous synthetic document markers")
                if matches:
                    vector = matches[0]
            vectors.append(list(vector))
        if self.failure == "count":
            return vectors[:-1]
        if vectors and self.failure:
            bad = {
                "dimension": [1.0] * (self.dimensions + 1),
                "zero": [0.0] * self.dimensions,
                "nan": [math.nan] + [0.0] * (self.dimensions - 1),
                "infinity": [math.inf] + [0.0] * (self.dimensions - 1),
            }
            vectors[-1] = bad[self.failure]
        return vectors

    def count(self, kind):
        return sum(len(texts) for call_kind, texts in self.calls if call_kind == kind)


class KnowledgeSemanticContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "knowledge.sqlite3"
        self.provider = SyntheticProvider()
        self.store = KnowledgeStore(self.path, embedder=self.provider)
        self.serial = 0

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def reopen(self, provider):
        self.store.close()
        self.store = KnowledgeStore(self.path, embedder=provider)

    def task(self, project="project-a", **kwargs):
        self.serial += 1
        task_id = "public-task-" + str(self.serial)
        self.store.begin_task(task_id, project, "public contract fixture", **kwargs)
        return task_id

    def publish(self, marker, vector=None, project="project-a", kind="observation",
                applicability=None, symbols=None, update=None, grounded=True):
        task = self.task(project)
        claim = marker + " reproducible source observation"
        evidence_file = self.root / (task + ".txt")
        evidence_file.write_text(claim, encoding="utf-8")
        evidence = self.store.add_evidence(task, str(evidence_file))
        self.store.finish_task(task, {"status": "success", "evidence_ids": [evidence["evidence_id"]]})
        self.store.reconcile()
        proposal = {
            "title": marker, "claim": claim, "kind": kind, "scope": "project",
            "evidence_ids": [evidence["evidence_id"]],
            "applicability": applicability or {}, "symbols": symbols or [],
        }
        if grounded:
            proposal["basis"] = {"evidence_id": evidence["evidence_id"], "quote": claim}
        if update:
            proposal.update(entry_id=update[0], expected_revision=update[1])
        self.store.propose(task, [proposal], batch_id="public-batch")
        receipts = self.store.reconcile()["receipts"]
        refs = [ref for receipt in receipts for ref in receipt.get("entry_refs", [])]
        self.assertEqual(len(refs), 1)
        entry_id, revision = refs[0].rsplit("@", 1)
        if vector is not None:
            self.provider.documents[marker] = vector
        return entry_id, int(revision)

    def ids(self, result):
        return [entry["entry_id"] for entry in result["results"]]

    def ready(self):
        result = self.store.index_sync()
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["remaining"], 0)
        self.assertEqual(result["model_id"], self.provider.model_id)
        return result

    def search(self, task, query="unshared-query", mode="semantic", **kwargs):
        result = self.store.search(task, query, mode=mode, **kwargs)
        self.assertEqual(result["mode"], mode)
        self.assertNotEqual(result["status"], "degraded")
        return result

    def assert_fallback(self, task, query, mode):
        baseline = self.store.search(task, query, mode="lexical")
        result = self.store.search(task, query, mode=mode)
        self.assertEqual(result["mode"], "lexical")
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(result["warnings"])
        self.assertEqual(self.ids(result), self.ids(baseline))
        return result

    def test_empty_index_and_status_do_not_embed(self):
        status = self.store.index_status()
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["remaining"], 0)
        self.assertEqual(status["model_id"], self.provider.model_id)
        self.assertIn("watermark", status)
        self.assertEqual(self.ready()["indexed"], 0)
        self.assertEqual(self.provider.calls, [])

    def test_no_provider_status_and_explicit_lexical_fallback(self):
        self.publish("fallbackneedle")
        task = self.task()
        self.reopen(None)
        self.assertEqual(self.store.index_status()["status"], "unavailable")
        self.assertEqual(self.store.index_sync()["status"], "unavailable")
        for mode in ("semantic", "hybrid"):
            self.assert_fallback(task, "fallbackneedle", mode)

    def test_limit_restart_idempotence_and_watermark_not_task_counter(self):
        for marker in ("doc_alpha", "doc_beta", "doc_gamma"):
            self.publish(marker)
        initial = self.store.index_status()
        self.assertEqual(initial["status"], "lagging")
        self.assertEqual(initial["remaining"], 3)
        self.assertEqual(self.provider.calls, [])
        first = self.store.index_sync(limit=1)
        self.assertEqual(first["indexed"], 1)
        self.assertEqual(first["remaining"], 2)
        self.assertEqual(first["status"], "lagging")
        second_provider = SyntheticProvider()
        self.reopen(second_provider)
        self.provider = second_provider
        final = self.ready()
        self.assertEqual(final["indexed"], 2)
        self.assertEqual(second_provider.count("document"), 2)
        self.assertEqual(self.ready()["indexed"], 0)
        self.assertEqual(second_provider.count("document"), 2)
        self.task()
        self.task()
        self.assertEqual(self.store.index_status()["watermark"], final["watermark"])

    def test_invalid_provider_batch_commits_no_vectors(self):
        self.publish("doc_alpha")
        self.publish("doc_beta")
        for failure in ("exception", "count", "dimension", "zero", "nan", "infinity"):
            with self.subTest(failure=failure):
                before = self.store.index_status()
                self.provider.failure = failure
                try:
                    result = self.store.index_sync(limit=2)
                except Exception:
                    # Contract specifies atomicity, not the provider-error envelope.
                    pass
                else:
                    self.assertNotEqual(result["status"], "ready")
                    self.assertEqual(result["indexed"], 0)
                self.provider.failure = None
                after = self.store.index_status()
                self.assertEqual(after["remaining"], 2)
                self.assertEqual(after["watermark"], before["watermark"])
        self.assertEqual(self.ready()["indexed"], 2)

    def test_index_excludes_candidate_hypothesis_and_inactive_entries(self):
        active = self.publish("doc_active")[0]
        self.publish("doc_candidate", grounded=False)
        hypothesis = self.publish("doc_hypothesis", kind="hypothesis")
        stale = self.publish("doc_stale")
        retracted = self.publish("doc_retracted")
        admin = self.task()
        self.store.review(admin, hypothesis[0], hypothesis[1], "approve")
        self.store.review(admin, stale[0], stale[1], "stale")
        self.store.review(admin, retracted[0], retracted[1], "retract")
        self.assertEqual(self.ready()["indexed"], 1)
        self.assertEqual(self.provider.count("document"), 1)
        self.assertEqual(self.ids(self.search(self.task())), [active])

    def test_cosine_normalization_and_stable_ties(self):
        high = self.publish("doc_alpha", [2, 2, 0])[0]
        low = self.publish("doc_beta", [100, 0, 0])[0]
        tie = self.publish("doc_gamma", [0.5, 0.5, 0])[0]
        opposite = self.publish("doc_delta", [-10, -10, 0])[0]
        self.provider.queries["vector-query"] = [20, 20, 0]
        self.ready()
        task = self.task()
        expected = sorted([high, tie]) + [low, opposite]
        self.assertEqual(self.ids(self.search(task, "vector-query")), expected)
        self.assertEqual(self.ids(self.search(task, "vector-query")), expected)

    def test_hybrid_uses_equal_weight_rrf_k60(self):
        entries = [
            self.publish("sharedterm doc_alpha", [1, 0, 0])[0],
            self.publish("sharedterm sharedterm doc_beta", [0.8, 0.6, 0])[0],
            self.publish("sharedterm doc_gamma", [0, 1, 0])[0],
            self.publish("sharedterm doc_delta", [-1, 0, 0])[0],
        ]
        self.provider.queries["sharedterm"] = [1, 0, 0]
        self.ready()
        task = self.task()
        lexical = self.ids(self.store.search(task, "sharedterm", mode="lexical"))
        self.assertEqual(set(lexical), set(entries))
        scores = {entry: 1 / (60 + entries.index(entry) + 1)
                  + 1 / (60 + lexical.index(entry) + 1) for entry in entries}
        expected = sorted(entries, key=lambda entry: (-scores[entry], entry))
        self.assertEqual(self.ids(self.search(task, "sharedterm", mode="hybrid")), expected)

    def test_exact_entry_ref_and_symbol_override_vector_rank(self):
        target, revision = self.publish("doc_alpha", [-1, 0, 0], symbols=["Cache.invalidate"])
        self.publish("doc_beta", [1, 0, 0])
        self.ready()
        task = self.task()
        for mode in ("semantic", "hybrid"):
            for query in (target, target + "@" + str(revision), "Cache.invalidate"):
                with self.subTest(mode=mode, query=query):
                    self.assertEqual(self.ids(self.search(task, query, mode))[0], target)

    def test_hybrid_caps_each_input_rank_at_thirty(self):
        semantic_order = []
        for index in range(35):
            angle = index / 12
            entry = self.publish("sharedterm marker%03dend" % index,
                                 [math.cos(angle), math.sin(angle), 0])[0]
            semantic_order.append(entry)
        self.provider.queries["sharedterm"] = [1, 0, 0]
        self.ready()
        task = self.task()
        lexical = self.ids(self.store.search(task, "sharedterm", mode="lexical", limit=30))
        semantic = semantic_order[:30]
        scores = {}
        for ranking in (lexical, semantic):
            for rank, entry in enumerate(ranking, start=1):
                scores[entry] = scores.get(entry, 0) + 1 / (60 + rank)
        expected = sorted(scores, key=lambda entry: (-scores[entry], entry))[:30]
        self.assertEqual(self.ids(self.search(task, "sharedterm", "hybrid", limit=30)), expected)

    def test_lexical_and_empty_queries_never_call_provider(self):
        self.publish("doc_alpha")
        task = self.task()
        self.provider.failure = "exception"
        self.store.search(task, "doc_alpha", mode="lexical")
        for mode in ("lexical", "semantic", "hybrid"):
            self.assertEqual(self.ids(self.store.search(task, "", mode=mode)), [])
        self.assertEqual(self.provider.calls, [])

    def test_index_lag_and_query_provider_failure_are_honest_fallbacks(self):
        self.publish("fallbackneedle")
        task = self.task()
        for mode in ("semantic", "hybrid"):
            self.assert_fallback(task, "fallbackneedle", mode)
        self.ready()
        self.provider.failure = "exception"
        for mode in ("semantic", "hybrid"):
            self.assert_fallback(task, "fallbackneedle", mode)

    def test_unindexed_inaccessible_entries_do_not_degrade_complete_visible_corpus(self):
        allowed = self.publish("doc_alpha")[0]
        self.ready()
        task = self.task()
        self.publish("doc_beta", project="project-b")
        self.publish("doc_gamma")  # This revision is after this task's cutoff.
        self.assertEqual(self.store.index_status()["status"], "lagging")
        for mode in ("semantic", "hybrid"):
            self.assertEqual(self.ids(self.search(task, mode=mode)), [allowed])

    def test_invalid_query_vectors_fall_back(self):
        self.publish("fallbackneedle")
        self.ready()
        task = self.task()
        for failure in ("count", "dimension", "zero", "nan", "infinity"):
            self.provider.failure = failure
            for mode in ("semantic", "hybrid"):
                with self.subTest(failure=failure, mode=mode):
                    self.assert_fallback(task, "fallbackneedle " + failure, mode)

    def test_query_cache_persists_and_is_project_scoped(self):
        self.publish("doc_alpha")
        self.publish("doc_beta", project="project-b")
        self.ready()
        a = self.task()
        b = self.task("project-b")
        self.search(a, "same-query")
        self.search(a, "same-query", mode="hybrid")
        self.assertEqual(self.provider.count("query"), 1)
        self.search(b, "same-query")
        self.assertEqual(self.provider.count("query"), 2)
        second = SyntheticProvider()
        self.reopen(second)
        self.search(a, "same-query")
        self.search(b, "same-query")
        self.assertEqual(second.calls, [])
        self.search(a, "different-query")
        self.assertEqual(second.count("query"), 1)

    def test_query_cache_survives_an_actual_new_process(self):
        self.publish("doc_alpha")
        self.ready()
        task = self.task()
        self.search(task, "persistent-query")
        expected = self.ids(self.search(task, "persistent-query"))
        self.store.close()
        script = """
import json, sys
from harness.knowledge import KnowledgeStore
class CacheOnlyProvider:
    model_id = 'public-synthetic/v1'
    dimensions = 3
    def embed(self, texts, kind='document'):
        raise AssertionError('persisted vector cache unexpectedly missed')
with KnowledgeStore(sys.argv[1], embedder=CacheOnlyProvider()) as store:
    print(json.dumps(store.search(sys.argv[2], 'persistent-query', mode='semantic')))
"""
        process = subprocess.run([sys.executable, "-c", script, str(self.path), task],
                                 cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True, text=True, timeout=20)
        self.store = KnowledgeStore(self.path, embedder=self.provider)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["mode"], "semantic")
        self.assertNotEqual(result["status"], "degraded")
        self.assertEqual(self.ids(result), expected)

    def test_new_model_and_dimensions_never_reuse_old_vectors(self):
        self.publish("doc_alpha")
        self.ready()
        task = self.task()
        self.search(task, "same-query")
        for model, dimensions in (("public-synthetic/v2", 3), ("public-synthetic/v2", 4)):
            with self.subTest(model=model, dimensions=dimensions):
                new = SyntheticProvider(model, dimensions)
                self.reopen(new)
                self.provider = new
                self.assertEqual(self.store.index_status()["remaining"], 1)
                self.assertEqual(self.ready()["indexed"], 1)
                self.search(task, "same-query")
                self.assertEqual(new.count("document"), 1)
                self.assertEqual(new.count("query"), 1)

    def test_revised_entry_gets_new_vector_and_old_snapshot_cannot_read_it(self):
        old = self.publish("doc_alpha", [1, 0, 0])
        other = self.publish("doc_beta", [0, 1, 0])[0]
        self.ready()
        before = self.task()
        self.assertEqual(self.ids(self.search(before))[0], old[0])
        revised = self.publish("doc_gamma", [-1, 0, 0], update=old)
        self.assertEqual(revised, (old[0], old[1] + 1))
        after = self.task()
        self.assertEqual(self.store.index_status()["remaining"], 1)
        self.assert_fallback(after, "doc_gamma", "semantic")
        self.assertEqual(self.ready()["indexed"], 1)
        self.assertEqual(self.ids(self.search(after)), [other, old[0]])
        self.assertNotIn(old[0], self.ids(self.search(before)))

    def test_vectors_do_not_bypass_project_cutoff_or_applicability(self):
        allowed = self.publish("doc_alpha")[0]
        foreign = self.publish("doc_beta", project="project-b")[0]
        linux = self.publish("doc_gamma", applicability={"platform": "linux"})[0]
        windows = self.publish("doc_delta", applicability={"platform": "windows"})[0]
        task = self.task(applicability={"platform": "linux"})
        later = self.publish("doc_epsilon")[0]
        self.ready()
        for mode in ("semantic", "hybrid"):
            result = self.search(task, mode=mode)
            self.assertEqual(set(self.ids(result)), {allowed, linux})
            for forbidden in (foreign, windows, later):
                self.assertNotIn(forbidden, self.ids(result))
            for forbidden in (foreign, windows, later):
                self.assertNotIn(forbidden, self.ids(self.search(task, forbidden, mode)))
        missing_conditions = self.task()
        self.assertNotIn(linux, self.ids(self.search(missing_conditions)))

    def test_cached_query_rechecks_retractions_and_stale_states(self):
        retracted = self.publish("doc_alpha")
        stale = self.publish("doc_beta")
        active = self.publish("doc_gamma")[0]
        self.ready()
        task = self.task()
        self.assertEqual(len(self.search(task)["results"]), 3)
        self.store.review(task, retracted[0], retracted[1], "retract")
        self.store.review(task, stale[0], stale[1], "stale")
        for mode in ("semantic", "hybrid"):
            result = self.store.search(task, "unshared-query", mode=mode)
            self.assertEqual(self.ids(result), [active])

    def test_context_sources_recheck_roles_and_revocation(self):
        entry, revision = self.publish("doc_alpha")
        self.ready()
        task = self.task()
        packet = self.store.prepare_context(task, query="unshared-query", role="public",
                                            mode="semantic", budget=1200)
        self.assertIn("doc_alpha", packet["text"])
        self.assertEqual(len(packet["sources"]), 1)
        ref = entry + "@" + str(revision)
        self.store.expand(packet["packet_id"], ref)
        self.store.set_task_roles(task, ["developer"])
        with self.assertRaises(KnowledgeError):
            self.store.expand(packet["packet_id"], ref)
        self.store.set_task_roles(task, ["developer", "public", "adversarial"])
        self.store.review(task, entry, revision, "retract")
        with self.assertRaises(KnowledgeError) as error:
            self.store.expand(packet["packet_id"], ref)
        self.assertEqual(error.exception.code, "not_found")

    def test_prepare_and_scout_accept_modes_and_lexical_defaults(self):
        self.publish("doc_alpha")
        self.ready()
        task = self.task()
        calls = len(self.provider.calls)
        self.store.prepare_context(task, query="doc_alpha")
        self.store.scout_brief(task)
        self.assertEqual(len(self.provider.calls), calls)
        for mode in ("semantic", "hybrid"):
            packet = self.store.prepare_context(task, query="context-query", mode=mode)
            self.assertIn("doc_alpha", packet["text"])
            self.assertTrue(packet["sources"])
            brief = self.store.scout_brief(task, mode=mode)
            self.assertIsInstance(brief, dict)


if __name__ == "__main__":
    unittest.main()
