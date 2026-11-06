"""Derived local vector index, incremental recovery and deterministic rank fusion."""
import json
import math

from .knowledge import KnowledgeError, encode, fail, positive, sha, text

SCHEMA = """
CREATE TABLE IF NOT EXISTS embedding_vectors(model_key TEXT NOT NULL, entry_id TEXT NOT NULL, revision INTEGER NOT NULL, content_hash TEXT NOT NULL, vector TEXT NOT NULL, PRIMARY KEY(model_key,entry_id));
CREATE TABLE IF NOT EXISTS embedding_state(model_key TEXT PRIMARY KEY, watermark INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS query_vectors(model_key TEXT NOT NULL, project_id TEXT NOT NULL, query_hash TEXT NOT NULL, vector TEXT NOT NULL, PRIMARY KEY(model_key,project_id,query_hash));
"""


def identity(provider):
    if provider is None:
        fail("embedding_unavailable", "No local embedding provider configured")
    model = text(provider.model_id, "model_id", 1000)
    dimensions = positive(provider.dimensions, "dimensions")
    return encode([model, dimensions]), model, dimensions


def document(record):
    return record["title"] + "\n" + record["claim"] + "\n" + " ".join(record.get("tags", []) + record.get("symbols", []))


def normalized(vector, dimensions):
    try:
        values = [float(v) for v in vector]
        if len(values) != dimensions or any(not math.isfinite(v) for v in values):
            raise ValueError("Wrong dimension or non-finite vector")
        scale = max((abs(v) for v in values), default=0)
        if scale == 0:
            raise ValueError("Invalid vector norm")
        # Scale first: subnormal/very large finite inputs otherwise under/overflow.
        scaled = [v / scale for v in values]
        norm = math.hypot(*scaled)
        return [v / norm for v in scaled]
    except (TypeError, ValueError, OverflowError) as exc:
        fail("embedding_error", str(exc))


def embed(provider, texts, kind):
    try:
        _, _, dimensions = identity(provider)
        vectors = list(provider.embed(texts, kind=kind))
        if len(vectors) != len(texts):
            fail("embedding_error", "Provider returned wrong batch size")
        return [normalized(v, dimensions) for v in vectors]
    except Exception as exc:
        # Never expose provider exception text: it may contain input material.
        raise KnowledgeError("embedding_error", "Local embedding provider failed or returned invalid vectors") from exc


def targets(store):
    return [r for r in store._records() if r["state"] == "active" and r["kind"] != "hypothesis"]


def existing(store, key):
    return {row["entry_id"]: dict(row) for row in store.db.execute("SELECT * FROM embedding_vectors WHERE model_key=?", (key,))}


def matches(row, record):
    return row is not None and row["revision"] == record["revision"] and row["content_hash"] == sha(document(record))


def status(store):
    if store.embedder is None:
        return {"status": "unavailable", "remaining": None, "model_id": None, "watermark": 0}
    key, model, _ = identity(store.embedder)
    rows = existing(store, key)
    remaining = sum(not matches(rows.get(r["entry_id"]), r) for r in targets(store))
    watermark = store.db.execute("SELECT watermark FROM embedding_state WHERE model_key=?", (key,)).fetchone()
    return {"status": "lagging" if remaining else "ready", "remaining": remaining,
            "model_id": model, "watermark": watermark[0] if watermark else 0}


def sync(store, limit=100):
    positive(limit, "limit")
    if store.embedder is None:
        return {**status(store), "indexed": 0}
    key, _, _ = identity(store.embedder)
    rows = existing(store, key)
    selected = [r for r in targets(store) if not matches(rows.get(r["entry_id"]), r)][:min(limit, 1000)]
    # Compute outside SQLite's writer lock; commit only a fully validated batch.
    vectors = embed(store.embedder, [document(r) for r in selected], "document") if selected else []
    indexed = 0
    with store._write():
        for record, vector in zip(selected, vectors):
            current = store._current(record["entry_id"])
            if current["revision"] != record["revision"] or current["state"] != "active":
                continue  # A concurrent revision will be picked up on the next sync.
            store.db.execute("INSERT OR REPLACE INTO embedding_vectors VALUES(?,?,?,?,?)",
                             (key, record["entry_id"], record["revision"], sha(document(record)), encode(vector)))
            indexed += 1
        result = status(store)
        if result["remaining"] == 0:
            watermark = store.db.execute("SELECT coalesce(max(seq),0) FROM revisions").fetchone()[0]
            store.db.execute("INSERT OR REPLACE INTO embedding_state VALUES(?,?)", (key, watermark))
    return {**status(store), "indexed": indexed}


