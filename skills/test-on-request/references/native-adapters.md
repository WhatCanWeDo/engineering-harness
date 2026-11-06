# Нативное делегирование и discovery

Каноническая логика находится в этом skill. Agent-specific entrypoints только подключают её. Не переносить правила тестирования в отдельные копии.

## Codex

В проекте `.agents/skills/test-on-request` ссылается на `skills/test-on-request`. В agents/openai.yaml стоит allow_implicit_invocation:false. Вызов пользователем: `$test-on-request подготовь публичные тесты для …` или `$test-on-request атакуй готовое решение …`. Для обнаружения нового skill может потребоваться новая сессия из корня проекта.

Определи доступный native инструмент запуска по реальной tool schema. В среде с `collaboration.spawn_agent` используй `fork_turns:"none"`, отдельный task_name и message из brief; модель оставь по умолчанию. В другой версии API используй документированный эквивалент нового контекста. Не отправляй всю историю и не запускай генерацию сам при отсутствии такой возможности. Возвращённый agent ID сохраняй вместе с result для продолжения этого назначения. В stdout CLI только brief; собственный LLM API или agent loop утилита не запускает.

## Claude Code

Проектный `.claude/skills/test-on-request/SKILL.md` — тонкий указатель с disable-model-invocation:true. Вызов: `/test-on-request подготовь публичные тесты для …`. Worker `.claude/agents/harness-test-generator.md` читает те же общие инструкции. Запускай его через Agent tool как non-fork custom subagent с минимальным prompt; не выбирай Agent(fork), который наследует всю историю. Для трёх ролей нужны разные сессии, не resume предыдущей роли. Не включай persistent memory.

Перед запуском сверяй доступные tools и режим контекста. Установка файлов не доказывает, что конкретный клиент загрузил их или разрешил Agent tool. Если non-fork worker недоступен — generation_unavailable и brief для новой ручной сессии. Нельзя подменять отсутствие capability успешной декларацией.

## Проверенные основания и пределы

Проверено по официальной документации 2026-11-03: [Codex discovery](https://learn.chatgpt.com/docs/build-skills), [Claude skills и explicit-only](https://code.claude.com/docs/en/skills), [Claude non-fork subagents](https://code.claude.com/docs/en/sub-agents). Локальные указатели и metadata проверяются отдельно от живого прогона каждой платформы. Общий filesystem допускается для public/adversarial; эти adapters не дают private isolation.
