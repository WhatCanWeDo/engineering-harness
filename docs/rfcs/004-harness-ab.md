# RFC 004 — /harness-ab: A/B evaluation собственных skills

**Статус:** направление принято пользователем 2026-11-03; local MVP v0.1 реализован. Реальные A/B эксперименты ещё не проведены. [Canonical skill](../../skills/harness-ab/SKILL.md), [текущий CLI/контракты](../../skills/harness-ab/references/protocol.md). Ниже сохранён архитектурный дизайн; предложения расширенного runtime не означают готовую возможность.

## 1. Зачем

Определять, помогает ли изменение skill/workflow на целевых инженерных задачах, сколько стоит этот выигрыш и где возникают регрессии. Один красивый пример, рост покрытия тестами или хороший LLM review не заменяют измерение пользы человеку.

Единица сравнения — **пара запусков одной задачи на одном исходном snapshot**: A = зафиксированная рабочая конфигурация; B = та же конфигурация с объявленным изменением skill/workflow. Повторы нужны из-за недетерминированности; разнообразные задачи — чтобы не принять успех на одном случае за общую пользу.

Skill запускается по запросу, например `/harness-ab plan` или «сравни текущий skill с этой версией». Обычная правка skill не включает платные эксперименты автоматически. Запрос на дизайн не является разрешением начать A/B runs. Если задача и лимиты уже явно авторизованы, не запрашивать повторное разрешение на каждый шаг.

Предлагаемый default до выбора перед конкретным экспериментом: correctness как обязательное ограничение; основная цель — уменьшение активного времени человека, стоимость и число исправлений — отдельные показатели. Нет скрытого единого score. Конкретные пороги пользы, допустимого риска, бюджет и состав human review фиксируются в плане до результатов.

## 2. Что именно сравниваем

ExperimentPlan включает hypothesis, intended use cases, primary metric, guardrails, stopping rule, task suite, arm manifests, schedule, review protocol и budget. Пример гипотезы: «Новая версия understand-changes сокращает время review без снижения точности понимания и корректности артефакта».

У каждого arm полное effective configuration: базовые инструкции, skills, generated entrypoints, workflow, tools/permissions, model ID/reasoning settings, native agent version, environment/data/code hashes, limits. Manifest фиксирует и dirty/untracked файлы в scope. При отсутствии Git HEAD используются файловые hashes. Различие A→B проверяется against allowlist change scope; незаявленные изменения делают сравнение invalid.

Если B меняет несколько capabilities, измеряется **эффект всего пакета**, а не каждого элемента. Следующее исследование может отключать по одному компоненту. Сравнение разных моделей/агентов — отдельный фактор/эксперимент, не скрытая часть теста одного skill. Model alias, который нельзя привязать к серверной версии, обозначается как ограничение контроля.

Если skill требует дополнительного explanation/quiz, его чтение входит в человеческое время B. A получает обычный предусмотренный результат, а не искусственно ухудшенный baseline. При оценке знания пользователя нужен отдельный одинаковый transfer probe по контракту; quiz, сгенерированный самим treatment, не служит независимым эталоном.

## 3. Дизайн запуска и изоляция

Для каждого `(task_id, replicate_id)` создаются A/B из одного filesystem snapshot и идентичных исходных данных. У каждого — новая native session, отдельные рабочие файлы и writable state; история другого arm, repair feedback и последующие знания не передаются.

Расписание пар и порядок A/B внутри пары фиксируются случайно до выполнения; по набору задач используется баланс AB/BA. Default выполнение последовательно, чтобы одновременные процессы не конкурировали за CPU/GPU. Между arms одинаковые per-run ceilings; дополнительные subagent calls workflow считаются расходом своего arm. Seed записывается, если backend его поддерживает; одинаковый seed не обещает одинаковое поведение разных workflows.

Нужно проверять реально эффективную конфигурацию. Одна новая worktree не отключает глобальные skills, auto-memory, hooks или personal instructions. Adapter должен перечислить их, настроить поддерживаемую изоляцию и записать capability receipt. Если нельзя исключить значимую незаявленную подсказку — `isolation_unavailable`/exploratory run, не чистое A/B. Shared filesystem сам по себе не является границей безопасности.

