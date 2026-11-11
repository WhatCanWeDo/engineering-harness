# Knowledge Core — контракт реализации MVP-1

2026-11-03. Публичный контракт до реализации. Основание: RFC 003. Python 3.11+, stdlib + SQLite FTS5. Защищённый private backend отсутствует. Локальные bindings предотвращают ошибочную маршрутизацию через API, но не доступ процесса с теми же filesystem правами.

## API

`from harness.knowledge import KnowledgeStore, KnowledgeError`. `KnowledgeError.code` — стабильный код; текст пояснения не контракт. `KnowledgeStore(path)` открывает/создаёт SQLite и закрывается через `close()`/context manager. Результаты — JSON-совместимые dicts. Каждый write атомарен. Глобальные файлы не трогаются при переданном временном path.

- `begin_task(task_id, project_id, goal, roles=None, applicability=None)`: роли по умолчанию developer/public/adversarial. Возвращает task_id, project_id, snapshot_seq, roles, goal, status. Одинаковый повтор возвращает тот же binding; другой goal/project/roles с тем же ID — conflict. Snapshot фиксируется при первом begin; новые записи после него не попадают в пакет этой задачи. Role private недоступна.
- `get_task(task_id)`: текущий binding и outcome/curation status.
- `add_evidence(task_id, path, label='')`: снимок явно выбранного regular UTF-8 файла (не symlink), не более 2 MiB. Возвращает evidence_id, sha256. Снимок не меняется при последующей правке исходника. Evidence принадлежит проекту/задаче. Это source artifact, не trusted test verdict.
- `finish_task(task_id, outcome)`: outcome.status ∈ success/failure/interrupted, evidence_ids список принадлежащих этой задаче evidence, candidate_ref опционален. В транзакции сохраняет outcome и outbox. Возвращает status:queued и job_id. Идентичный повтор идемпотентен; другой outcome с тем же task — conflict. После сбоя процесса reconcile продолжает обработку.
- `propose(task_id, proposals, batch_id)`: только после finish; durable enqueue списка предложений. Повтор task/batch_id+тот же payload идемпотентен, другой payload — conflict. Пустой список разрешён (no_change). Возвращает status:queued/job_id. Невалидный batch отклоняется целиком, не публикуется частично.
- `reconcile(limit=100)`: детерминированно применяет jobs без вызовов LLM. Результат `{processed, receipts, pending}`. Outcome job оставляет задачу curation_pending; proposal job завершает curation. Receipt включает entry_refs (`K@rev`), no_change и job_id. Закрытие/повторное открытие store и повтор reconcile не создают дубликатов.
- `review(task_id, entry_id, expected_revision, decision, claim=None, kind=None)`: approve/reject/stale/retract. Approve → active, reject/retract → retracted, stale → stale. Сохраняет новую revision, не перезаписывает историю. Неверный expected_revision — conflict. Доступ только к проекту task или general; операция требует ранее полученного пользователем разрешения, API сам не проверяет человека по криптографической подписи. Automation её не вызывает. Active hypothesis остаётся гипотезой и не входит в factual search по умолчанию.
- `promote(task_id, entry_id, expected_revision, title, claim)`: явная разрешённая публикация нового general entry (active), а не смена scope исходной записи. Origin/evidence исходного проекта остаются в audit; public general projection содержит opaque release reference, не скрытые пути/содержимое проекта.
- `search(task_id, query, role='developer', limit=30, include_candidates=False, mode='lexical')`: `{status, mode, results, snapshot_seq, warnings}`. Results содержат entry_id/revision/title/claim/kind/state/scope и безопасные citations. Только текущие active revisions, существовавшие к snapshot, применимые к task и доступные роли; include_candidates открывает candidate/hypothesis только явным запросом. Disputed/stale/retracted не становятся фактами. Пустой query → пустая выдача. Exact entry IDs/symbols и FTS ранжирование; FTS-спецсимволы/кавычки входа не должны ломать SQL.
- `get_entry(task_id, entry_id, role='developer', revision=None)`: разрешённая проекция записи. Для запрещённого/чужого/отозванного источника — not_found; это не oracle существования. Старую revision нельзя вернуть вместо отозванной current. Candidate можно читать владельцу проекта для review; retrieval не делает его фактом.
- `prepare_context(task_id, query=None, role='developer', budget=1200, required_refs=None, selected_refs=None, mode='lexical')`: `{packet_id, task_id, role, snapshot_seq, text, sources, token_count, token_method, omitted_by_budget, warnings}`. Text — извлечённые claims/citations без свободной LLM-генерации, сохраняет тип и caveats. Бюджет относится к text, счётчик по умолчанию `utf8_bytes_div3_estimate`; это явно оценка, не гарантия конкретного tokenizer. Максимум 8 sources. Required refs нельзя молча отбросить: required_context_overflow или required_context_unavailable. Selected refs от Scout проходят те же фильтры. Пакет сохраняется для аудита. Отсутствие результатов даёт пустой пакет с предупреждением, не выдуманные факты.
- `expand(packet_id, entry_ref)`: только source из этого packet, с повторной проверкой binding/current revision/состояния/прав. Отозванный или заменённый source — not_found.
- `set_task_roles(task_id, roles)`: локальная административная операция смены binding, увеличивает policy revision. Уже созданный packet не обходит новый запрет.
- `curator_brief(task_id)` / `scout_brief(task_id, role='developer', budget=1200)`: готовый компактный prompt + task metadata. Curator получает outcome и разрешённые evidence; Scout — разрешённые candidates для отбора, не историю разработчика. Private generation unavailable.
- `export_project(project_id)`: JSON snapshot текущих записей своего проекта + general, без чужих project details. Экспорт — проекция, не второй источник истины.

