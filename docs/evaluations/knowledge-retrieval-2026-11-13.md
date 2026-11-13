Retrieval study — post_hoc public evaluation, 2026-11-13. Baseline commit 58567560b98b750de70258213dd91a8c1ff656d5. Product source was unchanged. Personal knowledge contents were neither read nor modified. Full raw outputs remain beside this summary.

124 existing tests passed across the initial run (121 pass, three preview checks blocked by sandbox loopback) and an unchanged permitted rerun (3/3). Five new post_hoc freshness tests passed: 14-day boundary, packet expiry, file drift, upstream retraction, snapshot/current revocation, and delayed reconciliation. No confirmed product bug. This is not proof of correctness.

The independent corpus has 100 documents and 32 queries (28 answerable, including six multi-fact; four no-answer). Corpus and qrels were frozen before retrieval: `0befae5f70aaf463a7b0cfce16f8875833962f27a757204c058a66788386f782`. A fresh author produced 102 transformation strings from query-only input. A different fresh native agent reranked 73 deduplicated candidate packets without qrels, retrieval scores/order, or method labels.

Quality below is on the 28 answerable questions. No-answer abstention is reported separately; returning unrelated candidates is an observed retrieval behavior, not a violation of an abstention requirement in the existing Core contract.

| Method | Recall@5 | MRR@5 | nDCG@5 | Multi-fact full coverage | No-answer abstention |
|---|---:|---:|---:|---:|---:|
| lexical | 0.6964 | 0.6250 | 0.6337 | 0.6667 | 2/4 |
| semantic | 0.9643 | 0.9357 | 0.9338 | 1.0000 | 0/4 |
| hybrid | 0.9464 | 0.9643 | 0.9476 | 0.8333 | 0/4 |
| semantic + original + rewrite | 1.0000 | 0.9583 | 0.9632 | 1.0000 | 0/4 |
| semantic + original + decomposition | 0.9286 | 0.9107 | 0.9031 | 1.0000 | 0/4 |
| semantic + original + hyde | 1.0000 | 0.9583 | 0.9632 | 1.0000 | 0/4 |
| semantic + native rerank/filter | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 4/4 |
| hybrid + native rerank/filter | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 4/4 |
| combined_semantic + native rerank/filter | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 4/4 |

All three top20 candidate pools had Recall@20 = 1.0. Combined means fixed semantic RRF over original + rewrite + decomposition, not a selection of the best method using labels. Before reranking it had Recall@5=1.0, MRR@5=0.9268, nDCG@5=0.9411. Native reranking includes relevance filtering and abstention with variable-length output; it is not a pure cross-encoder sorter. Production model identity, automated reranking latency, token cost and generation cost were not measured. Perfect results on this easy, small authored corpus are not evidence of general reliability.

Semantic + rewrite improved Recall on 1/28 queries, tied 27, lost 0; bootstrap mean-delta interval [0, 0.1071]. Semantic decomposition lost Recall on 1/28 and improved none. Semantic + native rerank improved nDCG on 5/28, tied 23, lost 0; exploratory paired bootstrap mean delta 0.0662, interval [0.0057, 0.1572]. Confidence intervals resample this authored set only; there is no held-out task-success claim. Full paired values and regressions: `paired-results.json`.

HyDE used the query embedding path in the retrieval adapter. A direct follow-up compared all 32 frozen hypothetical texts through query and document paths: maximum absolute vector difference 0, minimum cosine 0.9999999999999999. This is document-embedding equivalence for these texts and this exact MiniLM bundle, not a universal adapter guarantee. Hypothetical text is never stored as factual knowledge.

The committed development set (18 documents, 14 queries) gave Recall@5 lexical 0.5000, semantic 1.0000, hybrid 0.6429; nDCG 0.4736/1.0000/0.6165. Hybrid fusion regressed cross-language retrieval on this set. It should not replace semantic by default based on these measurements.

