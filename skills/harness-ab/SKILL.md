---
name: harness-ab
description: По запросу сравнивать baseline и candidate skill/workflow на одинаковых задачах, с независимой correctness оценкой, человеческим review и учётом расходов; не запускать A/B при обычной правке skill.
---

# Harness A/B

Измеряй пользу изменения на заданном workload, сохраняя нативные agent loops. Python CLI выполняет snapshots, pairing, валидацию receipts, таймер и расчёты. Не переписывай эту механику в рассуждениях агента.

## Маршрутизация

**Plan.** Уточни только отсутствующие задачу/гипотезу, версии A/B, набор задач и бюджет. Зафиксируй primary metric, минимальный полезный выигрыш, human review subset и условия проверки до запусков. Полная схема и команды — [protocol.md](references/protocol.md). Подготовь конкретный `plan.json`; `scripts/ab.py plan` заморозит входы. Просьба спроектировать или реализовать skill не запускает платные эксперименты. Для уже авторизованного конкретного experiment не спрашивай повторное разрешение на каждый шаг.

**Run.** `prepare`, затем последовательный `dispatch` выдают immutable задания. Каждый assignment исполняет отдельная свежая нативная сессия с собственным контекстом, workspace и knowledge DB. Это могут быть доступные native workers; не передавай им coordinator transcript или другой arm. Wrapper сам не запускает LLM и не настраивает sandbox. Проверь реальную загрузку конфигурации и доступ к глобальным skills/memory/hooks. Если изоляция не установлена, запиши `isolation:unavailable`, не выдумывай attestation. Не читай соседние результаты для помощи текущему исполнителю. Details: [native-adapters.md](references/native-adapters.md).

После завершения автономного run сохрани F0 через `freeze`, получи заготовку `receipt`, добавь фактические execution/usage records через `ingest`. Internal self-repair и attributable sidecars относятся к F0. Feedback-driven repair — отдельные F1 и phase repair. Уточнения спецификации одинаково доводятся обоим arms либо сравнение становится несопоставимым. Не продолжай незаметно run после лимита, не выбирай лучший attempt: MVP retry_policy=none. Инфраструктурный сбой сохраняется; замена — новый связанный experiment.

**Evaluate / review.** Переиспользуй независимый evaluator из плана. Новые тесты/rubrics поручай отдельному свежему агенту по [test-on-request](../test-on-request/SKILL.md), когда их создание входит в запрос пользователя. Исполнитель не получает private artifacts; в этом MVP protected backend unavailable. Treatment-generated tests не являются oracle. `evaluate` запускает уже заданную command на копии frozen output; external evaluation импортируется content-bound receipt. Не меняй evaluator после результатов.

`review` создаёт нейтральный HTML с таймером и экспортом JSON. Выдай проверенную HTTP-ссылку через существующий preview helper; после человеческого review импортируй скачанный JSON. Не заполняй human records от имени человека. [review.md](references/review.md) описывает паузы, censoring и carryover.

**Report / improve.** `report` вычисляет все запланированные пары и создаёт HTML + JSON без LLM. Покажи missingness, неизвестную стоимость, F0/F1 и ограничения. Не объявляй маленький dev выигрыш доказательством универсальной пользы. `close` завершает запись в experiment; после него отдельный Curator может сохранить публичные experiment evidence/кандидаты. Не сливай run-local знания автоматически в общий store.

Для следующей версии предложи узкое изменение: failure class → ссылки на runs → механизм → следующий evaluation. Не заменяй baseline автоматически. Использованный validation набор становится development; для promotion нужен новый validation. Новая hypothesis или метрика — новый experiment.

## Scope MVP

Python 3.11+, macOS/Linux/WSL; base dependencies не нужны. Канонический wrapper работает из repository либо с установленным `engineering-harness`. Один agent/model stratum, локальные файлы, manual/native fresh sessions. F0/F1, один зафиксированный review на run. Monetary/call/native time limits advisory; evaluator subprocess timeout enforced locally. Нет headless orchestrator, protected holdout, provider billing integration, автоматической публикации знаний или доказательства отсутствия утечек. Наличие каталогов не создаёт security boundary.
