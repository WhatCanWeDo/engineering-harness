# Fork Tab: установка и использование

```sh
sh scripts/setup.sh
```

Общий installer создаёт native skills и launcher с managed Python без перезаписи чужих файлов.
`scripts/setup_fork_tab.py` сохранён как совместимый вход в общий installer после setup.
Checkout должен оставаться на месте; после переноса повтори installer. Сам helper требует Python 3.9+,
macOS, Ghostty с AppleScript и свойством terminal.tty; проверена установленная 1.4.0.
Сам AppleScript API появился в 1.3.0; совместимость этого helper с 1.3 не проверена.
Зависимостей pip нет.
В новых сессиях: Codex `$fork-tab`, Claude Code `/fork-tab`. В уже открытой сессии
можно попросить агента запустить `~/.local/bin/fork-tab --agent codex`.
Shell-команда требует `--agent` и `--session UUID`, если это обычный shell вне агента.

```sh
~/.local/bin/fork-tab --agent codex --session UUID --dry-run
~/.local/bin/fork-tab --agent claude --session UUID
~/.local/bin/fork-tab --list
~/.local/bin/fork-tab --agent codex --session UUID --window window-ID
```

Окно определяется по TTY предков процесса, иначе — по единственному окну Ghostty.
При нескольких окнах и отсутствии привязки команда отказывает и требует `--window`
или `--terminal` из `--list`. Общий daemon Codex может терять привязку к TTY.
Его унаследованный `GHOSTTY_SURFACE_ID` может относиться к другой старой вкладке,
поэтому не используется. Выбор по переднему окну также не используется.

Рабочая директория сохраняется (`--cwd` позволяет задать явно). Исходная вкладка не
закрывается. Истории ветвятся нативными CLI; файлы общие, отдельного worktree нет.
Временные model/profile/permission overrides автоматически не воспроизводятся.
Передаётся текущий `PATH`: установленный через npm Codex использует `/usr/bin/env node`,
а окружение Ghostty, запущенного через macOS, может не содержать Homebrew.
Сохраняется путь `CODEX_HOME` / `CLAUDE_CONFIG_DIR`, если задан; секреты и окружение
исходного процесса целиком не копируются. Новый процесс использует обычные настройки
и авторизацию установленного агента. Удалённые SSH-сессии этим адаптером не поддерживаются.

`tab-created` подтверждает создание вкладки, а не успешную загрузку истории. Ошибки
native CLI остаются в новой вкладке (wait after command). Старую вкладку команда не трогает.
При превращении окна в группу вкладок Ghostty может менять window ID. Helper привязывает
создание к UUID исходного terminal, затем заново находит его окно и новую вкладку.
Ошибка необязательного заголовка/фокуса возвращается как warning после `tab-created`.
При неопределённом результате создания повтор автоматически не выполняется.
Нативный `/fork` сохраняет прежнее поведение. Вызов в чате проходит через агента,
поэтому это не перехват slash-команды с нулевой стоимостью model calls.

Источники, проверены 2026-11-06:

- [Ghostty AppleScript](https://ghostty.org/docs/features/applescript) — native new tab in window; локальный Ghostty.sdef 1.4.0 также даёт tty.
- [Codex CLI](https://learn.chatgpt.com/docs/cli/reference) — `codex fork SESSION_ID`; локально 0.167.0.
- [Claude CLI](https://code.claude.com/docs/en/cli-reference) — `--resume UUID --fork-session`; локально 2.1.224.
- [Claude skills](https://code.claude.com/docs/en/skills) — `${CLAUDE_SESSION_ID}` в тексте skill.

`CODEX_THREAD_ID` наблюдался в tool environment 0.167.0; это не обещание стабильности
недокументированного интерфейса. При его отсутствии используется явный UUID, не эвристика.

[Исправление и реальный пилот 2026-11-06](../../../docs/evaluations/fork-tab-fix-2026-11-06.md):
после исправлений пользователь подтвердил загрузку истории и строки ввода Codex.
