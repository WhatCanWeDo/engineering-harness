# Установка на новое устройство и ресурсы

Скопируй или клонируй репозиторий, открой его каталог и выполни:

```sh
sh scripts/setup.sh
```

Это установка **Knowledge Core + локальной embedding-модели**, а не нового coding agent. Codex/Claude устанавливаются отдельно; проектные skill entrypoints уже находятся в репозитории. Модель преобразует текст в 384-мерные векторы и не заменяет conversational LLM.

## Что делает setup

1. Находит `uv`; при отсутствии скачивает официальный uv 0.12.5 в `.harness/bin`, без sudo и изменений shell profiles.
2. Устанавливает управляемый Python 3.12 без глобальных Python launchers. Создаёт `.venv` и устанавливает зависимости строго по `uv.lock`, включая semantic extra.
3. Переиспользует готовый bundle из локального профиля или загружает quantized multilingual MiniLM. Для новой загрузки закреплён HF commit `faf4aa4225822f3bc6376869cb1164e8e3feedd0`. Checksums и runtime входят в manifest/model ID.
4. Проверяет SQLite FTS5, фактический inference, 384 измерения и конечные ненулевые vectors. Измеряет пик RSS и время для коротких запросов и небольшого batch. Готовый bundle публикуется из временного directory после диагностики.
5. Инициализирует локальную SQLite без удаления существующих данных. Устанавливает все native skills/workers и managed instruction blocks (отключается `--skip-skills`); подробности — [общая установка](../install-macos.md). Только после готовности записывает абсолютный путь модели и режим в `.harness/knowledge.local.json`; сохраняет receipt с ресурсами в `.harness/setup/`.

Это runtime readiness, не запуск regression suites. Тесты автоматически не включаются. Повторный setup переиспользует совместимую модель, окружение и сохранённый режим. Явный `--mode` меняет режим. При несовместимом или повреждённом bundle команда отказывает; новый `--model-dir` позволяет подготовить отдельную версию без стирания старой.

Setup в целом не транзакционный: установка пакетов может завершиться до поздней ошибки модели. Исправь указанную причину и повтори команду. Старый профиль не подменяется успешным статусом; временный bundle текущего неудачного вызова удаляется. Установка одного checkout защищена filesystem lock от параллельного setup.

```sh
sh scripts/setup.sh --offline                       # всё уже установлено/доступно в cache
sh scripts/setup.sh --model-dir /path/to/new/bundle # новый bundle или совместимый готовый
sh scripts/setup.sh --mode hybrid                  # явная смена режима
sh scripts/setup.sh --lexical-only                 # без модели и semantic dependencies
sh scripts/setup.sh --help                         # без установки и network
```

В offline-режиме не скачиваются uv/Python/dependencies/модель: отсутствие необходимого даёт ошибку. Установка lexical-only оставляет прежние model files на диске, но убирает модель из профиля. Новый компьютер получает пустую базу; перенос накопленных знаний не выполняется без отдельного явного запроса пользователя. Не копируй только основной `.sqlite3` файл при активном WAL. Изменённые абсолютные пути после переезда исправляет новый setup.

По умолчанию model bundles и БД находятся в `~/.local/share/engineering-harness/`; uv cache и managed Python — в стандартных пользовательских каталогах uv. `--model-dir` задаёт другой каталог модели, `HARNESS_KNOWLEDGE_DB` — другую БД. Env overrides имеют приоритет над локальным профилем и должны быть одинаковыми при установке и эксплуатации. Bootstrap не изменяет `.bashrc`, `.zshrc` или системный Python.

## Ресурсный профиль

| Ресурс | Требование / ориентир |
|---|---|
| ОС | Bootstrap: macOS, Linux, WSL. Нужны shell и curl, если uv отсутствует. Нативный Windows bootstrap пока не предоставлен |
| Python | Setup устанавливает CPython 3.12; Core поддерживает 3.11+. SQLite должен иметь FTS5 — проверяется setup |
| CPU | Совместимый CPU runtime ONNX. В текущем adapter 2 inference threads; разумно иметь 2 доступных CPU threads. Это настройка, не обязательное число физических ядер |
| GPU / VRAM | Не требуются; используется CPUExecutionProvider, CUDA не устанавливается |
| Модель на диске | Около 255 MiB весь bundle в локальном замере; опубликованный ориентир ~0.22 GB относится к модели, не всему окружению |
| Python environment | Около 194 MiB суммарных размеров файлов `.venv` на macOS arm64; hardlinks/FS compression могут изменить реально занятое место |
| Свободный диск | Рекомендуется 3 GiB для первой установки, managed Python, dependencies и caches. Перед новой загрузкой setup проверяет минимум 2 GiB свободного места на разделе модели. База и evidence растут дополнительно |
| RAM процесса | Локальный пик RSS около 1.2 GiB для cold load, 2 коротких RU/EN queries и batch из 32 документов. Это измерение процесса с Python/runtime, не размер одних weights и не гарантированный максимум |
| Запас RAM | Планировать примерно 2 GiB доступной RAM на одновременно работающий embedding-процесс; больше при длинных документах/нескольких процессах. Это эксплуатационный ориентир, а не измеренный универсальный minimum |
| RAM компьютера | 8 GiB — стартовый практический ориентир, 16 GiB удобнее при одновременно открытых IDE, браузере и agents. Не жёсткое требование модели |
| Сеть | Нужна при первой загрузке uv/Python/packages/public weights. После setup inference локальный; проектный текст не отправляется embedding API |

Указанный RSS измерен на macOS arm64 / CPython 3.12.14 / FastEmbed 0.9.1 / ONNX Runtime 1.31.1. На другой ОС/CPU память и latency могут отличаться. Встроенный probe повторяет замер на новом устройстве и сохраняет его в receipt. Он не измеряет общий свободный RAM и не обещает защиту от OOM.

```sh
.venv/bin/python scripts/knowledge_resources.py --model /path/to/bundle
```

Каждый CLI-процесс загружает свой runtime; несколько параллельных процессов могут суммировать расход. Постоянного daemon нет. Индекс хранится в SQLite; cosine ranking пока делает точный scan доступных vectors, а исходные metadata читаются в Python. Большая база также увеличит RAM и время поиска. Embedding vectors сейчас JSON float arrays, поэтому оценка `384 × 4 bytes` не равна размеру записи в SQLite.

## Подтверждённость и источники

Проверены установка в чистую временную копию checkout на текущем macOS arm64, повторное offline-применение и readiness текущей модели. Это не испытание на физически другом компьютере; managed Python/package caches могли переиспользоваться. Linux/WSL пути предусмотрены, но не проверены здесь. На платформе без совместимых pinned wheels установка завершится ошибкой; для такой машины доступен lexical-only режим.

Источники (просмотрены 2026-11-03): [uv installation](https://docs.astral.sh/uv/getting-started/installation/), [uv installer options](https://docs.astral.sh/uv/reference/installer/), [FastEmbed model catalog](https://qdrant.github.io/fastembed/examples/Supported_Models/), [quantized ONNX model](https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q). Размеры/RSS выше — собственные локальные измерения; запас RAM/диска — наше эксплуатационное предложение.
