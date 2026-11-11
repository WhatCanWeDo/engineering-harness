# Проверка Knowledge Freshness — 2026-11-11

Существующий набор: `.venv/bin/python -m unittest discover -s tests -p 'test_knowledge*.py' -q` — **74 tests, OK**. Новая test suite не создавалась. `git diff --check` — без ошибок.

Два дополнительных API-сценария выполнены на отдельных временных SQLite с фиксированным UTC clock. Semantic provider синтетический из существующего набора; это проверка фильтрации, не качества embeddings. Рабочая база не использовалась для тестовых записей.

## TTL, повтор и изменение источника

```json
{
  "initial_hits": 1,
  "packet_expires_at": "2026-11-15T00:00:00+00:00",
  "just_before_deadline_hits": 1,
  "at_deadline_hits": 0,
  "expired_packet": "not_found",
  "maintenance_due": 1,
  "renew": "committed",
  "old_snapshot_hits": 0,
  "new_snapshot_hits": 1,
  "renewed_expires_at": "2026-11-29T00:00:00+00:00",
  "repeat_old_revision": "conflict",
  "source_drift_hits": 0,
  "source_drift_reasons": [
    "source_changed"
  ],
  "source_drift_export_state": "stale",
  "stale_hash_renewal": "conflict",
  "revision_after_rejected_renewal": 2,
  "deferred_due": 0,
  "due_after_next_14_days": 1,
  "revision_history_count": 3,
  "legacy_anchor": "2026-11-15T00:00:00+00:00"
}
```

## Зависимости и semantic/hybrid

```json
{
  "dependent_packet_deadline": "2026-11-15T00:00:00+00:00",
  "semantic_before_expiry": 2,
  "semantic_at_upstream_expiry": 0,
  "hybrid_at_upstream_expiry": 0,
  "renew_before_upstream": "conflict",
  "dependent_after_upstream_revision": "stale",
  "dependent_after_review": "current",
  "indirect_cycle": "validation",
  "semantic_after_renewals": 2,
  "old_snapshot_after_renewals": 0
}
```

В сценариях истечение, source drift, stale hash, revision conflict, сохранение истории и порядок upstream → downstream дали ожидаемое поведение. После renew нужен новый task snapshot. Native Maintenance Curator описан в skill; автономный таймер не установлен, полномасштабная оценка семантических решений агента не выполнялась.
