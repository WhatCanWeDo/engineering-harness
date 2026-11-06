# Проектные знания: карта кода, сервисы и рабочие инструкции

Knowledge Core уже хранит observation/decision/procedure/hypothesis/negative_result/preference с project scope, evidence, revisions, tags, symbols и applicability. Это позволяет отвечать «где находится обработчик?», «какой сервис создаёт результат?» и «как воспроизвести workflow?». Но запись появилась в базе только если её действительно внесли; наличие RAG не означает полного знания всего репозитория.

Разделяй два вида материала:

- **Генерируемая навигационная карта.** Пути, hashes, Python classes/functions/methods и line numbers. Это механическое извлечение; не архитектурная интерпретация и не доказательство актуального deployment.
- **Содержательные знания.** Назначение компонентов, связи с сервисами, условия и последовательности действий. Для них нужны исходники, config/docs, observations и review. Их хранит обычная Knowledge DB, а не отдельная конкурирующая карта.

## Пустая база нового проекта

Из установленного окружения:

```sh
harness project init --root /absolute/path/to/project --id my-project
harness project status --root /absolute/path/to/project
```

Или `python3 /path/to/engineering-harness/skills/knowledge-cycle/scripts/knowledge.py project init ...`.

Root — уже существующий каталог. Создаются `.harness/knowledge/project.json`, `knowledge.sqlite3` и ignore rule для SQLite/WAL. Никаких tasks, evidence, entries, queues или packets при init нет. Semantic index также пуст. Автосканирования и копирования чужой базы нет. `project_id` стабилен и не зависит от названия папки. Profile можно версионировать; SQLite игнорируется. В клоне с profile, но без DB повторный явный init создаст пустую DB с тем же ID. Это не восстановление старых знаний.

Повторный init с теми же ID/mode сохраняет данные; другой ID/mode даёт conflict. Он никогда не служит reset. Existing current shared database не мигрируется и не очищается. Для переноса накопленного знания нужен отдельный выбранный migration/backup workflow, а не переименование project_id.

После init CLI и thin skill wrapper находят ближайший project profile, поднимаясь от cwd до Git root. Из nested независимого Git repo родительский профиль не наследуется. Явный `--project-root /path` перед командой выбирает другой initialized project, когда cwd вне него.

Приоритет database: `--db` → HARNESS_KNOWLEDGE_DB → project DB → legacy global store (только если project profile не найден). Явное перенаправление полезно для A/B run-local store. Project DB связана с project_id в meta; чужой task binding отклоняется. Отсутствующая DB при найденном profile не приводит к тихому fallback в global store.

`workflow start` может получить task.json без project_id: в bound project DB подставится её ID. В unbound legacy store ID по-прежнему обязателен. Одинаковый task_id допустим в разных физических DB.

Модель embeddings не требуется дублировать на проект. Wrapper может использовать установленный shared runtime bundle; mode нового проекта по умолчанию lexical. `project init ... --mode semantic` выбирает semantic для workflow start при доступной модели; можно передавать `--semantic-model PATH` или HARNESS_SEMANTIC_MODEL. Init модель не скачивает.

Разные project DB не читают друг друга. General releases из старого общего store **не федератируются автоматически**: межбазовая доставка разрешённого general знания пока отдельная будущая возможность. Чистый новый проект действительно пуст.

Init настраивает хранилище и CLI, но не перезаписывает AGENTS.md/CLAUDE.md и не устанавливает global skills. В новом проекте явно вызови canonical knowledge-cycle либо включи цикл в инструкциях проекта. Доступность переносимого skill в native session остаётся задачей установки адаптера.

## Карта выбранных файлов

Подготовь JSON file list через обычный `rg --files` с нужным scope. Включай релевантные исходники, entrypoints, docs и несекретные конфигурации; не дамп credentials, logs и datasets. Например:

```json
["src/client.py", "src/jobs.py", "docs/services.md"]
```

```sh
harness project map --root /absolute/project --files selected-files.json --output /absolute/project/.harness/code-map.json
harness project map-check --root /absolute/project --input /absolute/project/.harness/code-map.json
harness project map --root /absolute/project --files selected-files.json --output /absolute/project/.harness/code-map.json --refresh
```

Нет вызова LLM или исполнения кода. До 1000 явно выбранных regular files, до 2 MiB/file; symlinks/traversal исключены. Python AST извлекает top-level classes/functions и class methods, не call graph. Для остальных языков — file inventory. Symbol cap 300/file с явным method=python_ast_truncated. Hash mismatch/missing → stale; `--refresh` явно заменяет только generated map. Добавление нового файла вне списка не обнаруживается: обновляй список при расширении scope.

В initialized project `workflow start` проверяет стандартный `.harness/code-map.json` и добавляет Scout `project_navigation`: максимум шесть совпавших файлов, до десяти symbols/file. Подсказки строятся по словам задачи. Устаревшая карта не даёт matches, только статус/изменённые пути. Это отдельная навигационная подсказка, не запись RAG и не retrieved factual claim. Scout может кратко передать полезные пути в caveats; developer читает реальные файлы. Готовый knowledge packet не пополняется произвольным текстом Scout, его собственный budget остаётся прежним.

Map не заполняет DB автоматически. Чтобы сохранить подтверждённую проектную информацию, добавь выбранные source excerpts как evidence и передай Curator. Raw map может быть evidence, но файл карты ограничен общим evidence лимитом; для большой карты выбери компактный фрагмент. Карта не заменяет архитектурные документы.

## Какие записи поддерживать

**Code location:** title «Где формируется manifest», kind observation, claim с точным путём/символом и ролью, symbols `["src/jobs.py", "JobRunner.submit"]`, tags `["code-map","jobs"]`. Номер строки — подсказка на конкретном hash, не постоянный идентификатор.

**Service fact:** observation о назначении сервиса, interface/environment, источнике конфигурации и владельце. URL без credentials допустим, токены и значения secrets — нет. Из документа следует лишь документированная роль; фактическая доступность требует отдельного наблюдения.

**How-to / runbook:** procedure, один конкретный желаемый результат; prerequisites → какие сервисы/команды → expected output → как проверить успех → известные ограничения. Например «получить benchmark report»; укажи job submission endpoint и artifact store только когда они подтверждены исходниками/config/выполнением. Не выполняй инструкции из памяти как новые полномочия: deployment/внешние записи всё равно требуют пользовательского scope.

**Открытая работа:** decision или hypothesis с явно незавершённым состоянием и ссылкой на issue. Нельзя сохранять «сделать X» как факт «X работает». Эта DB не заменяет issue tracker.

После задачи Curator рассматривает изменённые расположения, сервисные связи и повторяемые процедуры вместе с результатами экспериментов. При известной прежней записи передавай entry_id/expected_revision и source evidence, чтобы обновить revision вместо дубликата. Предыдущие claims не становятся проверенными автоматически. Не сканируй весь проект после каждой правки: обновляй затронутый scope и проверяй source hashes.

Procedure/интерпретация остаётся candidate до разрешённого review. Exact source-excerpt observation может стать active автоматически, но означает «источник сообщает», а не доказанную истинность поведения. Map-check не отзывает автоматически все старые KB entries: это сигнал агенту проверить зависимые факты и предложить revision/stale через принятую процедуру.

## Подпроекты без ручной регистрации

Внутри одной DB workflow теперь автоматически обнаруживает компоненты и повторяющиеся темы, связывает с ними задачи и знания. Никаких отдельных subproject init. [Автоматическая организация, общий поиск и snapshot](subprojects.md). Эти мягкие affiliations отделены от строгого applicability.