def query_vector(store, task, query):
    key, _, dimensions = identity(store.embedder)
    params = (key, task["project_id"], sha(query))
    cached = store.db.execute("SELECT vector FROM query_vectors WHERE model_key=? AND project_id=? AND query_hash=?", params).fetchone()
    if cached:
        return normalized(json.loads(cached[0]), dimensions)
    vector = embed(store.embedder, [query], "query")[0]
    with store._write():
        store.db.execute("INSERT OR REPLACE INTO query_vectors VALUES(?,?,?,?)", (*params, encode(vector)))
        # Bounded per-project/model cache; raw queries are never stored here.
        store.db.execute("DELETE FROM query_vectors WHERE model_key=? AND project_id=? AND rowid NOT IN (SELECT rowid FROM query_vectors WHERE model_key=? AND project_id=? ORDER BY rowid DESC LIMIT 256)", (key, task["project_id"], key, task["project_id"]))
    return vector


def search(store, task_id, query, role, limit, include_candidates, mode):
    baseline = store.search(task_id, query, role, limit, include_candidates, mode="lexical")
    task = store.get_task(task_id)
    query = query.strip()[:4000]
    allowed = {r["entry_id"]: r for r in store._records() if store._eligible(task, r, include_candidates)}
    try:
        key, model, dimensions = identity(store.embedder)
        if not query or not allowed:
            return {**baseline, "mode": mode}
        rows = existing(store, key)
        if any(not matches(rows.get(k), r) for k, r in allowed.items()):
            fail("index_lagging", "Applicable corpus has missing or stale vectors")
        vector = query_vector(store, task, query)
        scores = {}
        for entry_id in allowed:
            candidate = normalized(json.loads(rows[entry_id]["vector"]), dimensions)
            scores[entry_id] = math.fsum(a * b for a, b in zip(vector, candidate))
        semantic = sorted(scores, key=lambda k: (-scores[k], k))
        if mode == "hybrid":
            lexical = store.search(task_id, query, role, 30, include_candidates, mode="lexical")
            fusion = {}
            for ranking in ([r["entry_id"] for r in lexical["results"]], semantic[:30]):
                for rank, entry_id in enumerate(ranking, 1):
                    fusion[entry_id] = fusion.get(entry_id, 0) + 1 / (60 + rank)
            ordered = sorted(fusion, key=lambda k: (-fusion[k], k))
        else:
            ordered = semantic
        normalized_query = query.casefold()
        exact = sorted(k for k, r in allowed.items() if normalized_query in {
            k.casefold(), f"{k}@{r['revision']}".casefold(), *(s.casefold() for s in r.get("symbols", []))})
        ordered = exact + [k for k in ordered if k not in exact]
        from .subprojects import rank
        ordered = rank(store, task, ordered, allowed, exact)
        # Re-read before returning so a slow query embedding cannot revive revoked data.
        fresh = store.get_task(task_id); store._role(fresh, role)
        results = []
        for entry_id in ordered:
            current = store._current(entry_id)
            if current["revision"] == allowed[entry_id]["revision"] and store._eligible(fresh, current, include_candidates):
                results.append(store._project(current))
            if len(results) >= min(limit, 100):
                break
        return {"status": "ok" if results else "empty", "mode": mode, "results": results,
                "snapshot_seq": task["snapshot_seq"], "model_id": model, "warnings": []}
    except (KnowledgeError, ValueError, TypeError, AttributeError) as exc:
        # Recompute fallback after a possible provider delay; do not return a stale baseline.
        fallback = store.search(task_id, query, role, limit, include_candidates, mode="lexical")
        reason = exc.code if isinstance(exc, KnowledgeError) else "invalid_vector_index"
        return {**fallback, "status": "degraded", "warnings": [*fallback["warnings"], "Semantic retrieval unavailable: " + reason]}
