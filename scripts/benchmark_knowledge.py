#!/usr/bin/env python3
"""Evaluate a precommitted retrieval corpus; no query/label generation or tuning."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.embeddings import LocalEmbedder
from harness.knowledge import KnowledgeStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    corpus = json.loads(args.corpus.read_text())
    started = time.perf_counter()
    provider = LocalEmbedder(args.model)
    load_seconds = time.perf_counter() - started
    with tempfile.TemporaryDirectory(prefix="harness-retrieval-benchmark-") as directory:
        with KnowledgeStore(Path(directory) / "store.sqlite3", embedder=provider) as store:
            ids = {}
            for doc in corpus["documents"]:
                task = "seed-" + doc["id"]
                store.begin_task(task, "benchmark", "Import fixed evaluation corpus", roles=["developer"])
                file = Path(directory) / (doc["id"] + ".txt")
                file.write_text(doc["claim"])
                evidence = store.add_evidence(task, file)["evidence_id"]
                store.finish_task(task, {"status": "success", "evidence_ids": [evidence]})
                store.propose(task, [{"title": doc["title"], "claim": doc["claim"], "kind": "observation",
                                      "symbols": doc.get("symbols", []), "tags": doc.get("tags", []),
                                      "evidence_ids": [evidence], "basis": {"evidence_id": evidence, "quote": doc["claim"]}}], "import")
                receipts = store.reconcile()["receipts"]
                entry = next(r["entry_refs"][0].split("@")[0] for r in receipts if r.get("entry_refs"))
                ids[entry] = doc["id"]
            started = time.perf_counter()
            index = store.index_sync()
            index_seconds = time.perf_counter() - started
            store.begin_task("retrieval", "benchmark", "Fixed retrieval comparison", roles=["developer"])
            rows = []
            for query in corpus["queries"]:
                modes = {}
                for mode in ("lexical", "semantic", "hybrid"):
                    started = time.perf_counter()
                    result = store.search("retrieval", query["text"], mode=mode, limit=3)
                    elapsed = (time.perf_counter() - started) * 1000
                    ranked = [ids[r["entry_id"]] for r in result["results"]]
                    relevant = set(query["relevant"])
                    modes[mode] = {"ranked": ranked, "status": result["status"], "actual_mode": result["mode"],
                                   "recall_at_3": len(set(ranked) & relevant) / len(relevant),
                                   "mrr_at_3": next((1 / rank for rank, entry in enumerate(ranked, 1) if entry in relevant), 0),
                                   "elapsed_ms": round(elapsed, 3)}
                rows.append({**query, "modes": modes})
            summary = {mode: {metric: statistics.mean(r["modes"][mode][metric] for r in rows)
                              for metric in ("recall_at_3", "mrr_at_3", "elapsed_ms")}
                       for mode in ("lexical", "semantic", "hybrid")}
    actual = all(r["modes"][m]["actual_mode"] == m and r["modes"][m]["status"] != "degraded"
                 for r in rows for m in ("semantic", "hybrid"))
    report = {"status": "pass" if actual and index["status"] == "ready" else "fail",
              "corpus_sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
              "model_id": provider.model_id, "dimensions": provider.dimensions,
              "documents": len(corpus["documents"]), "queries": len(rows), "summary": summary,
              "bundle_validation_seconds": load_seconds, "cold_index_seconds": index_seconds,
              "results": rows, "limitations": "Development smoke set, no holdout or task-success estimate. Semantic queries run before hybrid: hybrid benefits from query cache. Cold model load is included in index timing."}
    (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "summary": summary, "result": str(args.output / "results.json")}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