Skill loaded ≠ skill followed. Основной анализ включает все назначенные runs, а не только те, где модель, по её словам, использовала skill. Отдельно записываются доступность/загрузка по adapter evidence. Техническая невозможность загрузить пакет — infra error; загруженный, но неэффективно применённый skill — результат treatment.

Cache/network policy фиксируется: исходный dependency cache одинаков, warm/cold режим объявлен, latency внешних сервисов записана. Случайно прогреть кэш только для B нельзя. Нельзя очищать глобальные пользовательские caches ради эксперимента; нужен отдельный cache namespace. Warmup costs показываются отдельно.

## 4. Как совместить A/B с общей памятью

Knowledge snapshot фиксируется **до всего эксперимента**, не обновляется между задачами/повторами. Общие writes из экспериментальных runs перенаправляются в отдельные run-local stores/outboxes. Даже обычный knowledge-cycle не должен публиковать ответы одной ветки в общую базу до закрытия эксперимента.

Если изучается другой skill, можно заранее собрать одинаковый разрешённый context packet для обоих arms. Если treatment — сам retrieval/Scout workflow, фиксируется corpus и политика доступа, но пакеты вправе различаться: это часть вмешательства. Стоимость Scout/Curator включается в соответствующий arm; не требуется одинаковый контекст ценой устранения изучаемого эффекта.

После закрытия публикуются experiment evidence и узкие conclusions с config/task-set IDs. Контрпримеры и изменённые prompts попадают в development namespace, исключённый из будущего независимого holdout. General «skill всегда лучше» автоматически не появляется. Приватные suites/ответы не проходят через общую память.

Это требует дополнительного adapter режима: существующий `workflow start/ingest` работает с указанной БД, но сам по себе не гарантирует перенаправление всех native memory writes.

## 5. Набор задач и проверка корректности

TaskSuite фиксируется до результатов и отражает intended workload: типы задач, сложность, положительные сценарии и существенные границы. Нельзя выбрать только случаи, где candidate уже выиграл. Historical реальная задача с известным решением — development case, если skill создавался с её учётом.

У каждой задачи открытый контракт требований и независимый evaluator/rubric. Исполняемая корректность — одинаковые acceptance checks для A/B на frozen outputs. Для документа/объяснения нужны проверки фактов, требований и обоснованности ответа; количество Markdown-заголовков недостаточно. LLM reviewer может дать дополнительную рубрику, но не превращает её в объективную гарантию.

Тесты генерирует другой свежий агент по test-on-request protocol, до решения где требуется. Уже готовый общий suite используется повторно без нового LLM-вызова. Тесты, которые создал сам treatment, считаются продуктом workflow, а не независимым oracle для сравнения.

Private checks допускаются только через защищённый evaluator; в текущем local profile они unavailable. Если приватность обязательна для выбранного gate, результат partial/unavailable. Папка с другим именем и второй subagent не создают секретный holdout.

Optional adversarial stage начинается после фиксации обоих outputs: одинаковый бюджет атаки, отдельные авторы/сессии, проверенный общий spec. Подтверждённые contract-valid reproducers объединяются и запускаются на обоих frozen outputs. Результат — supplemental stress evaluation, с post-hoc provenance, не переписанный initial suite. Feedback о решениях не поступает ни одному продолжающему baseline/candidate run.

## 6. Четыре метрики

| Метрика | Что сохранять | Что не подменяет метрику |
|---|---|---|
| Correctness | Независимый результат frozen first output, requirement-level failures/severity, suite/rubric hashes; отдельно after-repair | Самооценка исполнителя, число его тестов, успешность после скрытого ремонта |
| Review time | Активные секунды человеческого чтения/проверки по start/pause/resume/finish events; stop reason и artifact hash | Время ответа LLM reviewer, время открытой вкладки, скорость генерации |
| Cost | Все attributable calls/tools/compute по arm и фазе; raw usage, billing basis, currency и tariff version | Количество токенов как якобы точный долларовый счёт или нулевая цена подписки |
| Manual corrections | Уникальные подтверждённые issue IDs, severity, human edits и agent repair requests; отдельно rounds и active repair time | Число commits/строк diff/каждое сообщение как отдельный баг |