## Предложение

```json
{
  "title": "Наблюдение TTL",
  "claim": "На границе TTL возвращено старое значение",
  "kind": "observation",
  "scope": "project",
  "evidence_ids": ["E-..."],
  "basis": {"evidence_id": "E-...", "quote": "На границе TTL возвращено старое значение"},
  "applicability": {},
  "tags": ["TTL"],
  "symbols": ["Cache.get"]
}
```

Kinds: observation/decision/hypothesis/negative_result/procedure/preference. Scope в propose только project; general — через promote с отдельным release. Missing scope → project. Private/restricted scope и попытки подменить project_id отклоняются.

Без basis предложение становится candidate независимо от уверенности автора. Auto-active только для observation с basis.quote, буквально присутствующим в доступном immutable evidence и равным claim. В пакет попадает **цитируемое наблюдение источника, не универсальный вывод**. Нельзя этим способом auto-publish hypothesis/procedure или cross-project knowledge. Прочие обобщения требуют review.

Evidence refs должны принадлежать исходной task; иначе batch не проходит. Для обновления существующей project записи используются entry_id + expected_revision; новая revision candidate/active определяется теми же правилами и сохраняет историю. Applicability — map строковых условий; если task не сообщает нужного совпадающего значения, запись не включается. Observed_at при наличии ISO UTC не может быть позже начала receiving task; recorded revision также должна попадать в snapshot. Исторический публичный bug из другой прошлой задачи допустим, вывод о текущей целевой реализации после cutoff — нет.

## CLI

`python3 -m harness --db PATH COMMAND`. Без --db: пользовательский локальный store в ~/.local/share/engineering-harness/knowledge/knowledge.sqlite3. Init явный; API(path) создаёт store. CLI commands:

```text
init
task begin --input task.json
task finish --task T --input outcome.json
task show --task T
evidence add --task T --path output.log --label run
knowledge propose --task T --batch B --input proposals.json
knowledge reconcile
knowledge review --task T --entry K --expected-revision 1 --decision approve
knowledge promote --task T --entry K --expected-revision 2 --title TITLE --claim CLAIM
knowledge search --task T --query QUERY [--role developer]
knowledge export --project P
context prepare --task T [--role public] [--budget 900] [--query QUERY]
context expand --packet P --entry K@1
context scout --task T [--role public]
context curator --task T
```

task.json: task_id, project_id, goal, roles/applicability опциональны. proposals.json — JSON array. stdout JSON, ошибки stderr JSON и exit 2. Протокол не запускает subprocess/LLM ради записи или поиска. Shell-команды из памяти не исполняются. CLI/API должны давать одинаковое поведение.

## Автоматизированные lifecycle-команды

Перед реализацией adapter зафиксировано дополнение: `python -m harness --db PATH workflow start --input task.json --output DIR` создаёт store при отсутствии, выполняет reconcile очереди без LLM, затем begin binding и сохраняет по выбранным task.roles файлы `scout-ROLE.json` плюс `task.json` в новый DIR. Результат JSON содержит task_id/output/brief_paths. Если directory уже существует, команда явно отказывается до записи в него, не перезаписывает файлы. Тестирование продукта этим вызовом не активируется.

`workflow context --task T --role developer --input scout-selection.json --output DIR [--budget 1200]` проверяет selected_refs и сохраняет packet JSON + text в файлы с packet ID; возвращает packet_id/packet_path/text_path. Есть конкретный авторизованный packet, не просто summary моделью.

