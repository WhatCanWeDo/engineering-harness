# Knowledge MVP-2: открытый контракт

Draft 2026-11-03. Дополнение к knowledge-mvp.md; реализация начинается после MVP1 gate.

## Семантика и интерфейсы

`KnowledgeStore(path, embedder=None)` принимает опциональный локальный provider: `model_id` (непустая строка, включает версию модели), `dimensions` (положительный int), `embed(texts, kind='document'|'query')` → список векторов в том же порядке. Synthetic providers допустимы только в unit tests и не доказывают смысловой поиск. Рабочий backend — FastEmbed/ONNX multilingual MiniLM, явная установка модели; ordinary search/index не скачивают модель и не отправляют тексты наружу.

`index_sync(limit=100)` детерминированно индексирует до limit текущих active не-hypothesis записей, которым недостаёт актуального вектора выбранной модели. Сохраняет vectors по model_id/entry_id/revision/content_hash. Проверяет количество, dimension, конечность и ненулевую норму; нормализует векторы. Ошибка provider/невалидные vectors не должна частично коммитить batch. Повтор использует готовые vectors. API возвращает status ready/lagging/unavailable, indexed, remaining, model_id, watermark. Индекс производный, SQLite revisions остаются источником истины. Рестарт может продолжить index_sync. Более новая revision не получает вектор от старой. Разные модели/размерности не смешиваются.

`index_status()` возвращает те же ready/lagging/unavailable, remaining, model_id, watermark без вызова embeddings. Watermark — seq последней полностью синхронизированной совокупности current revisions, а не номер последней задачи. Без provider — unavailable. Нет активных записей → ready.

`search(..., mode='lexical'|'semantic'|'hybrid')`. Lexical — прежний API без вызовов embedder. Semantic — cosine similarity, hybrid — Reciprocal Rank Fusion (k=60, равные веса двух рангов, каждый максимум 30), exact ID/ref/symbol имеет приоритет. Все retrieval modes используют прежние scope/role/cutoff/state/applicability ограничения. Если нет полной актуальной индексации доступного корпусa, нет provider либо provider падает, возвращается lexical fallback с mode='lexical', status='degraded' и warnings, а не успешная имитация semantic. Foreign/после-cutoff записи не включаются в выдачу/пакет; векторы не отменяют policy.

Query vectors кэшируются по model_id, dimension и hash(query), в отдельном project namespace. Cache сохраняется между процессами, не хранит сырой query. Новая модель не использует старые vectors. Пустой query не вызывает provider. При одинаковых scores порядок стабилен по entry_id. Независимо от кеша retrieval повторно проверяет актуальность записей.

`prepare_context(...,mode=...)` и `scout_brief(...,mode=...)` используют тот же search. Старые defaults lexical сохраняются. CLI knowledge search/context prepare/context scout имеют --mode, `knowledge index --limit N`, `knowledge index-status`. Отсутствующий provider даёт понятный fallback, не traceback. `--semantic-model PATH` перед командой загружает явно подготовленную model bundle. `model-setup --output DIR` — единственная команда, которой разрешено скачать публичные веса; no data upload. Bundle содержит provenance, file hashes и provider identity; изменение bundle не смешивается со старым индексом.

## Заранее фиксируемая оценка

Отдельный автор до реализации готовит public behavior tests (synthetic deterministic vectors) и небольшой development corpus + queries/qrels на русском/английском (включая cross-language, exact symbol, отвлекающие документы). JSON benchmark format: {documents:[{id,title,claim}],queries:[{id,text,relevant:[docid],category}]}. Не подгонять baseline/queries после измерений. Реальный backend сравнивается с lexical при одинаковом corpus/task cutoff: Recall@3 и MRR@3, per-query ranking, время и идентичность модели/корпуса. Это smoke/development benchmark, не доказательство общего роста task success. Честно показать регрессии, даже если hybrid не выиграл.

Gate MVP2: public+post-hoc adversarial checks, предыдущие regression suites, реальный локальный embedding run и сохранённые benchmark results. Private unavailable. Поведение native agents не считается проверенным только по CLI unit tests.