First-pass означает результат полного разрешённого автономного run до первого repair feedback, а не первый набросок кода: внутренние попытки, public test runs и self-repair входят в его стоимость. Разрешённые уточнения требований задаются одинаковой заранее подготовленной политикой ответов; новое человеческое уточнение спецификации фиксируется и одинаково применяется к обоим arms либо пара признаётся несопоставимой. Подсказка готового решения — уже intervention, а не незаметное уточнение.

Замеры привязаны к run/artifact revision. Начальное решение `F0` неизменно. Исправления дают `F1…Fn` и новую after-repair проверку; `F0` не становится correct задним числом.

Review time и repair time не перекрываются. Human active total = review + repair + необходимые task-time interventions, если они входят в заранее объявленную границу эксперимента. Таймер ставится на паузу при уходе/ожидании, сохраняет events между reload; idle detection предлагает паузу, а не делает вид, что измеряет мыслительную работу. Abandoned/capped review — цензурированное наблюдение с затраченным временем, не ноль.

Одна ошибка, потребовавшая три итерации, имеет один issue ID, три rounds и фактическое затраченное время. Clarification без исправления дефекта — отдельная intervention category. Уверенное «не видел багов» без законченного review не означает ноль исправлений. Unreviewed corrections/time = null.

Cost breakdown: production first pass, production repair, skill sidecars, shared experiment setup/evaluation/report overhead. Sidecars treatment не прячутся в overhead. Shared evaluator preparation не записывается как дополнительная цена B. Отдельно показываются стоимость проведения A/B и оцениваемая стоимость использования skill.

Для API есть `reported`/`estimated`/`unknown`, input/output/cache/reasoning usage только где они доступны, дедупликация request IDs и версия тарифа. Тариф можно передать явно или проверить у provider при запуске; текущие цены в skill не зашиваются. Для CLI подписки допустимы usage proxies и факт подписки, но не выдуманная marginal USD цена. Unknown не складывается как ноль: показываются известный subtotal и coverage.

## 7. Человек в эксперименте

Review UI показывает artifact с нейтральным label, контракт, одинаковые разрешённые evidence и таймер. Mapping arm↔label скрывается от reviewer до фиксации его verdict; coordinator может его знать. Не удаляется содержательная разница, ради которой изучается skill.

Порядок AB/BA сбалансирован, но один человек неизбежно учится при втором просмотре той же задачи. `review_order`, prior exposure и возможное распознавание treatment записываются. Такой personal crossover полезен для пилота, но не считается полностью слепым чистым причинным замером времени.

Для более строгого подтверждения нужны независимые reviewers, видящие один вариант задачи, с рандомизацией и блокировкой по reviewer/task; либо первая экспозиция на новых сопоставимых задачах с назначением вариантов. Это отдельный reviewer protocol: его нельзя молча смешать с paired same-person review. Если таких данных нет, ограничение остаётся в conclusion.

Можно сделать automatic-only этап и позднее human review. Тогда correctness/cost доступны раньше, human metrics остаются missing, и обещание сэкономить человеку время не подтверждено. Если review дорогой, subset определяется до результатов: например, один заранее выбранный replicate на задачу. Он не выбирается из самых удачных outputs; coverage и отдельный denominator явны.

## 8. Анализ и решение

Сначала проверяются protocol integrity, полнота и correctness guardrails; затем стоимость и трудозатраты. Ошибка более дешёвого кандидата не компенсируется произвольным высоким баллом.

Основной summary — paired deltas B−A по каждой задаче/replicate и распределение task-level результатов. Для correctness показывается матрица both-pass / only-A / only-B / both-fail, а не только средний pass rate. Технические сбои и missing assessments показываются отдельно; denominator всех назначенных runs сохраняется. Более быстрый timeout не считается ускорением успешной разработки.

В MVP — описательный paired report без автоматического p-value. По repeated tasks сначала агрегируем replicates внутри task; task families не объявляются независимыми, если это варианты одного случая. При достаточном заранее спланированном наборе следующий этап может добавить интервалы с ресемплингом по независимым task clusters. Повтор одного task сто раз не даёт сто новых задач и не доказывает переносимость. Отсутствие наблюдённой регрессии не доказывает equivalence/non-inferiority.

