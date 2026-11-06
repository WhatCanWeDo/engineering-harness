# Native entrypoints и границы исполнения

Проверено по официальным документам 2026-11-03:

- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills): repository skills в `.agents/skills`, explicit `$skill-name`, invocation policy в `agents/openai.yaml`.
- [Claude Code: Skills](https://code.claude.com/docs/en/skills): project `.claude/skills`, `/skill-name`, `disable-model-invocation:true`.

В этом проекте `.agents/skills/harness-ab` ссылается на canonical skill; `.claude/skills/harness-ab/SKILL.md` — тонкий указатель. Invocation по запросу соответствует принятому RFC. Глобальной установки нет. Live roundtrip discovery/invocation в новых Codex/Claude sessions этим MVP не измерен; CLI работает независимо от native discovery. Если skill не виден в меню, укажи canonical SKILL.md явно; это не доказательство загруженности treatment в experiment.

Fresh execution получает только assignment.json, scoped inputs и role context. Для collaboration runtime используй новый контекст без fork; для нативного CLI — новую сессию с рабочим каталогом assignment.workspace. Точную команду запуска/флаги isolation определяй по установленной версии агента. MVP не кодирует непроверенные глобальные flags и не сбрасывает пользовательские настройки.

Проверь effective config, model/reasoning, permissions, hooks, global skills, native memory и cache namespace. Укажи фактические возможности в isolation_evidence и loading evidence. Экспортируй `HARNESS_KNOWLEDGE_DB` к run-local SQLite; для knowledge wrapper дополнительно передавай `--db` явно. Не используй общий store из-за привычного project profile. Внешние native auto-memory механизмы этот env не перехватывает.

Если невозможно исключить чтение sibling output или global instructions, записывай unavailable/violated. Нельзя доказать приватность сменой имени каталога. Для enforceable A/B нужны отдельные OS/container credentials/mounts и независимый evaluator backend; они остаются отдельной последующей работой.
