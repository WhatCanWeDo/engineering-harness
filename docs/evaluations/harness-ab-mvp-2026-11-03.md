# Harness A/B MVP — техническая проверка, 2026-11-03

Реализован local cooperative MVP: plan/prepare/dispatch/freeze/receipt/ingest/evaluate/review/status/report/close. Канонический skill находится в skills/harness-ab; project entrypoints Codex/Claude подключены. Runtime не вызывает LLM и не запускает реальные native sessions автоматически.

## Выполнено

- Skill Creator quick_validate: valid. Системному Python не хватало PyYAML; validator выполнен существующим проектным .venv, без установки новых зависимостей.
- Python compileall: без ошибок. `uv lock --check --offline`: lock актуален.
- `uv build --offline`: wheel и sdist собраны, `harness/ab/review.html` включён в пакет.
- `scripts/demo_harness_ab.py`: 37 CLI шагов, четыре синтетических run, transport evaluator, usage/review import, отчёты до/после. Повторный comparison.json идентичен. Это вымышленные данные; decision принудительно synthetic_demonstration.
- Идентичный usage replay принят. Конфликтующий usage отклонён с Immutable record conflict; evaluation другого output hash — с Evaluation output hash mismatch; повторный freeze F0 — Output revision already frozen. F1 сохранён и оценён отдельно. После close импорт отклонён с Experiment is closed.
- Headless Chrome: review на ширине 390 px без горизонтального переполнения; start → reload восстанавливает сохранённые events и ставит pause. Browser-generated диагностический JSON прошёл валидацию таймера как abandoned, не импортировался как человеческий замер.
- Объяснение: пять вопросов, 20 вариантов; feedback виден после выбора. На 390 px и при увеличенном шрифте на 1280 px переполнений не обнаружено. Скриншот mobile feedback просмотрен визуально.
- Локальные ссылки skill и thin entrypoints разрешаются; Codex symlink ведёт к canonical skill.

Авторские command receipts и hashes реализации: [operational.json](../../evals/harness-ab/2026-11-03/operational.json). Они не заменяют независимый test suite. После диагностик source hashes совпадали.

## Не проверено / не реализовано

Новые независимые тесты не генерировались, полный regression suite не запускался: пользователь сохраняет тестирование по запросу. Реальное улучшение skill, реальные human measurements, cross-agent roundtrip discovery и fresh-session isolation не измерялись.

Private backend, global native memory interception, headless runner, автоматическое получение provider billing, retry controller и статистические подтверждающие исследования отсутствуют. Per-run native limits advisory; только command evaluator имеет локальный process timeout. Receipt attestations и файловые hashes обнаруживают несогласованность, но не защищают от процесса с теми же правами, способного переписать весь store.

Статус: реализованный локальный прототип, готов к отдельному независимому тестированию и ограниченному пилоту; не доказательство качества сравниваемых skills.