Для confirmatory run заранее определяются допустимая correctness margin, practically meaningful improvement и способ обработки неопределённости. Значение margin=0 как эксплуатационное требование не означает, что маленькая выборка может статистически доказать отсутствие ухудшения. Если данных мало — inconclusive. Нельзя подбирать threshold после просмотра результата, перебирать варианты до успеха или останавливаться в удачный момент без заранее заданного sequential protocol.

DecisionRecord statuses:

- `invalid`: нарушены условия сравнения/изменён контракт/утечка между arms.
- `incomplete`: нет обязательных метрик/оценок, включая human review.
- `regression_observed`: найдена нежелательная correctness/guardrail регрессия; требуется анализ/повтор на новом candidate.
- `inconclusive`: evidence не отделяет полезный эффект от вариации.
- `promising_on_dev`: интересный результат на development наборе, пригодный для следующей проверки.
- `recommend_pilot`: выполнен заранее заданный критерий выбранного validation profile; всё ещё не автоматическая установка.

Эти статусы не заменяют raw metrics и uncertainty. Даже явный выигрыш одной метрики может быть trade-off по другой. В MVP report предлагается следующее действие, но baseline меняется только по решению пользователя.

## 9. Лимиты, повторы и неполные данные

Пример небольшого разведочного плана: 3 задачи × 2 replicates × 2 arms = 12 solution runs, плюс явно посчитанные evaluator/sidecar calls. Это стартовый smoke, не статистически достаточное число. Более широкий пилот выбирается по бюджету и intended workload, а не по magic sample size.

План заранее содержит max runs, per-run time/call limits, общий бюджет денег при доступном billing и лимит human review. При неизвестной цене ограничивать calls/time и маркировать monetary limit non-enforceable. Interactive-only adapter может давать advisory limit; enforceable wall-clock/process/resource limits требуют внешнего runner.

Budget exhaustion прекращает новые запуски. Таймаут/исчерпание разрешённого лимита исполнителем — результат under-budget constraint. Сбой runner/сети — infra error, не доказанный баг skill. Политика retries задаётся заранее (например, одна замена полной пары при infra failure); все attempts и расходы сохраняются, «лучший из нескольких» не выбирается. Без доступного budget никакие платные native runs автоматически не начинаются.

Ускорение среди both-pass пар можно показать отдельно, но оно условно и может иметь selection bias; рядом обязательны overall correctness, failed/censored cases и coverage. Неполная пара не получает delta и не исчезает из журнала. Непросмотренный артефакт не получает `review_seconds=0`.

## 10. Автоматизация и общие контракты

| Сущность | Ключевые поля |
|---|---|
| ExperimentPlan | objective, task_suite hash, A/B manifests, primary metric, guardrails, limits, schedule, review protocol, analysis version |
| RunAssignment | experiment/task/replicate/arm IDs, starting snapshot, native adapter, run-local paths, context provenance |
| ExecutionReceipt | effective config, model/version controls, frozen output hash, status, duration, attempts, skill loading evidence |
| UsageRecord | request_id, provider, phase, tokens/cached units/compute, billing basis, tariff snapshot, money/null |
| EvaluationRecord | output hash, evaluator version, per-requirement verdict, errors, provenance, protected ref where applicable |
| HumanReview | pseudonymous reviewer, artifact hash, exposure/order, timer events, verdict, correction issues/rounds, cap/abandon reason |
| ComparisonReport | paired rows, denominators, missingness, phase costs, guardrails, uncertainty/limitations, decision candidate |
| ImprovementProposal | failure class, supporting runs, proposed skill change, expected mechanism, new experiment requirements |

Составные keys кодируются структурированно, а не конкатенацией через двоеточие: в текущем Knowledge MVP уже находилась такая коллизия. Idempotent writes связаны с содержимым; повтор с другим payload не перезаписывает результат.

Исходный CLI sketch (точный реализованный интерфейс см. protocol.md):

```text
harness ab plan --baseline A --candidate B --suite tasks.json
harness ab prepare --experiment E
harness ab dispatch --experiment E --next
harness ab ingest --run R --receipt receipt.json
harness ab evaluate --experiment E
harness ab review --experiment E
harness ab report --experiment E
```

