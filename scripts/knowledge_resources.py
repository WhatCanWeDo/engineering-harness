#!/usr/bin/env python3
"""Local installation readiness and resource probe; no suites, no external calls."""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import resource
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def size(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


def peak_rss():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if sys.platform == 'darwin' else value * 1024


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path)
    args = parser.parse_args()
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE VIRTUAL TABLE probe USING fts5(text)')
    result = {'status': 'ready', 'platform': platform.platform(), 'machine': platform.machine(),
              'python': sys.version, 'logical_cpus': os.cpu_count(), 'sqlite': sqlite3.sqlite_version,
              'fts5': True, 'venv_file_bytes': size(Path(sys.prefix)), 'gpu_required': False}
    if args.model:
        from harness.embeddings import LocalEmbedder
        started = time.perf_counter()
        provider = LocalEmbedder(args.model)
        result['bundle_validation_seconds'] = time.perf_counter() - started
        started = time.perf_counter()
        vectors = provider.embed(['Как восстановить очередь после сбоя?', 'Recover a durable queue after a crash.'], kind='query')
        result['cold_query_seconds'] = time.perf_counter() - started
        if len(vectors) != 2 or any(len(v) != 384 or not all(math.isfinite(x) for x in v) or not any(v) for v in vectors):
            raise ValueError('Embedding readiness failed')
        result['query_peak_rss_bytes'] = peak_rss()
        started = time.perf_counter()
        sample = 'An immutable source reference preserves evidence across task retries. ' * 6
        vectors = provider.embed([sample] * 32)
        result['batch32_seconds'] = time.perf_counter() - started
        if len(vectors) != 32:
            raise ValueError('Batch readiness failed')
        result.update(model_id=provider.model_id, dimensions=provider.dimensions, cpu_threads=2,
                      model_file_bytes=size(args.model), workload=f'2 short RU/EN queries, then 32 documents of {len(sample.split())} words each; batch_size=32',
                      batch_peak_rss_bytes=peak_rss())
    result['process_peak_rss_bytes'] = peak_rss()
    result['rss_scope'] = 'Peak RSS of this process including Python/runtime/model; not whole-system RAM or a guaranteed worst-case limit.'
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
