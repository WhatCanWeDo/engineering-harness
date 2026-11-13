# Улучшение поиска Knowledge Core: качество, скорость и выбор реализации
ML Task Spec v1 · knowledge-retrieval-improvements · revision 1 · DRAFT
SHA-256: 79554f94002ab8327a14fdc4616b8c34642984834aeb6f4310fced3907f15262

Результат исследования: первым пилотом предлагается semantic top-20 → LLM reranking/фильтрация → top-5, затем условный query rewriting. На 100 synthetic документах и 28 answerable запросах reranking поднял Recall@5 с 96.43% до 100%, nDCG@5 с 93.38% до 100%; 4/4 no-answer случая отклонены. Rewriting и HyDE дали одинаковый Recall@5=100%, decomposition при общем включении снизила его до 92.86%. Это небольшой development эксперимент, не доказательство production выигрыша. Оптимизацию начать с представления векторов и повторных вычислений; полный Rust rewrite пока не обоснован. Рабочее ядро не изменялось.

## Исходный запрос
подумай какие из этих техник добавить, чтобы улучшить поиск. Так же предлагаю оптимизировать базу знаний,можно переписать на rust, но только проведи все необходимые тесты

## 01 · Задача и ожидаемый результат

[Из запроса] Получить обоснованный порядок улучшений: качество поиска измеряется отдельно от скорости, а успех исследования не требует победы каждой новой техники. Пользователь получает результаты, воспроизводимые команды и следующий минимальный этап.
Источники: U1, U2, U3
Пробелы: 

## 02 · Контекст и границы системы

[По источнику] Сейчас task.goal напрямую поступает в lexical/semantic/hybrid. Scout получает до 12 найденных кандидатов и выбирает до 8; это уже содержательный отбор после поиска, но он не генерирует план retrieval и не реализует формально измеренный reranker.
Источники: C1, C2
Пробелы: 

[По источнику] Текущий runtime установки использует semantic. Локальная база содержит всего 34 записи. Масштабные synthetic measurements нужны как оценка роста, а не как описание текущей нагрузки.
Источники: E2, C4
Пробелы: 

[По источнику] В историческом пакете указано разделение project DB; у текущего checkout отсутствует project profile, поэтому использован существующий legacy store с известным project ID. Инициализация новой БД и перенос данных не выполнялись.
Источники: K1
Пробелы: 

## 03 · Scope и non-goals

[Из запроса] В этом проходе: read-only анализ исходников/метаданных, публичные тесты на временных базах, blind transformations и rerank на фиксированных данных, результаты и план. Реализация оптимизаций, миграция живой БД и переход на Rust отложены согласно выбранному scope.
Источники: U2
Пробелы: 

[Предложение] Не нужны новая vector DB, собственный agent loop, внешний inference service и загрузка private knowledge в сеть. Будущий интерфейс сохраняет native Scout/Curator и существующие правила scope/snapshot/freshness.
Источники: 
Пробелы: 

## 04 · Требования и приёмка

[Предложение] R1–R7 ниже связывают исследование с артефактами. Требования к будущей реализации явно помечены proposal; численные production SLA пока неизвестны.
Источники: 
Пробелы: 

### R1 [Из запроса]
Сравнить техники transformation и двухстадийный поиск на фиксированных запросах с явной релевантностью.
Источники: U1, U3
Пробелы: 

### R2 [Из запроса]
Оценить скорость и bottlenecks, обосновать Python/SQLite против возможного Rust.
Источники: U1
Пробелы: 

### R3 [Из запроса]
Выполнить необходимые correctness проверки и честно показать ошибки/ограничения.
Источники: U1
Пробелы: 

### R4 [Из запроса]
Не менять рабочее ядро и живые данные в проходе анализа.
Источники: U2
Пробелы: 

### R5 [Предложение]
Будущие оптимизации сохраняют scope, role, snapshot, revision, expiry/dependency checks, evidence и fallback.
Источники: C1, C2, C3
Пробелы: 

