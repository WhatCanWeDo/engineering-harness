# Engineering Harness

Персональная переносимая engineering harness система для applied ML: общее ядро, тонкие адаптеры и нативные интерфейсы coding agents.

В репозитории есть переносимые skills и локальный Knowledge Core на Python/SQLite. Исходная архитектура RFC 001 сохраняет статус **Draft v0.1** от 2026-11-03; реализация отдельных MVP не означает принятия всего RFC.


## Установка на другой MacBook

```sh
git clone https://github.com/WhatCanWeDo/engineering-harness.git
cd engineering-harness
sh scripts/setup.sh
.venv/bin/python scripts/doctor.py
```

Приватный репозиторий требует авторизации GitHub. Общий setup устанавливает **8 skills** для
Codex/Claude, managed Python, Knowledge Core и локальную embedding-модель. Новое устройство
начинает с **пустой базы**; накопленные знания, credentials и локальные настройки не переносятся.
[Полная инструкция и ограничения](docs/install-macos.md).

## Документы

- [RFC 001 — Native-First, Agent-Agnostic Engineering Harness](docs/rfcs/001-native-first-agent-agnostic-engineering-harness.md) — полный исходный документ.
- [RFC 002 — Тестирование по запросу](docs/rfcs/002-test-on-request.md) — public/private/adversarial, защита holdout и раскрытие контрпримеров.
- [RFC 003 — Knowledge & Context Layer](docs/rfcs/003-knowledge-context.md) — общий store, поиск, отдельные Scout/Curator, role packets и обновление после задач. Архитектурный дизайн; реализованный scope описан в контрактах MVP1/MVP2.
- [RFC 006 — Актуальность знаний](docs/rfcs/006-knowledge-freshness.md) — срок 14 суток, зависимости и содержательный пересмотр отдельным агентом.
- [RFC 005 — Visualization](docs/rfcs/005-visualization.md) — дизайн skill-роутера для честных интерактивных демо; учебные прототипы image/mask и parser trace в `docs/explainers/011-visualization`. Устанавливаемый instruction-based skill находится в `skills/visualization`; универсальный renderer/live backend пока не реализованы.
- [План проектирования](docs/design-plan.md) — предложенный порядок следующих обсуждений и критерии готовности первого прототипа.
- [Общие инструкции проекта](docs/project-instructions.md) — канонические инструкции для работы над репозиторием.
- [Оценка качества skills](docs/skill-evaluation.md) — предложенные критерии, evidence и процедура проверки.

## Первый skill

[understand-changes](skills/understand-changes/SKILL.md) создаёт автономный HTML с объяснением изменений и пятью вопросами на понимание. Частота и глубина настраиваются; по умолчанию объяснение выдаётся в конце задачи со средней глубиной, после чего агент ждёт пользователя.

Результат выдаётся обычной HTTP-ссылкой прямо в чате через локальный preview одного документа. Пользователь подтвердил этот способ; файловая ссылка в его интерфейсе не открылась. Preview по умолчанию живёт два часа, а сам HTML хранится постоянно вне репозитория. Старый разбор можно открыть снова, запустив preview без повторной генерации quiz. См. [выдачу и открытие HTML](skills/understand-changes/references/delivery.md).

[Независимая проверка от 2026-11-03](docs/evaluations/understand-changes-2026-11-03.md): найденные дефекты исправлены и перепроверены; текущий статус — кандидат для личного пилота.

В skill входят переносимые инструкции и Python-утилиты без сторонних зависимостей. Технические проверки запускаются из корня репозитория:

```sh
python3 -m unittest discover -s tests -v
```

## Второй skill

[test-on-request](skills/test-on-request/SKILL.md) v0.1 реализует тестирование по явному запросу: public и adversarial генерируют отдельные агенты с минимальным контекстом. CLI без сторонних зависимостей готовит plan/brief, копирует candidate и проверяет его digest. Private возвращает unavailable до подключения защищённого evaluator; лимиты пока advisory.

Проектные entrypoints подключены: Codex `$test-on-request`, Claude Code `/test-on-request` (новая сессия из этого репозитория). Общая логика хранится в `skills/test-on-request`; Claude entrypoint и worker — тонкие указатели. Live-переносимость на Claude ещё не проверена. Общий setup также устанавливает пользовательские entrypoints и workers.

Примеры запросов: «подготовь публичные тесты до реализации по этому контракту», «атакуй готовую функцию, продукт не меняй», «запусти существующий набор». [Команды и форматы](skills/test-on-request/references/execution.md), [делегирование](skills/test-on-request/references/native-adapters.md).

