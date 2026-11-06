---
name: fork-tab
description: Создать ветку текущего чата Claude Code в новой вкладке того же окна Ghostty на macOS.
---

Прочитай общие правила [Fork Tab](../../../skills/fork-tab/SKILL.md).
UUID текущей сессии — `${CLAUDE_SESSION_ID}` (подстановка текста skill, не shell env).
Выполни из текущего проекта:

```sh
~/.local/bin/fork-tab --agent claude --session '${CLAUDE_SESSION_ID}'
```

Если placeholder не заменён, нужен явно известный UUID; не используй latest и не делегируй вызов.
