# RFC 003 — Knowledge & Context Layer

Статус: **Draft v0.1**, 2026-11-03. Архитектурный дизайн; локальные MVP1/MVP2 реализованы в ограниченном scope. Актуальные интерфейсы: [MVP1](../contracts/knowledge-mvp.md), [MVP2](../contracts/knowledge-mvp2.md); [эксплуатация](../knowledge/operations.md). Остальные компоненты этого RFC остаются проектируемыми.

## 1. Решение и подтверждённые предпочтения

Создать общий локальный Knowledge Core: версионированные записи с evidence, быстрый поиск и отдельные агенты подготовки контекста и обновления знаний. Codex/Claude сохраняют нативные loops. CLI и опциональный MCP вызывают одно ядро.

Пользователь выбрал:

- После каждой задачи автоматически сохранять evidence и кандидатов в знания. Спорные обобщения требуют подтверждения.
- Между проектами переносить общие инженерные знания; детали проекта доступны только внутри него.
- Перед задачей отдельный агент собирает минимальную выжимку для разработчика и автора тестов. Генерация самих тестов остаётся у другого агента согласно RFC 002.

Память делает полезный опыт доступным, но само её увеличение не доказывает улучшения harness. Изменения skills, policies, permissions и критериев приёмки не применяются автоматически из записей памяти.

## 2. Компоненты и полномочия

| Компонент | Делает | Не делает |
|---|---|---|
| Native adapter | Передаёт task boundary, task brief и разрешённые роли; доставляет пакеты | Не содержит логики знаний и не обещает гарантии недоступных hooks |
| Knowledge Core | Версии, ACL, scope, транзакции, evidence refs, freshness, retrieval | Не принимает текст модели за новое разрешение |
| Context Scout | В отдельном свежем контексте формулирует запросы, выбирает полезное и предлагает краткий пакет | Не читает всю базу/историю разработки и не меняет знания |
| Context compiler | Проверяет разрешённые record revisions, бюджет, структуру и citations; формирует окончательный пакет | Не доказывает автоматически смысловую корректность LLM-пересказа |
| Developer / Test author | Получают короткий пакет под роль; могут запросить уточнение по record ID | Не получают рабочий transcript Scout и приватный индекс |
| Knowledge Curator | После задачи извлекает новые наблюдения, предлагает merge/supersede и вопросы | Не публикует спорные обобщения как установленные факты |
| Commit gate | Проверяет связи/evidence, типы и политику публикации; записывает revision/event/outbox | Не подменяет доказательство проверкой JSON или мнением второй LLM |
| Protected evaluator | В собственном контуре хранит private знания и выпускает разрешённые disclosures | Не загружает закрытый корпус в обычный Scout |

Для обычных ролей Scout может один раз собрать разрешённое пересечение знаний. Разные role packs собираются с отдельными фильтрами. Если одному контексту требуются более широкие права, запускается новый Scout; читать private и затем «забыть» его перед публичным summary нельзя. Права задаёт доверенный task binding, не свободный аргумент `--role`.

## 3. Каноническое хранение

Первый прототип — локальная SQLite: записи, immutable revisions, current pointers, evidence links, task events, packet receipts и durable outbox. FTS5 — производный поисковый индекс; vector index добавляется по результатам оценки. Markdown/JSON export — читаемая проекция для review/backup, не второй редактируемый источник истины. Изменения проекции возвращаются через проверяемый import proposal. Obsidian/другие заметки можно подключить позже как источники или проекции с provenance.