```sh
python3 skills/test-on-request/scripts/testing.py --help
python3 -m unittest discover -s tests -p 'test_test_on_request.py' -v
```

## Fork в новой вкладке Ghostty

[fork-tab](skills/fork-tab/SKILL.md) создаёт ветку точной сессии в новой вкладке того же
окна на macOS. Установка: `sh scripts/setup.sh`; после загрузки skills
Codex — `$fork-tab`, Claude Code — `/fork-tab`. Общий CLI — `~/.local/bin/fork-tab`.
Нативный `/fork` не переопределяется. Если daemon не позволяет определить исходное
окно и открыто несколько окон Ghostty, нужен явный `--window` из `--list`.
[Использование и ограничения](skills/fork-tab/references/usage.md),
[проверка интеграции](docs/evaluations/fork-tab-2026-11-06.md),
[исправления и подтверждённый реальный fork Codex](docs/evaluations/fork-tab-fix-2026-11-06.md).

## Архитектурное направление

Codex CLI и Claude Code остаются пользовательскими точками входа. Общие skills, workflows, evaluators и форматы артефактов принадлежат переносимому ядру. CLI и опциональный MCP используют одну реализацию. Независимая проверка и обязательные ограничения располагаются за пределами agent loop.

Interactive mode — основной сценарий. Managed orchestration — дополнительная возможность по мере появления подтверждённой потребности.

## Работа над дизайном

RFC 002 посвящён тестированию по запросу, RFC 003 — общей памяти и подготовке контекста. Интерактивный HTML-дизайн RFC 003 собирается командой `python3 docs/explainers/004-knowledge-context/build.py`; в нём диаграммы, демонстрация отбора по роли/бюджету и quiz. Минимальный Portable Foundation остаётся отдельной предлагаемой темой: один сквозной сценарий, границы первой версии, минимальный контракт адаптера и установка общих skills.

Новые RFC размещаются в `docs/rfcs/` с последовательными номерами. Статус Draft сохраняется до явного принятия решения. Принятые отдельные архитектурные решения можно фиксировать в `docs/adr/` по мере их появления.

## Knowledge MVP1 и MVP2

[knowledge-cycle](skills/knowledge-cycle/SKILL.md) подключён к этому проекту. SQLite хранит evidence, immutable revisions, tasks и durable queue; FTS5 и optional локальные embeddings готовят компактные role packets. Отдельные native Scout/Curator получают готовые briefs. Private backend отсутствует; общий installer адаптеров — `scripts/install_skills.py`.

Знания имеют срок актуальности **14 суток**. Просроченные записи сохраняются в истории, но исключаются из контекста. При обращении к проекту отдельный Maintenance Curator проверяет source/spec/lockfiles и связанные записи; подтверждение продлевает срок, неопределённость оставляет запись вне выдачи. [Поведение и команды](skills/knowledge-cycle/references/freshness.md). Фонового таймера нет.

[Рабочие команды и восстановление](docs/knowledge/operations.md), [MVP1 API](docs/contracts/knowledge-mvp.md), [MVP2 API](docs/contracts/knowledge-mvp2.md), [проверки и результаты](docs/evaluations/knowledge-mvp-2026-11-03.md).

```sh
python3 skills/knowledge-cycle/scripts/knowledge.py --help
python3 scripts/check_knowledge.py --stage all --output /tmp/harness-check-UNIQUE
```

Базовое ядро не требует зависимостей. Для semantic extra: `uv sync --extra semantic --locked`, затем `.venv/bin/python -m harness model-setup --output /new/model/bundle`. Модель загружается только этой явной командой; поиск выполняется локально. `uv.lock` фиксирует зависимости. Локальный bundle и профиль подготовлены на этой машине; на другой машине нужен свой путь, см. operations.


## Новое устройство

```sh
sh scripts/setup.sh
```

Setup устанавливает Python/locked dependencies, локальную embedding-модель, все skills и native adapters, измеряет ресурсы и записывает профиль. [Инструкция, повторный/offline setup и требования к ресурсам](docs/knowledge/setup.md). GPU не требуется; ориентиры: 3 GiB свободного диска на установку и ~2 GiB доступной RAM на embedding-процесс. Bootstrap: macOS/Linux/WSL; проверено на macOS arm64.

## /harness-ab

[harness-ab](skills/harness-ab/SKILL.md) реализует локальный A/B MVP: immutable plan/config snapshots, balanced schedule, native-session assignments, F0/F1, receipts, независимый evaluator transport, human timer и deterministic paired HTML/JSON. [RFC 004](docs/rfcs/004-harness-ab.md) принят как направление 2026-11-03; [точные команды и контракты](skills/harness-ab/references/protocol.md) описывают текущий scope.

