# Двухстадийный поиск и условный rewrite

Core не вызывает LLM и не хранит сгенерированные тексты как knowledge claims.
Нативный агент делает две ограниченные содержательные операции: Query Planner
(только когда нужна переформулировка) и свежий Reranker/Context Scout после retrieval.
Python CLI валидирует JSON, выполняет поиск и сохраняет проверенный context packet.

## Путь по умолчанию для skill

1. `workflow start --input task.json --retrieval staged --output START`.
   Перед работой обработать maintenance. Получить `planner_paths[ROLE]`.
2. Для точного ID/symbol/path и ясного вопроса planner можно пропустить.
   Иначе передать planner brief свежему агенту без базы, корпуса, qrels или transcript.
   Его ответ — план ниже. Один rewrite допустим для неясного/разговорного/межъязыкового
   запроса. Версии, имена и отрицания сохраняются; факты не выдумываются.
3. `workflow retrieve --task T --role developer --input plan.json --mode semantic --output RETRIEVAL`.
   Без `--input` выполняется явно обозначенный original-only bypass/fallback.
   Original всегда сохраняется; по каждой уникальной ветви до 30 результатов,
   RRF k=60, дедупликация, приоритет исходного точного ID/ref/symbol, до 20 кандидатов.
   `--candidate-limit` допускает 1–30. Все ветви сохраняют scope/snapshot/freshness.
4. Передать **только файл по `reranker_path`** другому свежему native агенту.
   `retrieval_path` — полный audit trace, не его prompt: там есть план и HyDE.
   Reranker видит goal и candidate claims (до 2000 символов, с признаком truncated),
   а не исходные scores, qrels или гипотетические документы. Его задача — ранжировать
   полезные записи, сохраняя все необходимые факты, и отказаться при недостатке поддержки.
   Усечённый текст и пустой ответ не доказывают отсутствия знания во всей базе.
5. `workflow rerank --task T --role developer --input ranking.json --top-k 5 --budget 1200 --output PACKETS`.
   Подставленные/чужие/повторные refs отклоняются. Изменившиеся/отозванные/просроченные
   записи удаляются, затем выбирается top-k; дополнения из неранжированных refs нет.
   Budget может дополнительно сократить packet: проверяй `omitted_by_budget`.
   Current-state checks выполняются ещё раз перед сохранением packet.

В этой установке запускай CLI через managed Python из installation-profile.
Команды выше — аргументы `skills/knowledge-cycle/scripts/knowledge.py`.

## JSON

```json
{
  "version": 1,
  "task_id": "T",
  "role": "developer",
  "original": "дословный task.goal",
  "rewrite": null,
  "reason": "Вопрос достаточно ясен"
}
```

`rewrite` — один непустой текст до 1000 символов либо null. Unknown fields,
wrong task/role/original и некорректные типы отклоняются. Experimental поля:
`subqueries` (до 3, каждый до 1000 символов), `hypothetical_document` (до 1500).
Они требуют явного `--experimental`, даже если их предложил planner.
HyDE использует document encoder и отдельный namespace query-vector cache;
никакого implicit promotion/ingest гипотезы нет. Это opt-in исследовательские ветви,
а не рекомендация включать их на каждой задаче.

```json
{
  "retrieval_id": "R-идентификатор-из-brief",
  "ranked_refs": ["K-id@1"],
  "abstain": false,
  "reason": "Запись содержит требуемое условие"
}
```

До 30 unique refs из сохранённого DB-owned candidate pool. `abstain:true`
требует пустой массив; `abstain:false` — непустой. `--top-k` 1–8, default 5.
Ответ на другой task/role/policy/snapshot не принимается. Возвращённый reason —
объяснение выбора, не новый claim и не независимое доказательство корректности.

## Недоступность агента и trace

`workflow rerank --task T --role ROLE --fallback --retrieval-id R-ID --output PACKETS`
использует порядок retrieval с текущей проверкой источников. Mode в сохранённом
packet — `retrieval_fallback`; при настоящем ответе — `native_rerank`.
Невалидный ответ не превращается в молчаливый fallback; исправь JSON или явно
отметь недоступность агента. При `abstain:true` получается пустой packet.

Новая additive таблица `retrieval_runs` хранит immutable task/role-bound pool,
plan digest и provenance ветвей; schema текущих knowledge revisions не меняется.
Saved packet содержит retrieval trace: ranking source, refs, исключённые refs,
abstention и предупреждения. Это local cooperative audit, не криптографическая
защита от владельца SQLite/файлов. Внешний private backend отсутствует.

## Вычисления и пределы

Semantic search повторно использует одну ограниченную матрицу нормализованных
float64 vectors на connection. NumPy опционален; без него работает stdlib path.
Первый одиночный запрос не импортирует NumPy, если модель ещё его не загрузила;
переход от кэша чисел к матрице выполняется при повторном использовании.
Cache key включает model identity и фактические index rows (revision/hash/vector),
в том числе direct SQL changes. Eligibility, TTL, source hashes и current revocation
не кэшируются. Очень близкие scores пересчитываются reference fsum для стабильного
порядка. Производный индекс на диске остаётся совместимым JSON; Rust, daemon,
новая vector DB и загрузка модели не требуются.

Cached matrix ускоряет повторные запросы внутри процесса и multi-query retrieval;
CLI cold startup и native LLM latency остаются отдельными затратами. Наличие этих
API/skill instructions не гарантирует автоматический вызов native агента каждым
клиентом. Для проверки поведения нужны отдельные native smoke runs и реальные задачи.
