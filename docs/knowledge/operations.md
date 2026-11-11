# Knowledge: рабочий цикл

Общее ядро — пакет `harness`, Python 3.11+, SQLite с FTS5. Без semantic extra стандартной библиотеки достаточно. Из корня репозитория работает `python3 -m harness`; после установки пакета — команда `harness`. Нативный переносимый skill: [knowledge-cycle](../../skills/knowledge-cycle/SKILL.md).

## Автоматизация

Скрипты делают ввод/вывод, проверку policy, budgets, citations, очередь, retries, индекс и receipt. Отдельным агентам остаются два решения: Scout выбирает полезные refs; Curator предлагает новые короткие записи. Ни обход каталога, ни сборка prompt, ни пересчёт индексов не требуют LLM. Каждый получает ограниченный brief, а разработчик — готовый packet. Тестирование этим циклом не включается.

```sh
python3 -m harness workflow start --input task.json --output .harness/tasks/T/start
# Native Scout получает scout-developer.json и возвращает selection.json.
python3 -m harness workflow context --task T --role developer --input selection.json --output .harness/tasks/T/packets
python3 -m harness evidence add --task T --path result.json --label verification
# В outcome.json указать фактический status и полученные evidence_ids.
python3 -m harness workflow finish --task T --input outcome.json --output .harness/tasks/T/finish
# Native Curator получает curator.json и возвращает proposals.json.
python3 -m harness workflow ingest --task T --batch B --input proposals.json
```

`task.json`: `{"task_id":"T","project_id":"engineering-harness","goal":"Конкретная задача","roles":["developer"]}`. Selection: `{"selected_refs":[]}` или до восьми refs. Outcome: `{"status":"success","evidence_ids":[],"summary":"Реальный итог"}`. Proposals: array по [контракту](../contracts/knowledge-mvp.md), в том числе `[]`, если полезного нового знания нет.

Добавляй public/adversarial в roles только при заказанном тестировании. Start сначала продолжает очередь, затем фиксирует snapshot. Новые сведения после snapshot не попадут в initial context этой задачи. Для следующей задачи используй новый ID. Обязательные инструкции читаются напрямую до RAG.

Start/finish требуют новый output directory, чтобы не затереть briefs. При повторе используй новое имя directory: состояние task/outcome/batch идемпотентно. После ошибки очередь остаётся в SQLite; папка briefs не источник истины.

## Подтверждение и восстановление

Без basis запись — candidate. Автоматически active становится только observation, буквально совпадающее с цитатой immutable evidence. Это цитируемое наблюдение источника, а не удостоверенная истина или универсальная рекомендация. Approve/general release требуют решения человека; вызовы не входят в автоматический цикл.

```sh
python3 -m harness knowledge pending --project engineering-harness
python3 -m harness knowledge reconcile
python3 -m harness context curator --task T
python3 -m harness knowledge export --project engineering-harness
```

`queued`/`curation_pending` не означают обновлённые знания. Проверяй receipts и `curation_status`. Ошибочный proposal исправляется новым batch ID; reuse прежнего ID с другим payload запрещён. Устаревшее expected_revision требует нового предложения на текущей версии.

В initialized проекте CLI выбирает `.harness/knowledge/knowledge.sqlite3` по cwd (также из подкаталогов). [Инициализация пустого проекта, карта кода и runbooks](../../skills/knowledge-cycle/references/project-knowledge.md). Legacy store при отсутствии project profile: `~/.local/share/engineering-harness/knowledge/knowledge.sqlite3`. Для испытаний всегда отдельный `--db PATH` перед командой. `HARNESS_KNOWLEDGE_DB` меняет default. Для резервной копии живой БД используй SQLite backup API, а не простое копирование только .sqlite3 при активном WAL. Экспорт project — читаемая проекция, не полный backup.

## Границы

Локальный cooperative profile фильтрует роли и проекты в API. Процесс с теми же правами filesystem способен прочитать SQLite; private backend отсутствует. Содержимое evidence сохраняется только из явно выбранных UTF-8 файлов; автоматического поиска секретов/доступа ко всем файлам нет. Сырые чаты не индексируются.

