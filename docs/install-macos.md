# Установка на другой MacBook

## Быстрый старт

Нужны Git и интернет. Codex CLI / Claude Code и их авторизация устанавливаются отдельно;
Ghostty нужен только для `fork-tab`. Начальная установка harness не запускает LLM-сессии,
не включает камеру и не переносит накопленную память.

```sh
git clone https://github.com/WhatCanWeDo/engineering-harness.git
cd engineering-harness
sh scripts/setup.sh
.venv/bin/python scripts/doctor.py
```

Репозиторий приватный: Git должен иметь доступ к GitHub account. При использовании GitHub CLI
можно сначала выполнить `gh auth login`, затем `gh repo clone WhatCanWeDo/engineering-harness`.
Не вставляй access token прямо в URL. GitHub, Codex и Claude требуют отдельных входов.

Setup устанавливает managed Python 3.12, зависимости из `uv.lock`, локальную embedding-модель,
восемь skills и два Claude worker. Он создаёт пустую глобальную БД, если её ещё нет; существующая
локальная БД не стирается. Никакого скачивания старой базы или seed-импорта нет.

## Что будет доступно

| Skill | Codex | Claude | Реализованный scope |
|---|---|---|---|
| Объяснение изменений | `$understand-changes` | `/understand-changes` | HTML, настройки частоты, пять вопросов |
| Тесты по запросу | `$test-on-request` | `/test-on-request` | Public/adversarial отдельными агентами; protected private backend пока unavailable |
| Знания | `$knowledge-cycle` | `/knowledge-cycle` | SQLite/FTS5, local semantic search, Scout/Curator, проекты/подпроекты |
| A/B skills | `$harness-ab` | `/harness-ab` | Локальные планы/receipts/отчёты; запуск native sessions по протоколу |
| Спецификация | `$spec-init` | `/spec-init` | ML Task Spec, scouting, HTML review и quiz |
| Визуализация | `$visualization` | `/visualization` | Instruction-based router и recipes; HTML создаёт агент, универсального renderer нет |
| Ветка чата | `$fork-tab` | `/fork-tab` | macOS/Ghostty, новый tab в том же окне, точный session UUID |
| Границы изменений | `$scope-guard` | `/scope-guard` | Актуальные разрешения, исключения и побочные эффекты; advisory, без технической блокировки |

По умолчанию подключаются оба агента. Для одного: `sh scripts/setup.sh --agents codex`
или `--agents claude`. Агент может потребовать обновления списка skills/перезапуска.
CLI доступны как `~/.local/bin/harness` и `~/.local/bin/fork-tab`; shell PATH не меняется.

## Установка и пользовательские файлы

Codex получает ссылки в `~/.agents/skills` (при явном CODEX_HOME — его `skills`). Claude —
генерируемые wrappers в `~/.claude/skills` и ссылки на workers в `~/.claude/agents`.
`CLAUDE_CONFIG_DIR` учитывается. Предметная логика хранится только в checkout.

В `~/.codex/AGENTS.md` и `~/.claude/CLAUDE.md` добавляется block между
`engineering-harness:start/end`, с указателем на [личный профиль](installation-profile.md).
Он подключает правила Knowledge Cycle для инициализированных проектов, тестов по запросу
и предложения visualization. Остальные инструкции сохраняются. Это advisory дисциплина,
не гарантированный lifecycle hook.

Installer проверяет конфликты до записи. Он обновляет только собственные неизменённые wrappers
по receipt `~/.local/share/engineering-harness/install.json`; чужие файлы и вручную изменённые
wrappers не перезаписывает. Незнакомые конфликты нужно разобрать явно. Старые ссылки fork-tab
на этот же checkout мигрируются, вложенный Claude skill больше не дублируется в Codex.

Checkout должен оставаться на месте. После его перемещения или обновления запусти:

```sh
git pull --ff-only
sh scripts/setup.sh
```

Все установки используют managed Python через launchers/profile. Системный Python и shell
profiles не меняются. Runtime и generated wrappers могут содержать абсолютные пути **нового**
устройства: они регенерируются installer, не копируются из Git.

## Новая пустая база проекта

```sh
~/.local/bin/harness project init --root /absolute/path/to/project --id my-project
~/.local/bin/harness project status --root /absolute/path/to/project
```

Проект получает `.harness/knowledge/project.json` и отдельную SQLite; последующие вызовы CLI
из его каталога выбирают её. Подпроекты обнаруживаются автоматически и используют ту же БД.
Init по умолчанию lexical; чтобы использовать установленную локальную модель, укажи
`--mode semantic` при init. Проверь `project init --help` перед сменой режима существующего проекта.

Текущая накопленная база, история задач, notebooks/results вне checkout, локальные model bundles,
credentials и пользовательские preferences **не находятся в Git и не переносятся**.
Перенос знаний возможен только по отдельному явному запросу. Наличие semantic index не означает,
что в новой базе есть знания: она начинает пустой. Личные настройки understand-changes по умолчанию
берутся из версионированного defaults (task_end, medium, HTML, 5 вопросов).

## Ресурсы и варианты

GPU не нужен. Ориентиры: 3 GiB свободного диска на runtime/model/cache; примерно 2 GiB доступной
RAM на embedding-процесс. Модель около 255 MiB. Setup измеряет фактический inference/RSS;
[подробности ресурсов](knowledge/setup.md). Проверенная платформа — macOS arm64; Intel Mac
не проверен и зависит от доступности wheels закреплённых dependencies.

```sh
sh scripts/setup.sh --lexical-only       # без embedding-модели; skills и FTS5 остаются
sh scripts/setup.sh --offline           # только при наличии всех caches/bundle
sh scripts/setup.sh --skip-skills       # только Knowledge runtime
.venv/bin/python scripts/install_skills.py --dry-run
```

На новом устройстве сначала нужен online setup. Offline не означает наличие модели внутри Git.
Agents/Ghostty могут отсутствовать при setup; doctor помечает это warning, а не делает вид,
что соответствующий интерфейс проверен. Для fork-tab проверены Ghostty 1.4.0 и Codex 0.167.0;
настоящая загрузка истории Claude пока не проверена.

## Проверка переносимости

Проверки выполняются на временном fresh Git clone и отдельном `--home`, без подмены HOME,
без чтения/копирования накопленной БД и без запуска agent sessions. Режим проверки installer:

```sh
.venv/bin/python -m unittest discover -s tests -p test_installation.py -v
.venv/bin/python scripts/check_portability.py --output /tmp/new-harness-install-check
```

Это отдельная явно запускаемая проверка, setup сам regression suite не выполняет.
Отчёт текущей проверки: [portable-install](evaluations/portable-install-2026-11-06.md).
