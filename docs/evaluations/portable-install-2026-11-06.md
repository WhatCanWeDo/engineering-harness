# Переносимость установки — 2026-11-06

Проверена локальная установка на macOS 15.7.3 arm64 / managed Python 3.12.14.
Начальная ревизия для fresh clone: `cdd5efc`.

## Подтверждено

- Создан настоящий Git clone из коммита, без `.venv`, runtime profile, локальной БД и модели.
  Checkout и отдельный target home содержат пробелы в путях. HOME процесса не подменялся.
- Полный setup с semantic dependencies прошёл; повторный offline setup тоже прошёл.
  Первый проход использовал существующий совместимый model bundle. Затем online setup загрузил
  новый bundle в отдельный каталог и выполнил реальный inference/resource probe.
- Doctor в clone возвращает ready: семь skills, managed Python, Core/FTS5, model manifest,
  native adapter paths и installer receipt без ошибок. Launcher работает из каталога вне repo.
- Global БД и отдельно созданная project БД содержат ноль tasks, entries, evidence, revisions,
  jobs и packets. Накопленная пользовательская БД не читалась/не копировалась для этой проверки.
- Независимый агент создал `tests/test_installation.py`; все 10 regression checks прошли.
  Проверены идемпотентность, два native набора, workers, сохранение чужих инструкций/skills,
  отказ до записи при конфликтах, dry-run, legacy migration, launcher без Python в PATH,
  создание пустой БД. Его замечание об env override в изолированном --home исправлено.
- Семь канонических SKILL.md прошли штатный validator. У visualization проверен формат
  instruction-based router; universal renderer/live backend и предметный production pilot не заявлены.
- Staged Git audit: нет runtime DB/model files, личных `.harness` данных и внешних/битых symlinks;
  проверка распространённых credential-patterns не нашла совпадений. Это не математическая
  гарантия отсутствия всех возможных секретов.
- Единый installer применён также к текущему пользовательскому окружению; doctor ready.
  Накопленная база не перенесена и не очищена.

## Автоматизация и пределы

`scripts/check_portability.py --output NEW_PATH` повторяет fresh clone, setup/repeat,
doctor и проверку пустых баз. `--offline --model-dir EXISTING_BUNDLE` использует локальные
caches; `--lexical-only` исключает модель. Скрипт проверяет **закоммиченный HEAD**, не unstaged edits.

Это проверка изоляции установки на той же машине, а не физического второго MacBook.
uv/Python/package caches могли переиспользоваться. Intel Mac не испытан. Авторизацию новых
Codex/Claude/GitHub нужно выполнить отдельно; повторный live Claude fork не запускался.
По явному выбору пользователя никакой snapshot накопленных знаний не создаётся и не публикуется.

Финальный автоматизированный прогон `check_portability.py` на ревизии `642b482`:
clone, setup, setup-repeat, doctor, project-init — passed; global/project БД пусты.
Использованы offline caches и bundle, успешно скачанный отдельным online прогоном выше.
После этого прогона менялся только этот отчёт. Приватность
`WhatCanWeDo/engineering-harness` подтверждена GitHub API перед отправкой кода.
