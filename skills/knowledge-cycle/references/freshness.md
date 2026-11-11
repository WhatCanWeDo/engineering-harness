# Актуальность: 14 суток и содержательный пересмотр

Срок = 14 × 24 часа UTC. На границе expires_at знание уже недействительно. Из поиска,
get и expansion оно исключается без удаления истории. Source drift или устаревшая
связанная запись исключают его раньше. Чтение, export, embeddings, retry и general
publication не продлевают срок. Исторический snapshot не отменяет текущую просрочку.

## Нативный цикл

1. До основной задачи создай отдельный task binding, например `T-maintenance`, с
   project_id и roles:["developer"] через `task begin --input maintenance-task.json`.
   Затем `knowledge maintenance --task T-maintenance --limit 8`.
2. Если due=0, отдельный LLM не нужен. Если есть записи, передай brief **отдельному
   свежему native Maintenance Curator**, fork_turns:none. Не передавай весь чат.
   Он читает текущие файлы и зависимости в разрешённом проекте, проверяет спецификации,
   версии API/lockfiles, условия применимости, статус связанных решений. При unknown
   находит недостающие источники. Неизменный hash не доказывает смысл claim.
3. Для рассмотренных файлов агент получает актуальные hashes командой
   `knowledge source --task T-maintenance --path src/module.py` и читает файлы.
   Передай JSON решений в `knowledge maintain --task T-maintenance --input decisions.json`.
   Core проверит current revisions/hashes, обязательные зависимости и сохранит source
   snapshots в evidence. При conflict подготовь новый brief, не подставляй свежий hash
   в старое неподтверждённое решение. Сначала пересматривай upstream knowledge, затем
   зависимые записи отдельным batch. Сравни receipts с реальными решениями.
4. Запроси следующий brief: due отражает всё ещё просроченное, remaining — записи за
   пределами batch. Не скрывай backlog; при ограниченном бюджете можно продолжить
   основную работу без непроверенных записей. Успешный renew даёт следующие 14 дней;
   stale оставляет запись вне выдачи и откладывает следующую попытку на 14 дней.
5. Заверши maintenance task через обычные `task finish` + `knowledge reconcile`;
   для bookkeeping допускается пустой `knowledge propose --batch no-new-claims --input empty.json`
   и reconcile: уже сохранённые решения повторно Curator не пересказывает.
   Только после этого запускай основную задачу с новым task_id/snapshot.

`workflow start` дополнительно выдаёт maintenance_path/maintenance_due. Если preflight
был пропущен, обработай brief до Scout, заверши служебную задачу и создай новую основную:
старый snapshot нельзя незаметно расширить обновлёнными знаниями. Если developer role
не разрешена, обычный role packet не получает maintenance-информацию.

Проверка выполняется при следующем обращении к проекту после 14 суток. Это не фоновый
scheduler: выключенный компьютер/закрытый агент не запускает пересмотр. При отказе
агента due остаётся durable в датах/состояниях записей. Общие general releases не
переподтверждаются из чужого проекта; их явный review остаётся отдельной операцией.

## Формат решения

```json
[{
  "entry_id": "K-example",
  "expected_revision": 1,
  "decision": "renew",
  "rationale": "Текущий source и lockfile по-прежнему подтверждают прежний claim при указанных условиях.",
  "dependencies": {
    "files": [{"path": "src/module.py", "sha256": "HASH_FROM_SOURCE_COMMAND"}],
    "entries": []
  }
}]
```

Renew не меняет claim/kind и не превращает candidate в active. Допустим для ранее active,
включая отложенный maintenance-stale; human-stale требует отдельного разрешённого review.
Нужны хотя бы один содержательный источник и rationale, прежние paths/knowledge IDs
нельзя тихо выбросить. Core проверяет механику, а не семантическую истинность рассуждения.
Audit явно отмечает native agent review, не независимое доказательство.

При опровержении — retract; при недостаточной информации — stale. Для исправленного
claim подготовь обычный proposal с entry_id/expected_revision и новым evidence;
обобщение остаётся candidate до review. Не делай blanket approve всех просроченных.

## Новые знания и зависимости

В обычном proposal добавляй `dependencies:{files:["src/module.py","uv.lock"],entries:["K-other@2"]}`.
Указывай выбранные source/spec/config/lockfiles и известные связи. Core фиксирует hashes.
Только относительные regular UTF-8 files до 2 MiB, максимум 20 файлов и 20 entry refs;
symlinks/traversal, .git/.harness, .env*, .pem/.key запрещены. Это не полный secret scanner:
выбирать несекретные источники — обязанность агента. Не делай dependency на всю БД.

Legacy записи получают срок по прежним recorded_at/observed_at, без массовой миграции
и подаренных 14 дней. Экспорт показывает persisted_state, effective state, freshness,
expires_at и maintenance audit. Истёкшие записи без источников имеют coverage:unknown.
Неизвестные внешние API/окружение проверяются агентом только в разрешённом scope;
при недоступности не выдавай их за проверенные.