```sh
python3 -m harness ab --help
python3 scripts/demo_harness_ab.py --output /tmp/new-ab-demo
```

Demo синтетический: без моделей и человеческих замеров. Для настоящего сравнения нужны task suite, baseline/candidate, бюджет и fresh sessions. Проектные entrypoints: Codex `$harness-ab`, Claude `/harness-ab`. Automatic native launch, protected holdout и provider billing integration пока отсутствуют; isolation attestations и native budgets не являются внешним enforcement. [Человеческий review и открытие HTML](skills/harness-ab/references/review.md).

[Проверки local A/B MVP и ограничения](docs/evaluations/harness-ab-mvp-2026-11-03.md). Итоговое объяснение с пятью вопросами: `docs/explainers/008-harness-ab-mvp/content.json`, рендерится общим understand-changes helper.

## Проектные базы и карта кода

`harness project init --root /absolute/project --id my-project` создаёт отдельную пустую SQLite. CLI выбирает её по cwd; повторный init сохраняет данные. `project map` фиксирует выбранные файлы/хеши/Python symbols, `project map-check` обнаруживает изменения. Назначение сервисов и how-to хранятся как обычные evidence-backed facts/procedures, а не выводятся автоматически из дерева файлов. [Рабочий сценарий и ограничения](skills/knowledge-cycle/references/project-knowledge.md).

## Автоматические подпроекты

Knowledge workflow сам выделяет компоненты по структуре репозитория и темы по повторяющимся предметным tags. Задачи могут быть общими или относиться к нескольким группам; вся память остаётся в одной SQLite проекта. Scout может уточнить affiliation без дополнительного LLM-вызова, а поиск сохраняет доступ к знаниям соседних подпроектов. [Поведение и ограничения](skills/knowledge-cycle/references/subprojects.md). Просмотр: `harness knowledge subprojects --project PROJECT_ID`; отдельная инициализация подпроектов не требуется.


## /spec-init

[spec-init](skills/spec-init/SKILL.md) готовит постановку сложной задачи до реализации: свежий Scout по проектной памяти, фиксированный **ML Task Spec v1**, Markdown и автономный HTML с обзорной схемой, пробелами, временными решениями и пятью вопросами. Формат адаптирован к ML engineering: данные/leakage, baseline, протокол оценки, uncertainty, ресурсы, воспроизводимость и operations; неприменимые разделы объясняются.

JSON — канонический источник; renderer проверяет R → AC, источники и unknown → gap, связывает KB refs с packet и записывает digest. HTML позволяет отметить непонимание и скопировать автоматически собранный текст поправок в чат. Review/quiz не утверждают спеку и не запускают реализацию. [Контракт](skills/spec-init/references/format.md), [обоснование и первичные источники](skills/spec-init/references/research.md), [пример ML-задачи](skills/spec-init/assets/ml-example.json).

В проекте подключены указатели `.agents/skills/spec-init` и `.claude/skills/spec-init`: вызов `$spec-init` / `/spec-init` соответственно после обнаружения skill в новой сессии. Сквозной запуск в Claude пока не проверен. Пользовательские entrypoints устанавливаются общим setup.

```sh
python3 skills/spec-init/scripts/spec.py scaffold --request request.txt --project PROJECT_ID --id TASK_ID --title 'Название задачи' --output draft.json
python3 skills/spec-init/scripts/spec.py validate draft.json
python3 skills/spec-init/scripts/spec.py build draft.json --packet context-packet.json --output docs/specs/TASK/r1
```

Scaffold требует наполнения агентом; packet готовится через существующий knowledge-cycle. При недоступности scouting возможен явно обозначенный degraded draft. Для примера с unavailable scouting `--packet` опускается.

## Контроль границ изменений

[scope-guard](skills/scope-guard/SKILL.md) помогает учитывать новые ограничения пользователя,
защищённые объекты и побочные эффекты перед изменениями внешних систем и общих ресурсов.
При неопределённости приостанавливается затронутое изменение; независимая разрешённая работа
может продолжаться. Общий профиль включает skill по умолчанию перед изменениями во всех проектах;
для простой локальной правки достаточно краткой сверки. Ручной вызов также доступен:
Codex `$scope-guard`, Claude `/scope-guard`; skill включён в общий installer.

Это инструкции агенту, а не техническая блокировка операций или гарантия безошибочного
понимания. [Требования к независимому исполнителю](skills/scope-guard/references/enforcement.md)
описаны отдельно; такой исполнитель этим skill не устанавливается.