`plan` конкретизирует сравнение и бюджет; `prepare` проверяет hashes/isolation capabilities и создаёт schedule/briefs. `dispatch` выдаёт следующий immutable assignment нативному adapter — не собственный LLM loop. Fresh native execution создаёт receipts; `ingest` проверяет их. `evaluate` использует общий независимый evaluator. `review` запускает local review recorder; `report` вычисляет результаты и выдаёт кликабельный HTML.

Скрипты отвечают за snapshot/config diff/schedule, создание папок и briefs, импорт usage, валидацию, таймер events, pairing, агрегацию, графики и ссылки. LLM нужны исполнителям, отдельным авторам tests/rubrics при необходимости и необязательному анализатору failure patterns. Analyzer получает компактные evidence, а не все transcripts, и не может менять исходные результаты.

## 11. Структура будущего skill и MVP

```text
skills/harness-ab/
  SKILL.md                 # маршрутизация plan/run/report/improve
  agents/openai.yaml       # explicit invocation
  references/protocol.md   # смысл arm, evidence, metrics, limits
  references/review.md     # human measurement и carryover
  scripts/ab.py            # thin CLI wrapper к shared Core
harness/ab/                # manifests, schedule, receipts, aggregation
  ...                      # выбирается при реализации, не обязателен framework
```

Codex/Claude entrypoints остаются тонкими. `/harness-ab` — пользовательское имя Claude-style invocation; конкретные native bindings проверяются при реализации, не считаются уже установленными. CLI и optional MCP используют одну business logic. Канонический entrypoint теперь находится в skills/harness-ab и подключён project-level адаптерами.

MVP: один model/agent stratum на experiment; локальные snapshots, вручную/нативно запущенные fresh sessions, evidence ingest, independent existing evaluator, local review recorder и paired descriptive HTML. Auto headless dispatch, protected holdout backend, статистические sequential tests и multi-model ranking позже.

Приёмка будущей реализации: drift A/B обнаруживается; B не читает результат A через memory; evaluation hash mismatch invalidates verdict; missing cost/review не становится нулём; retry не превращается в best-of; first output не перезаписывается ремонтом; exposure/censoring сохраняются; report воспроизводится без LLM. Это критерии, не уже выполненные тесты.

## 12. Улучшение skills без overfitting

Development набор нужен для диагностики. Новый candidate = новая версия с локальным, объяснимым изменением. Его повторная оценка на использованном dev-наборе честно называется adaptive. Перед promotion — зафиксированный candidate и свежий validation набор; если защищённого holdout нет, не называть набор секретным. После изучения ошибок validation данные становятся dev для последующей итерации.

После решения можно постепенно вводить skill в ежедневную работу и наблюдать реальные метрики/rollback criteria. Смешанные результаты по task classes могут означать более узкий activation scope, а не необходимость ещё длиннее написать SKILL.md. Авто-переписывание skills и незаметное переключение baseline не входят в MVP.

## 13. Основания и открытые настройки

Подход к парным различиям опирается на [NIST: paired comparisons](https://www.itl.nist.gov/div898/handbook/eda/section3/eda353.htm); сохранение контролируемых условий и рандомизация порядка — на [NIST: randomized block designs](https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm). Это основание структуры эксперимента, а не готовый статистический сертификат маленького пилота. Остальные engineering решения — предложения этого RFC.

До реального run фиксируются primary metric, review protocol/coverage, total budget, task suite, guardrail thresholds и фактически доступные adapter capabilities. Эти параметры допускают настройку; текущие defaults — предложения, не сохранённое решение пользователя.

## 14. Реализованный local MVP, 2026-11-03

Детерминированный CLI: plan/prepare/dispatch/freeze/receipt/ingest/evaluate/review/status/report/close. Frozen inputs/output files и SQLite backups; content-bound idempotency; четыре метрики, planned denominator, task-level aggregation; standalone timer export/import и HTTP delivery через существующий helper.

Ограничения: manual native launch; сам адаптер не обеспечивает isolation. Отсутствие attestation исключает положительную рекомендацию; declared violation даёт invalid. Retry policy только none, repair revision только F1, один final review на run. Новый протокол/попытка требует нового experiment. Нет automatic headless controller, protected private backend, native memory interception, billing reconciliation или statistically powered inference. Review active total покрывает только реально записанные recorder intervals. Приёмочные assertions из раздела 11 остаются целями для независимого тестового набора, а не объявлением пройденных проверок.