FTS5 предоставляет полнотекстовый поиск и BM25. Для смешанных русских/английских записей стартуем с unicode tokenizer, отдельных полей symbols/paths/tags и проверенного словаря терминов. Английский Porter stemmer не считать русской морфологией. [SQLite FTS5](https://www.sqlite.org/fts5.html).

WAL допускает чтение параллельно записи, но writer только один, а shared DB не предназначена для сетевой файловой системы. Поэтому короткие транзакции, single-writer queue/retry, backup API; не синхронизировать живой SQLite-файл через облачный диск. Для нескольких машин — один авторитетный endpoint или позднее журнал репликации, не last-write-wins копирование DB. [SQLite WAL](https://www.sqlite.org/wal.html).

Бинарные artifacts остаются в Artifact Registry/object storage. Здесь — неизменяемые ссылки, digest, provenance и разрешённые excerpts. Raw transcript по умолчанию не индексируется. Секреты и private suites вообще не загружаются в обычную базу. Проверка секретов помогает, но сама по себе не обеспечивает отсутствие утечек.

## 4. Контракты данных

**KnowledgeEntry revision:**

```json
{
  "schema_version": 1,
  "entry_id": "K-042",
  "revision": 3,
  "kind": "observation",
  "state": "active",
  "scope": {"kind": "project", "project_id": "cache-service"},
  "visibility": "project",
  "claim": "В run-17 чтение на границе now == expires_at вернуло устаревшую запись.",
  "applies_to": {"spec_ref": "spec@2", "symbols": ["Cache.get"], "environment_ref": "env:..."},
  "evidence_refs": ["evidence:public-regression@sha256:..."],
  "trust_basis": "tool_observation",
  "observed_at": "2026-11-03T16:00:00Z",
  "recorded_at": "2026-11-03T16:02:00Z",
  "last_checked_at": "2026-11-03T16:02:00Z",
  "review_after": null,
  "relations": [{"kind": "supersedes", "ref": "K-042@2"}],
  "origin_task": "task-17",
  "origin_role": "public-test-author"
}
```

Пример иллюстративный. Разделять «spec требует X» и «run показал Y»: evidence подтверждает наблюдение о проверке, а не создаёт новое требование. Варианты kind: decision, observation, hypothesis, negative_result, procedure, preference. State: candidate, active, stale, disputed, superseded, retracted. Тип, lifecycle и доверие к evidence — разные оси; произвольный float confidence их не заменяет.

**ContextRequest:** task_id, task/spec snapshot, project bindings, principal, role, phase, allowed baseline, knowledge cutoff, queries, token budget, required refs. **ContextPacket:** packet_id, snapshot_id, policy revision, role/phase, source entry revisions и evidence refs, компактные claims, applicability, caveats/conflicts, omitted_by_budget, token count/method, retrieval diagnostics, expires/invalidation conditions. Все IDs ниже в визуализациях синтетические.

**TaskOutcome:** task/run/candidate IDs, actual status (success/failure/interrupted), changed paths, artifact/evidence manifests, user decisions, public findings, packet refs, что осталось непроверенным. Не полная переписка. **KnowledgeProposal:** additions/merge/supersede, basis, scope, reasons, expected_base_revision, idempotency key. **CommitReceipt:** persisted events/revisions, accepted candidates, pending approvals, index state; no_change является нормальным результатом.

## 5. Подготовка контекста до задачи

1. Adapter создаёт task binding. Открытый контракт и обязательные project instructions читаются напрямую; критические правила не зависят от попадания в top-k RAG.
2. Фиксируется knowledge snapshot и cutoff стадии. До генерации initial tests исключаются новые сведения о целевом решении; разрешённый baseline и исторические публичные regression остаются с честным provenance.
3. Новый Scout получает минимальный brief, project IDs, роль, бюджет и read-only Knowledge API. История разработчика не наследуется. По умолчанию максимум 3 поисковых запроса и 8 источников — настраиваемые стартовые значения.
4. Core ограничивает доступный corpus **до** поиска и извлечения текста. Фильтры проекта, прав, state, applicability и стадии применяются до передачи модели, включая reranker. Защищённый корпус физически отделён. Cache key включает principal/permissions revision, project, role, phase, task/spec, knowledge snapshot, budget и model/index versions.
5. Scout получает ограниченные snippets с source IDs, запрашивает нужные records, предлагает пакет. Compiler сверяет revisions, разрешения и размер. Каждое утверждение имеет ссылку; дополнительные допущения возвращаются как вопросы. В MVP предпочтительны extractive claims с минимальным перефразированием.
6. Разработчик и автор тестов получают разные краткие пакеты из одной модели знаний. Рабочий transcript Scout не передаётся. Расширение — точечный `context expand <ref>` под теми же правами; первоначальный пакет остаётся минимальным.

Стартовые бюджеты: developer 1200 токенов, public-test-author 900, adversarial 1200; общий контекст учитывается внутри бюджета каждого потребителя. Размер считается tokenizer потребителя; без него используется явно помеченная оценка. Это предложения, не измеренные оптимумы. Не обрезать обязательные условия молча: required_context_overflow требует большего бюджета или явного изменения scope. Empty result ≠ доказательство отсутствия знания; вернуть empty/degraded и ограничения поиска.

Scout не может гарантировать правильность любого LLM-summary. Compiler обнаруживает отсутствующие sources и неверные роли, но не все ошибки интерпретации. Поэтому короткие исходные claims, citations, eval fidelity и возможность прочитать оригинал обязательны.

## 6. Поиск: сначала полезный baseline, затем hybrid

MVP: exact IDs/symbols/paths + FTS5/BM25 по разрешённым active revisions; отдельный поиск candidate/hypothesis только по явному режиму. Важные конфликты возвращаются как предупреждения, а не смешиваются в один «факт».

После baseline: lexical top-30 и semantic top-30 по тому же разрешённому corpus → union/dedup → Reciprocal Rank Fusion → применимость/актуальность/разнообразие источников → при оправданной цене rerank → до 8 источников → budgeted packet. Это стартовые значения, не фиксированная обязательная глубина. RRF объединяет позиции в выдачах; семантическое сходство не подтверждает истинность. [Hybrid search и RRF](https://qdrant.tech/documentation/search-tuning/hybrid-search/).

Embeddings по умолчанию локальны, модель и размерность версионируются; внешний embedding/reranking provider подключается только для разрешённого профиля данных. Смена embedding model создаёт новый индекс, не меняет знания. ANN — сменный backend; для маленького корпуса можно начать с exact similarity scan. Qdrant — пример возможной будущей интеграции, не выбранная обязательная зависимость.

FTS и canonical revision публикуются в одной транзакции. Vector index обновляется из durable outbox и может отставать. У каждой выдачи есть index watermark; canonical recheck перед export исключает retired/deleted records даже при старом индексе. При отставании — lexical fallback или явный degraded, а не молчаливый пропуск только что внесённых знаний.

## 7. Кто что получает

| Получатель | Полезный контекст | Исключения |
|---|---|---|
| Developer | Требования, решения, публичные известные баги, применимые процедуры и ограничения окружения | Private suite/oracle/seeds/raw logs; детали других проектов |
| Public test author до решения | Контракт, интерфейсы, допуски, старые публичные bug classes, разрешённый baseline | Целевое решение и новые conclusions о нём после cutoff; гипотезы разработчика из transcript |
| Adversarial после решения | То же открытое ядро + frozen candidate и разрешённые observations о нём | Закрытые тесты и воспоминания private-автора |
| Private test author | Отдельный Scout/evaluator с собственным защищённым store | Вывод private-content в обычные packets/общую память |

Создание tests до решения требует зафиксировать пакет и время публикации suite; один фильтр по created_at записи не доказывает независимость. Важны observed_at, origin_task, source snapshot, phase и доступ автора. Public packet может знать старый baseline, но это указывается как раскрытая реализация baseline, не «полная слепота».

При private failure evaluator выпускает разрешённый минимальный reproducer; он становится публичной regression-записью с private-origin и release receipt. Остальной suite, связанные seeds и raw logs остаются закрыты. Summary наследует ограничения своих источников; пересказ LLM не является declassification.

## 8. Обновление после каждой задачи

1. Adapter фиксирует TaskOutcome независимо от успеха продукта. В одной короткой транзакции пишет task event и outbox event; только после durable receipt показывает `knowledge_update: queued`.
2. Curator запускается отдельным свежим агентом с разрешёнными outcomes/artifacts и точечным поиском возможных дубликатов. Он не получает весь transcript и не просматривает private backend.
3. Curator предлагает атомарные записи: что наблюдали, при каких условиях, источник, scope, отрицательный результат, новое решение или явная гипотеза. При отсутствии нового знания — no_change с причиной; нет квоты на записи после каждой задачи.
4. Gate проверяет schema, source accessibility, hashes, тип evidence, права, secret policy, совпадение base revision и duplicates. Проверка hash не доказывает истинность вывода. Локальный tool output подтверждает узкое наблюдение в данном run, а не внешнюю доверенную аттестацию.
5. Evidence и candidates сохраняются автоматически. Автоматически active допустим для узкого source-backed observation или дословно зафиксированного решения пользователя. Причинное/универсальное обобщение, конфликт или изменение нормы остаётся candidate/disputed до подтверждения. Второй LLM не получает право автоматически объявлять такие записи verified.
6. Commit пишет immutable revision + audit event + новый index outbox; receipt содержит accepted/pending/no_change. Конкурентное изменение base revision вызывает rebase/review, не перезапись. Idempotency key связывает task/run/outcome digest/extractor version, повтор не создаёт дубль.

В Interactive Mode это протокол native adapter и напоминание в project instructions. Нельзя гарантировать вызов после каждого свободного сообщения одним skill/hook. В управляемых task boundaries `task finish` обязан durable-queue outcome; аварийный выход оставляет interrupted/pending, reconcile продолжает незавершённые jobs. Сбой БД = update_failed, а не queued. Успех кода и состояние обновления знаний показываются отдельно. Не вводить скрытый daemon как обязательную зависимость: обработка очереди при завершении/следующем старте или явном `knowledge reconcile`, service позже.

## 9. Scope, устаревание и конфликты

Namespaces: personal-general, project:<stable-ID>, protected-evaluator:<ID>. Scope описывает применимость, ACL — доступ; это не одно поле. Repo identity не равна текущему filesystem path, а ветка/commit/environment входят в applies_to.

Детали проекта остаются project-scoped по умолчанию. Перенос общего метода создаёт **новую** general-запись с применимостью и разрешённым evidence/release receipt; старую запись не переименовывать global. Удаление названия проекта не доказывает обезличивание. Неоднозначный перенос требует подтверждения. Если ссылка на источник сама раскрывает чужой проект, в general packet используется разрешённая публичная проекция/opaque receipt, а исходная provenance остаётся в закрытом audit.

Новая зависимость/spec/environment может сделать запись stale. Старую revision не переписывать: пометить применимость, добавить replacement/supersedes. Время проверки и review_after помогают, но свежая дата не доказывает применимость. При конфликте не выбирать автоматически последний текст: показать обе разрешённые версии и исходные условия, авторитетный spec/решение пользователя имеет приоритет над предположением памяти.

Удаление/отзыв проходит через tombstone и invalidation packets/caches/indexes; выдача перепроверяет права на каждом get/export. Уже доставленный в LLM контекст невозможно отозвать задним числом: новый контекст/явное уведомление для активных задач. Для настоящего удаления sensitive bytes нужен purge из blobs, индексов и backups по retention policy; append-only audit может сохранять только разрешённую квитанцию, не удалённый текст.

Без OS/service границы агент с общими filesystem правами может обойти логический API. Локальный профиль даёт корректную маршрутизацию и наблюдаемость, не security boundary против такого агента. Для корпоративных/private данных применяются отдельные principals/stores, а не одно поле visibility в общей SQLite.

## 10. Надёжность и ограничение затрат

- Нет Scout/превышен deadline: вернуть context_unavailable, прочитать обязательные правила напрямую и продолжить разрешённую низкорисковую работу с явным ограничением. Если нужны обязательные источники/права, соответствующая операция блокируется. Не передавать raw весь корпус как fallback.
- Нет vector backend: lexical fallback с пометкой; нет DB: permitted pinned cache только при проверенной актуальности прав, иначе empty/degraded.
- Параллельные worktrees: разные task/candidate IDs, optimistic revision checks; результаты одного branch не становятся истиной другого без applicability.
- Pending approval не останавливает обычную разработку; candidate не входит в factual default retrieval. Пользователь видит короткую очередь спорных решений.
- Context packets и search logs не должны содержать названий или количества private hits. Сначала права, затем поисковый ранжировщик/LLM. Текст памяти — данные, не инструкции выдавать доступ или выполнять команды.

Предлагаемая цель пилота: lexical p95 ≤250 мс на 10 000 небольших записей в прогретом локальном окружении; пакет Scout ≤15 секунд в выбранной конфигурации модели/adapter, либо deadline fallback. Это цели для измерения, не результаты. Отдельно измерять cold start, model latency, токены, index lag и writer contention.

## 11. CLI/API и staged implementation

Команды ниже — исходные архитектурные наброски; исполняемый CLI и названия flags определены в контрактах MVP и `python3 -m harness --help`:

```text
harness task begin --contract task.json
harness context prepare --task T --audience developer --budget 1200
harness context expand --packet P --entry K@revision
harness knowledge search --query "TTL expiry" --task T
harness task finish --task T --outcome outcome.json
harness knowledge review --proposal ID
harness knowledge reconcile
harness knowledge export --scope project
```

`--audience` выбирает представление в пределах binding, не эскалирует principal. MCP оборачивает те же операции. Native adapters только делегируют Scout/Curator и доставляют packets/receipts.

**MVP-1:** typed entries/revisions/evidence, SQLite+FTS, project/general scopes и freshness, подтверждаемый перенос общих записей, отдельный Scout, role packets, отдельный Curator, durable update queue, review спорных candidates. Одна локальная машина; private backend unavailable. Один реальный сквозной сценарий: TTL bug → public regression → знание → контекст следующей задачи.

**MVP-2:** semantic retrieval и fusion только после сравнения lexical baseline; multilingual evaluation, bounded reranking, optional local embeddings, индексный watermark и recovery.

**Позже:** защищённый evaluator store, remote endpoint, расширенные policies межпроектной публикации, интеграция существующей базы заметок/trackers, многомашинная репликация. Не строить универсальный граф знаний или отдельную UI-платформу до подтверждённой необходимости.

## 12. Как доказать пользу

На замороженной выборке задач сравнить no-memory, lexical, hybrid и role-aware packets при одинаковом agent/model/task budget. Зафиксировать knowledge snapshot ДО eval run; не писать выводы eval в следующий независимый holdout. Изменения corpus, retriever, Scout prompt и embedding version оцениваются отдельно.

Метрики: recall нужных источников, точность citations, неподдержанные claims, доля stale/conflicting данных, prompt budget, retrieval/Scout latency, task success по независимым проверкам, повторение известных дефектов, review time человека, стоимость Curator/Scout и backlog. Click/retrieval frequency не является доказательством истинности или пользы записи.

Приёмочные сценарии: cross-project/private leakage, generation cutoffs для initial tests, source drift, contradictory records, shared-permission limitations, crash/retry/dedup, concurrent revision conflict, stale vector index, revoked ACL/cache, no-new-knowledge task, malformed evidence, failed/interrupted task и mandatory budget overflow. Это план оценки; такие испытания в данном дизайне не выполнены.

## 13. Открытые решения

До реализации уточнить критерии narrow observation для auto-active, формат минимального evidence, модель локальных embeddings при необходимости и identity binding native adapters. Подтверждённые пользователем настройки раздела 1 уже действуют как требования дизайна; остальные численные defaults и технологии — предложения для пилота.


## 14. Установка и ресурсный профиль локальной модели

Уточнение реализации, 2026-11-03. Для semantic retrieval используется отдельная embedding-модель, multilingual MiniLM в quantized ONNX через FastEmbed. Это encoder для 384-мерных vectors, не замена coding agent/его LLM. Core без semantic режима работает через SQLite FTS5 без модели.

Новый checkout устанавливается `sh scripts/setup.sh`: локальный uv при необходимости → managed Python 3.12 → locked dependencies в .venv → pinned public model bundle → offline readiness/resource probe → local profile. Повторный запуск переиспользует готовый bundle; `--lexical-only` позволяет обойтись без него. Details: [установка и ресурсы](../knowledge/setup.md).

Ресурсный ориентир: CPU backend с 2 inference threads, GPU не нужен; весь bundle ~255 MiB, .venv ~194 MiB по сумме размеров файлов на macOS arm64. На первую установку рекомендуется 3 GiB свободного диска плюс место под knowledge/evidence. Локальный probe показал ~1.2 GiB peak RSS процесса; разумно резервировать ~2 GiB доступной RAM на embedding-процесс. Эти значения не являются универсальным minimum/worst-case: workload, OS, runtime и параллелизм меняют расход. Setup сохраняет фактический замер нового устройства. Для рабочего ноутбука 8 GiB RAM — ориентир старта, 16 GiB удобнее с IDE/браузером/agents.

Установка требует сети для общедоступных dependencies/weights. Последующий inference локальный. База знаний не переносится автоматически на новое устройство: нужен отдельный SQLite backup/restore. Bootstrap предусмотрен для macOS/Linux/WSL; live validation выполнена на текущем macOS arm64. Native Windows installer пока не предоставлен.

## Дополнение реализации: automatic subprojects, 2026-11-03

По запросу пользователя реализована автоматическая организация подпроектов внутри одной базы. Источники: repository components, повторяющиеся tags active проектных записей и уточнение existing Scout. Это мягкие affiliations, не ACL и не строгий applicability filter. Task catalog/routing фиксируются до context packet; новые группы не переносятся в старые snapshots. [Контракт и ограничения](../../skills/knowledge-cycle/references/subprojects.md). Общий статус исходного RFC этим дополнением не меняется.