`workflow finish --task T --input outcome.json --output DIR` durable-queue outcome, reconcile и сохраняет `curator.json` в новый DIR, возвращает job_id/curator_path. Curator вызывается нативным агентом отдельно. `workflow ingest --task T --batch B --input proposals.json` делает propose+reconcile, возвращает enqueue и reconciliation; [] завершает curation с no_change. Все эти команды не запускают LLM/subprocess сами и не генерируют тесты. Это автоматизация детерминированных шагов.

Selected_refs с чужим/неизвестным ref — явный not_found, не молчаливое исключение. Explicit get_entry(revision=old) допускает историческую доступную revision при current active; expand старого packet после смены current revision отказывает.

## Gate MVP-1 → MVP-2 (выполнение)

Отдельный автор заранее пишет public tests по этому контракту; они не считаются private holdout. Требуются успешные public tests и post-hoc adversarial checks отдельного агента на snapshot. Проверить scopes, cutoffs, proposal states, evidence integrity, atomicity/retry, revisions, budgets, revoked packet sources и CLI lifecycle. До прохода gate semantic implementation не начинается. Baseline, hash файлов и результат gate сохраняются.

## Project-local stores и навигация (2026-11-03)

`project init/status/map/map-check` добавлены в общий CLI. В initialized проекте default DB определяется по ближайшему `.harness/knowledge/project.json` до Git root; --db/env имеют приоритет. Без профиля прежний global default сохраняется. Новый store имеет meta.project_id, begin_task отклоняет чужой project_id. Существующие unbound stores совместимы и не мигрируются автоматически. Schema_version остаётся 1: добавлена опциональная meta-запись, не изменены таблицы или payload существующих entries.

Workflow start подставляет project_id из bound DB, когда поле отсутствует. Он может добавить project_navigation в Scout brief из актуальной `.harness/code-map.json`; это отдельные selected-file hints, не factual retrieval. Knowledge packet и его budget не меняются. Детальные команды и ограничения: [project knowledge](../../skills/knowledge-cycle/references/project-knowledge.md).

## Автоматическая организация подпроектов (2026-11-03)

Добавлены optional tables subproject_catalog и task_organization (additive schema extension); существующие entries/tasks не переименовываются и не переносятся в другие DB. Workflow start принимает paths, сохраняет catalog snapshot и routing; workflow context принимает optional subproject_ids от Scout и фиксирует их до первого packet. Entry proposals имеют optional subproject_ids; классификация не меняет state, permissions или applicability. Lexical/semantic retrieval сохраняет eligible corpus и применяет небольшой ranking preference. Существующие get_task/projection ответы могут дополнительно содержать subprojects/subproject_ids. Низкоуровневый begin_task сам discovery не запускает. [Полный контракт](../../skills/knowledge-cycle/references/subprojects.md).

## Актуальность и maintenance (2026-11-11)

Поверх snapshot/scope действует срок 14 суток и проверка declared dependencies.
Expired/source-drift/dependency-stale исключаются из search/get/context/expand, включая
semantic/hybrid fallback. История не переписывается; export показывает effective stale,
persisted_state, freshness и expires_at. Packets дополнительно содержат expires_at.
Review approve начинает новый интервал; остальные state edits сохраняют прежний anchor.
General publication наследует оставшийся срок. Legacy human_review/release использует
recorded_at, остальные — min(observed_at,recorded_at); новые записи без observed_at —
время outcome, чтобы задержанный reconcile не продлевал срок.

Proposal.dependencies: {files:[relative_path],entries:[K@revision]}; Core сохраняет hashes.
`knowledge maintenance --task T [--limit 8]` — bounded fresh-agent brief с причинами
и dependency changes. `knowledge source --task T --path PATH` — hash выбранного файла.
`knowledge maintain --task T --input decisions.json` — атомарный batch renew/stale/retract
с expected_revision/rationale и проверенными source hashes. Renew не меняет claim/kind,
не повышает candidates и сохраняет обязательные зависимости. Source snapshots пишутся
в evidence, audit отмечает native agent review, не independent verification. Повтор старой
revision — conflict без продления. Stale maintenance повторяется через 14 дней;
human-stale не восстанавливается автоматически. General не входит в automatic maintenance.

`workflow start` возвращает maintenance_path/maintenance_due; preflight до основной
задачи описан в [skill](../../skills/knowledge-cycle/references/freshness.md).
[Дизайн и ограничения](../rfcs/006-knowledge-freshness.md). Фонового scheduler нет.