Latency uses sequential runs, randomized query/mode ordering, model/query-cache warm where indicated, and three repeats over the same eight queries for matched scaling. p95 is nearest-rank. These corpora have no declared source-file dependencies, so IO-heavy freshness checks remain unmeasured.

| Matched warm search | 100 docs median / p95 ms | 1000 docs median / p95 ms |
|---|---:|---:|
| lexical | 1.27 / 1.63 | 10.79 / 19.97 |
| semantic | 16.07 / 16.61 | 161.13 / 177.68 |
| hybrid | 17.71 / 18.81 | 172.88 / 188.64 |

On the full 32-query authored set, warm semantic median/p95 was 15.93/17.03ms; warm-model query-cache miss was 22.75/25.70ms. Fresh CLI process with persisted query vector: semantic median 199.85ms. Fresh process with that vector removed: 1223.11ms. Each cold-process condition has only three samples, uses warm OS filesystem cache, and includes model bundle integrity validation; it is not cold disk latency.

Warm semantic retrieval-only overhead, top30 per branch plus RRF: original 17.02ms median, rewrite 35.00ms, decomposition 34.93ms (p95 54.74), HyDE 35.25ms, combined 53.07ms (p95 73.70). Native generation and reranking time are excluded.

At 1000 documents cProfile attributed 155/327ms to repeated vector normalization, about 80ms to JSON parsing, and 42ms to Python dot-product accumulation. These times include profiler overhead and overlap; use unprofiled latency for the service number. Lexical profile spent 13/24ms in eligibility, including freshness. Semantic selected 35 SQL statements; hybrid selected 100 in the representative 1000-entry profile. Full trace counts also include FTS internals.

An isolated 1000×384 kernel test used 20 repetitions: Python JSON decode + normalization + dot median 128.96ms versus cached contiguous float64 NumPy matrix-vector median 0.0691ms. Building that matrix cost 123.81ms and 3,072,000 bytes. Top20 matched; max score delta 4.2e-17. This combines caching and vectorized arithmetic and is NOT an end-to-end speedup or a language comparison. It excludes policy, current revocation, eligibility, invalidation, SQL and ranking/fusion.

Measured opportunities, in priority order: preserve semantic as current baseline; evaluate a reused validated matrix and vectorized scoring with explicit revision/model invalidation plus unchanged freshness/current-revocation rechecks; avoid repeated eligible-record scans and repeated lexical work in semantic/hybrid; measure a persistent model worker versus cold CLI lifecycle; evaluate selective rewrite or top20 native rerank/filter on a new held-out engineering task set. Decomposition and hybrid fusion need routing/weight experiments, not unconditional rollout. The data does not justify a Rust rewrite; first test end-to-end Python/NumPy caching with behavior-parity tests.

Evaluation harness audit: v1 exact-result pin was selected using the dataset category. It was corrected to observable literal query equality with symbols/current IDs/refs; all transformation rankings and paired metrics reproduced exactly, and candidate packets/mapping were byte-identical. Old outputs are retained in `evaluation-v1`; `evaluation-harness-parity.json` binds the comparison. The frozen labels, transformations and native reranker output did not change.

Peak observed process RSS was 1,300,774,912 bytes in the 1000-entry run; 5000 was skipped conservatively. New test data and outputs use only this public scope. No downloads or external API calls. UUID-generated store IDs mean a fresh import can change exact tie ordering; mappings bind the recorded run. Benchmarks require fresh dataset subdirectories on reproduction.

Reproduction commands are stored per executed check in `*-check.json`, including argv/cwd/exit/duration/output. Use `/Users/mshekhunov/engineering-harness/.venv/bin/python` for every script. Start with `-m unittest discover -s tests -v`; then run `test_freshness_posthoc.py`, `benchmark.py --dataset authored`, `--dataset committed`, `--dataset scale1000`, `--dataset transforms`, followed by the isolated measurement/aggregation scripts. `worker-result.json` is the machine-readable result; `suite-manifest.json` and `code-manifest.json` record file digests.