### R6 [Неизвестно]
Выбор production techniques должен пройти оценку на реальных задачах и согласованном latency/cost budget.
Источники: 
Пробелы: G1, G2, G3

### R7 [Предложение]
Все экспериментальные результаты воспроизводимы и привязаны к code/data/model/config.
Источники: E1
Пробелы: 

### AC1 → R1
Статус: Предложение
measure: Recall/nDCG/MRR@5, evidence coverage, candidate recall и paired deltas
method: Фиксированные answerable/no-answer slices; одинаковый pool до/после rerank
threshold: Таблица всех выбранных вариантов и регрессий; выигрыш не обязателен
artifact: public/*/results.json
Источники: E1
Пробелы: 

### AC2 → R2
Статус: Предложение
measure: median/p95, cold/warm, RSS, profiler/SQL
method: Изолированные временные БД, последовательные 100/1000 records runs
threshold: Измеренные bottlenecks и обоснованный порядок оптимизаций
artifact: public/scaling*; profiles; worker-result.json
Источники: E1
Пробелы: 

### AC3 → R3, R5
Статус: Предложение
measure: Correctness status по каждому suite
method: Existing suite + post_hoc TTL/drift/snapshot; будущая differential evaluation
threshold: Все затронутые проверки проходят; infrastructure/private unavailable не считаются pass
artifact: public/existing-suite.log; preview-escalated.log; freshness.log
Источники: E1
Пробелы: 

### AC4 → R4
Статус: Из запроса
measure: Отсутствие изменений production paths
method: git diff для harness/skills/scripts/pyproject.toml/uv.lock; read-only metadata и temporary DB
threshold: 0 изменений production; permitted artifacts отдельно
artifact: git status/diff и scope report
Источники: U2
Пробелы: 

### AC5 → R6
Статус: Неизвестно
measure: Качество и end-to-end latency на реальных задачах
method: Новый заранее фиксированный dataset; отдельный production reranker/runtime
threshold: Не задано: пороги качества, p95 и стоимости согласовать перед rollout
artifact: Будущий acceptance report
Источники: 
Пробелы: G1, G2, G3

### AC6 → R7
Статус: Предложение
measure: Связь результатов с версиями и provenance
method: Проверить hashes corpus/queries/transforms, command/environment и baseline revision
threshold: Для каждого замера сохранены входы, фактическая команда и ограничения
artifact: worker-result.json + manifest/digests
Источники: E1
Пробелы: 

## 05 · Данные и контракты

[По источнику] Существующий development corpus проверяется повторно. Новый публичный synthetic engineering corpus: 100 документов, 32 запроса, relevance labels зафиксированы отдельным автором до измерений. 28 answerable и 4 no-answer; есть exact, paraphrase, multilingual и multi-fact slices. Это development evidence, не реальный пользовательский holdout.
Источники: E1
Пробелы: 

[По источнику] Трансформации создаются свежим агентом только из query text, без corpus/qrels/результатов. Reranker видит запрос и перемешанные candidate documents, без qrels/исходных scores. Отдельные контексты уменьшают leakage, но не являются защищённым private evaluator.
Источники: E1
Пробелы: 

[Неизвестно] Нужен будущий набор реальных инженерных задач с оценкой источников человеком, разделённый по задачам/темам и времени. Его размер, состав и допустимые материалы ещё не заданы.
Источники: 
Пробелы: G1

## 06 · Подход и альтернативы

[Предложение] Приоритет по результатам: (1) пилот второй стадии с контролем no-answer; (2) один rewrite условно, с original branch; (3) decomposition только как проверяемая гипотеза для сложных multi-fact задач; (4) HyDE opt-in, потому что на этом наборе не превзошёл более короткий rewrite. Дешёвый локальный cross-encoder — отдельный будущий эксперимент, native LLM пока служит проверкой качества подхода.
Источники: E1
Пробелы: 

[По источнику] Kernel microbenchmark 1000×384: JSON parse+validation+normalization+Python dot median 128.96 мс; повторно используемая нормализованная NumPy float64 матрица — 0.069 мс. Однократная подготовка матрицы 123.81 мс, размер 3.07 МБ; top-20 совпал, max score delta=4.2e-17. Это показывает потенциал устранения повторов и векторизации, но не ускорение всей системы: SQL, freshness, invalidation, sorting и restart сюда не входят.
Источники: E1
Пробелы: 

[Предложение] Сначала оптимизировать измеренные повторные вычисления: повторный lexical retrieval в hybrid, чтение/декодирование всех current records, JSON vectors, повторную нормализацию и Python dot-products. Сравнить векторизованный exact search, бинарное представление производного индекса и ограниченную SQL-выборку; формат источника истины SQLite сохранять до доказанной необходимости.
Источники: C1, C2
Пробелы: 

[Предложение] Query planner — отдельный native шаг перед retrieval. Предлагаемый QueryPlan v1: original, literal identifiers, optional rewrite, bounded subqueries, optional hypothetical_document, reason и бюджет. LLM создаёт данные; Core проверяет размер/форму, фиксирует task/snapshot, запускает разрешённые ветви и сохраняет trace. При недоступности planner выполняется исходный поиск.
Источники: 
Пробелы: 

[Предложение] Rewriting: один вариант для неясных/разговорных/межъязыковых запросов с сохранением исходного поиска. Decomposition: 2–4 самостоятельных подзапроса только для задач с несколькими фактами. Exact ID/path/symbol branch защищается от вытеснения. Количество вариантов не должно автоматически увеличивать вес одного источника при fusion.
Источники: W1, W2
Пробелы: 

[Предложение] Двухстадийный поиск: retrieve top-N → union/dedup → rerank → final top-k → повторная проверка eligibility → Scout/packet. Оценивать baseline и reranked на одном candidate pool. Reranker не способен восстановить документ, который не попал в кандидаты; поэтому отдельно измерять candidate recall и качество порядка.
Источники: U3, W2
Пробелы: 

[Предложение] HyDE оставить экспериментальной опцией для абстрактных описаний и низкого recall. Гипотетический документ кодируется document encoder и служит только поисковым сигналом, не попадает в БД как знание и не подменяет evidence. Для точных API/версий/состояния сначала обычный поиск.
Источники: W3
Пробелы: 

[Предложение] Полный Rust rewrite пока не выбирать. SQLite и ONNX уже выполняют тяжёлую работу вне Python; сначала нужен профиль остаточной стоимости после алгоритмических улучшений. Если CPU всё ещё доминирует, сравнить узкий Rust-компонент со векторизованным Python на том же контракте и workload.
Источники: C2, C4, E2
Пробелы: 

## 07 · Эксперименты и оценка

[По источнику] Основное сравнение (28 answerable, 4 no-answer отдельно): semantic Recall@5/nDCG@5=96.43/93.38%; original+rewrite=100/96.32%; original+decomposition=92.86/90.31%; original+HyDE=100/96.32%; semantic+rerank=100/100%; original+rewrite+decomposition+rerank=100/100%. Варианты сохраняют original, используют RRF и exact-identifier protection.
Источники: E1
Пробелы: 

[По источнику] Rerank улучшил порядок по nDCG у 5 из 28 запросов, не ухудшил ни одного; Recall улучшился только у одного. Exploratory 95% paired-bootstrap интервал прироста Recall: [0;10.71] п.п.; nDCG: [0.57;15.72] п.п. Все три candidate pools имеют Recall@20=100%. Комбинация всех техник не дала дополнительного выигрыша относительно rerank без transforms; эффект ограничен потолком набора.
Источники: E1
Пробелы: 

[По источнику] Это native LLM reranking + relevance filtering + abstention, один blind проход, 73 уникальных pool/query пакета, 96 сравнений. Корпус/qrels и исходные scores не передавались reranker. Production latency, токены и стоимость reranker не измерены; отдельный cross-encoder не тестировался.
Источники: E1
Пробелы: 

[По источнику] HyDE run использовал hypothetical-text query path; на всех 32 зафиксированных текстах проверена побитовая эквивалентность query/document embeddings текущего bundle (max abs delta=0). Вывод относится только к этой модели и этим текстам; Hypothetical documents не сохранялись как факты.
Источники: E1
Пробелы: 

[По источнику] В harness эксперимента сначала использовалась метка exact_symbol для закрепления первого результата. После аудита правило заменено проверкой реального совпадения query с ID/ref/symbol. Сохранён исходный v1, пересчитаны результаты: все rankings/metrics и rerank input/mapping совпали. Метки больше не используются для маршрутизации.
Источники: E1
Пробелы: 

[По источнику] Исходный correctness suite: 124 теста прошли совокупно; три preview tests повторно запущены с разрешением loopback после sandbox PermissionError. Дополнительно прошли 5 новых post_hoc freshness tests. Изменений продукта не было.
Источники: E1
Пробелы: 

[Предложение] Качество: Recall@5 — доля релевантных документов в первых пяти; nDCG@5 — качество их порядка; MRR@5 — позиция первого релевантного; complete evidence coverage — все факты multi-fact запроса. Для no-answer считать abstention отдельно: top-k выдача сама по себе не доказывает наличие ответа.
Источники: 
Пробелы: 

[Предложение] Ablation: raw lexical/semantic/hybrid, original+rewrite, original+decomposition, комбинация, original+HyDE; затем одинаковые pools до/после rerank и комбинация с transformations. Показать per-query wins/ties/losses, интервалы paired bootstrap при доступности; выбор лучшего на этом наборе является adaptive development, не независимым подтверждением.
Источники: 
Пробелы: 

[Предложение] Скорость: warm query-cache hit, warm model/cache miss, fresh-process CLI отдельно; последовательный interleaved порядок, median/p95 и число повторов. Масштаб: 100/1000, при бюджете 5000 synthetic записей. Профиль Python, SQL count и RSS связываются с dataset/code/model hash.
Источники: 
Пробелы: 

[По источнику] Correctness: существующие suites плюс отдельные post_hoc проверки TTL/dependencies/revocation. Для будущих оптимизаций нужны differential parity и failure-injection: model failure, stale index, concurrent revoke/source drift, ordering, transaction rollback, restart/idempotency. Protected private evaluator отсутствует; это не означает, что private suite пройден.
Источники: E1, C3
Пробелы: 

## 08 · Воспроизводимость и артефакты

[По источнику] Baseline — чистый commit 5856756. Managed Python /Users/mshekhunov/engineering-harness/.venv/bin/python; lock uv.lock, SQLite/OS/model identity и SHA корпуса фиксируются в результатах. Запросы/labels не меняются после просмотра качества. Все benchmark DB временные.
Источники: E1
Пробелы: 

[Предложение] Артефакты: public corpus, query-only transforms/provenance, blind rerank input/output, raw per-query metrics, profiles, commands и worker-result. Время native-agent генерации не выдаётся за production inference p95 или стоимость токенов.
Источники: 
Пробелы: 

## 09 · Ресурсы и ограничения

[По источнику] Matched warm workload (8 фиксированных запросов × 3, n=24 на режим): semantic median/p95 16.07/16.61 мс при 100 документах, 161.13/177.68 мс при 1000. Fresh-process semantic без query-cache: median 1223 мс (n=3); с cached query около 200 мс. Это разные условия, их нельзя объединять в один latency показатель.
Источники: E1
Пробелы: 

[По источнику] Локальный CPU, существующая MiniLM; новые веса не загружаются. Замеры выполняются последовательно, дополнительная память ограничена примерно 2GiB, один benchmark — 300 секунд. Для увеличения размера нужно отдельное основание, а не автоматический перебор.
Источники: E1
Пробелы: 

[Неизвестно] Целевая допустимая задержка и размер будущей базы не заданы. Пороги выигрыша для Rust и reranker предстоит согласовать на реальном workload; исследовательские цифры не превращаются в SLA.
Источники: 
Пробелы: G2

## 10 · Эксплуатация

[Предложение] Deployment и миграция в текущем исследовании неприменимы. Для будущей реализации: feature flags, legacy single-query fallback, rebuildable derived index, schema versioning, backup/rollback до изменения persisted format. История knowledge revisions/evidence и 14-дневная актуальность сохраняются.
Источники: U2, C3
Пробелы: 

[Предложение] Не кэшировать разрешение на выдачу между запросами без revalidation. Даже при reuse вычислений внутри операции, перед возвратом должны повторно проверяться текущая revision/state и актуальность источников; особенно после медленного embedder/reranker.
Источники: 
Пробелы: 

## 11 · Этапы и передача

[Предложение] Этап 1 завершён: исходные и freshness tests, blind transformations/rerank, scaling/cold-warm profiling, microbenchmark и этот draft. Следующее минимальное изменение — reuse валидированных векторов + векторизованный exact search с differential tests и финальной eligibility проверкой. Затем отдельный пилот второй стадии, оценка на реальных запросах, только потом conditional rewrite/decomposition/HyDE и решение об узком Rust spike.
Источники: E1
Пробелы: 

[Из запроса] Перед будущей разработкой зафиксировать точную ревизию спеки, выбранные техники и unresolved gaps. В текущем проходе исходники ядра не изменяются.
Источники: U2
Пробелы: 

## 12 · Риски и открытые решения

[Предложение] Маленький synthetic корпус может давать потолок recall и завышать эффект rerank. Query rewriting способен стереть отрицания/версии; decomposition — потерять связь между фактами; HyDE — направить поиск к вымышленному устройству системы. Обязательны исходная ветвь и отдельные регрессионные slices.
Источники: 
Пробелы: 

[Предложение] Оптимизации prefilter/caching могут ускорить поиск ценой утечки foreign/stale данных. Rust добавляет стоимость FFI, сборки/доставки и риск расхождения семантики. Эти риски проверяются до использования живой БД.
Источники: 
Пробелы: 

[Неизвестно] Offline native-agent rerank не равен внедрённому cross-encoder. Выбор production reranker и его latency/cost ещё не измерены.
Источники: 
Пробелы: G3

[Предложение] Корпус scaling не моделирует большие графы file/knowledge dependencies, высокую конкуренцию и поток записей. Production стоимость source hashing и cache invalidation требует отдельной нагрузки.
Источники: 
Пробелы: 

## Пробелы и принятые для черновика предположения

### G1: Репрезентативные реальные запросы и qrels
status: proposed
resolution: Для исследования используем публичный synthetic corpus и существующий smoke set; не заявляем production gain.
basis: Текущий scope U2 и отсутствие размеченных real tasks.
impact: При другом распределении запросов выбранная техника может проиграть.
blocking: False
question: Какие реальные инженерные задачи должны составить последующую оценку?

### G2: Целевой размер базы и SLA latency/cost
status: open
resolution: Показываем измеренные 100/1000 scaling и текущие 34 записи; численный SLA не придумываем.
basis: U1 допускает Rust, но не задаёт latency/throughput бюджет.
impact: Можно преждевременно усложнить систему или не подготовиться к росту.
blocking: False
question: Каковы ожидаемый масштаб и приемлемая задержка при следующей реализации?

### G3: Production reranker и бюджет native planner
status: proposed
resolution: Сейчас измеряем offline качество свежим native агентом, отделяя его от cross-encoder runtime и provider cost.
basis: U3 просит оценить двухстадийный поиск; конкретный backend не задан.
impact: Качество offline может не воспроизводиться выбранной локальной моделью.
blocking: False
question: Для внедрения предпочесть локальную модель или native LLM с большей задержкой?

## Схемы (визуализация в review.html)
Существующее ядро и предлагаемый путь retrieval
Предлагаемые узлы обозначают изменения текущего поиска. Core остаётся детерминированным; LLM вызывается нативным агентом. Направления показывают данные, а не новые полномочия.
A [external] Запрос задачи: Смысл задачи, точные идентификаторы и ограничения.
B [proposed] План поиска: Original + условные rewrite/decomposition/HyDE; бюджет и trace.
C [proposed] Кандидаты: FTS5 / dense / hybrid, scope и snapshot; dedup/fusion.
D [existing] SQLite и производный vector index: Revisions/evidence, TTL 14 дней и dependencies.
E [proposed] Reranking top-N: Оценка релевантности кандидатов; не источник новых фактов.
F [existing] Повторная проверка и context packet: Текущая актуальность, Scout selection и ограничение бюджета.
G [existing] Результат задачи и Curator: Outcome/evidence → proposals/reconciliation.
A → B: Текст и допустимые ограничения
B → C: Проверенный plan или fallback original
D → C: Только доступные записи и векторы
C → E: Ограниченный набор кандидатов
E → F: Отранжированные ссылки, без гипотетических фактов
D → F: Проверка свежести перед выдачей
F → G: Контекст для работы и проверяемый результат
G → D: Evidence-backed revisions через Core

## Scouting
{"status": "ready", "task_id": "retrieval-study-2026-11-13-spec", "packet_id": "P-c49938978e804a09a42d544e89a659e4", "notes": "Свежий отдельный Scout; maintenance due=0. Legacy store выбран по известному project_id engineering-harness: отдельного project.json у checkout нет. Пакет содержит четыре записи; история не заменяет новые замеры. Корпус целиком в основной контекст не загружался."}

## Источники
U1 [user]: .harness/tasks/retrieval-study-2026-11-13/request.txt — Исходный запрос: выбрать техники поиска, оценить оптимизацию и Rust, провести тесты.
U2 [user]: Ответ пользователя в этом чате 2026-11-13 — Выбран scope: «Анализ, замеры и план улучшений».
U3 [user]: .harness/tasks/retrieval-study-2026-11-13/rerank-addendum.md — Добавлено измерение двухстадийного поиска и совместного эффекта с transformations.
C1 [code]: harness/knowledge.py @5856756: search/scout_brief — Прямой goal, FTS5 OR, полный обход current revisions, Scout после retrieval.
C2 [code]: harness/semantic.py @5856756: search/query_vector/normalized — JSON vectors, cosine в Python, RRF, проверка актуальности и lexical fallback.
C3 [code]: harness/freshness.py @5856756: health/source — 14 суток, зависимые записи и file hashes; это обязательные инварианты оптимизаций.
C4 [code]: harness/embeddings.py @5856756: LocalEmbedder — Локальная multilingual MiniLM через FastEmbed/ONNX; query и document входы, проверка bundle.
E1 [artifact]: .harness/testing/retrieval-study-2026-11-13/public/worker-result.json — Независимый public evaluation worker: тесты, corpus hashes, замеры и ограничения.
E2 [artifact]: .harness/tasks/retrieval-study-2026-11-13/db-metadata.json — Read-only метаданные legacy store: 34 записи, 34 revisions, 13 vectors, 806912 bytes; содержимое не экспортировалось.
W1 [web]: https://arxiv.org/abs/2305.14283 — Первичная работа о rewriting; её выигрыш не переносится автоматически на наш корпус.
W2 [web]: https://aclanthology.org/2025.acl-srw.32/ — Декомпозиция + retrieval подзапросов + reranking для multi-hop; мотивация ablation.
W3 [web]: https://aclanthology.org/2023.acl-long.99/ — HyDE: гипотетический документ для векторного retrieval; синтетический текст может содержать вымысел.
W4 [web]: https://www.sqlite.org/fts5.html#sorting_by_auxiliary_function_results — FTS5 rank может ускорить сортировку относительно прямого bm25; применять только с прежними весами и проверкой порядка.
K1 [knowledge]: K-adcda7d944824ff1a79526f6bbd23946@1 — Контекст разделения project/legacy store; миграция не является частью исследования.