Native instructions описывают begin/finish, но не перехватывают любой аварийный выход. Durable outcome переживает закрытие сессии; pending Curator требует новой native agent session. Проектные entrypoints Codex/Claude подключены, live Claude evaluation пока не выполнена.

## MVP2: локальная модель и сравнение поиска

Для нового устройства используй `sh scripts/setup.sh`; [setup и ресурсный профиль](setup.md) описывает автоматическую установку, повтор и offline-режим. Ручные команды ниже остаются доступными.

`uv sync --extra semantic --locked` устанавливает воспроизводимое окружение. Явная `.venv/bin/python -m harness model-setup --output /new/bundle` скачивает публичную multilingual MiniLM (около 220 MB), фиксирует commit источника, hashes файлов, версии runtime и выполняет readiness probe. Обычные команды используют только локальные файлы; повреждённый или отсутствующий bundle даёт явный fallback. При изменении runtime нужен новый bundle/identity. Для очистки неудачной загрузки удаляй только свой незавершённый bundle либо выбери новый directory.

```sh
.venv/bin/python -m harness --semantic-model /path/to/bundle knowledge index
.venv/bin/python -m harness --semantic-model /path/to/bundle knowledge index-status
.venv/bin/python -m harness --semantic-model /path/to/bundle knowledge search --task T --query "запрос" --mode semantic
.venv/bin/python scripts/benchmark_knowledge.py --corpus evals/knowledge-mvp/2026-11-03/mvp2/retrieval-corpus.json --model /path/to/bundle --output /tmp/benchmark-UNIQUE
```

Модель имеет короткое входное окно: adapter разбивает текст по 96 model tokens, усредняет embeddings фрагментов и затем нормализует. Политика chunking входит в identity модели. Смена модели/версии/размерности не переиспользует чужие vectors. Cache хранит hash запроса и vector, имеет отдельный project namespace, ограничен 256 запросами на model/project. Он не отменяет проверку прав при выдаче. Изменённые revisions индексируются инкрементально; workflow start/ingest делает sync автоматически. Незавершённый индекс → lexical fallback с предупреждением, без молчаливого исключения новых записей.

В этой машине thin skill entrypoint использует проектную `.venv` и локальный `.harness/knowledge.local.json`: `{"semantic_model":"/path/to/bundle","mode":"semantic"}`. Env HARNESS_SEMANTIC_MODEL/HARNESS_RETRIEVAL_MODE и явные flags имеют приоритет. Профиль исключён из Git: абсолютные пути не переносятся. Без него default остаётся lexical. Пилотный semantic выбран после небольшого development comparison; hybrid сохранён для сравнения, а не объявлен лучшим по определению.

Базовый поиск обходит текущие metadata в Python, vector ranking — exact cosine scan. Это простой локальный MVP для небольшого корпуса; масштаб в десятки/сотни тысяч записей и p95 под нагрузкой пока не измерены. Нет hosted vector DB, отдельного сервера, LLM reranker или изменения agent loop. Совпадение по смыслу не подтверждает истинность записи; policy и evidence проверяются отдельно.

Источники реализации backend (просмотрены 2026-11-03): [FastEmbed API](https://qdrant.github.io/fastembed/Getting%20Started/), [supported models](https://qdrant.github.io/fastembed/examples/Supported_Models/), [offline/local model options](https://github.com/qdrant/fastembed/blob/main/fastembed/text/text_embedding.py). В установленной версии 0.9.1 проверены реальные API и локальный запуск.

## Отдельный новый проект

```sh
harness project init --root /absolute/path/to/project --id my-project
harness project status --root /absolute/path/to/project
```

Init не импортирует знания, не очищает существующую базу и не включает agent hooks. Модель embeddings может быть общей для разных SQLite. Подробнее: [project-knowledge.md](../../skills/knowledge-cycle/references/project-knowledge.md).

## Пересмотр раз в 14 суток

Перед основной задачей выполняй [maintenance preflight](../../skills/knowledge-cycle/references/freshness.md).
Не удаляй просроченные записи и не обновляй дату массовым approve. `knowledge maintenance`
показывает due/remaining и текущие dependency changes; `knowledge maintain` сохраняет
содержательное решение с evidence. После обновлений нужен новый task snapshot.
