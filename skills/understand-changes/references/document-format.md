# Контракт документа v1

JSON в UTF-8. Генератор принимает только данные, экранирует текст и использует общий HTML-шаблон. Настройки глубины и частоты управляют работой агента; генератор проверяет структуру, не педагогическую корректность.

Обязательные поля:

- `version`: 1.
- `title`: непустое название.
- `scope`: конкретные исходники, baseline/итог и ограничения охвата.
- `sections`: четыре секции с уникальными `id` в порядке `background`, `intuition`, `changes`, `verification`. У каждой `title` и непустой `blocks`.
- `quiz`: ровно пять вопросов. У каждого уникальный `id`, `question`, `concept`, четыре `options` и `correct_option_id`. У каждого варианта уникальный в пределах вопроса `id`, `text`, `explanation`. Все текстовые поля непустые; `correct_option_id` совпадает ровно с одним вариантом.

Блоки секций:

Общий HTML-шаблон держит читаемую ширину текста и одну колонку ответов. Вопрос находится внутри карточки как заголовок, а не в разрыве рамки `legend`; буква варианта отделена от текста, переносы выровнены. Выбор ответа меняет цвет, но не толщину границ и не положение текста. При изменениях шаблона проверяй реальную вёрстку с длинными вопросами на узком экране, с увеличенным текстом и после раскрытия feedback: одни структурные проверки HTML этого не подтверждают.

```json
{"type": "paragraph", "text": "Текст объяснения"}
{"type": "code", "text": "cache.pop(key, None)", "label": "cache.py: invalidate"}
{"type": "list", "items": ["Первое наблюдение", "Второе наблюдение"]}
{"type": "flow", "items": ["Запрос", "Проверка ключа", "Результат"]}
```

Код и подписи отображаются как текст; Markdown и HTML внутри строк не исполняются. Ссылки на код можно указывать как пути и имена символов в `label`/тексте. Генератор не проверяет существование этих путей: это делает агент по изученным исходникам.

Для архитектурного объяснения этих блоков недостаточно для обязательной общей схемы системы. Добавь авторский локальный HTML/SVG через builder поверх результата renderer по [правилам обзорной схемы](system-overview.md). Сам JSON-контракт остаётся v1; поля для raw HTML/SVG здесь не добавлены. В preview передаётся итоговый документ со схемой, а не промежуточный файл генератора.

Пример одного вопроса по форме (не полный документ):

```json
{
  "id": "q1",
  "question": "Что произойдёт в описанном сценарии?",
  "concept": "Поведение при изменении входа",
  "options": [
    {"id": "a", "text": "Первый исход", "explanation": "Обоснование первого исхода"},
    {"id": "b", "text": "Второй исход", "explanation": "Обоснование второго исхода"},
    {"id": "c", "text": "Третий исход", "explanation": "Обоснование третьего исхода"},
    {"id": "d", "text": "Четвёртый исход", "explanation": "Обоснование четвёртого исхода"}
  ],
  "correct_option_id": "b"
}
```

Команды (замени пути на фактические):

```sh
python3 SKILL/scripts/preferences.py show --depth deep
python3 SKILL/scripts/preferences.py set --depth brief
python3 SKILL/scripts/render_explainer.py INPUT.json
python3 SKILL/scripts/render_explainer.py INPUT.json --output /tmp/DATE-task/explanation.html
python3 SKILL/scripts/render_explainer.py INPUT.json --output /tmp/DATE-test/explanation.html --history /tmp/DATE-test/history.jsonl
python3 SKILL/scripts/delivery.py /path/to/explanation.html --open
python3 SKILL/scripts/preview.py /path/to/explanation.html
```

`preferences.py --path FILE show` и `preferences.py --path FILE set ...` используют изолированные личные настройки. Без `--path` настройки находятся в `~/.config/engineering-harness/understand-changes.json`. Команда `show` никогда не записывает настройки.

Без `--output` HTML получает уникальный постоянный путь в `~/.local/share/engineering-harness/explainers/DATE-ID/explanation.html`. JSON-результат содержит `output`, `warnings`, `history_recorded` и `delivery`: вспомогательную файловую Markdown-ссылку `file_link`, `file_path`, `preview_argv`, `open_argv`, `open_command`, `command_shell`, `launch_requested` и `remote_shell_detected`. Генерация не запускает браузер или сервер. Запуск `preview_argv` возвращает проверенную HTTP-ссылку `browser_link`, `preview_url` и срок действия. Выдачу и fallback см. в [delivery.md](delivery.md).

История по умолчанию: `~/.local/state/engineering-harness/understand-changes/quiz-history.jsonl`. `--no-history` отключает чтение и запись истории. Генератор отказывается перезаписывать существующий output. Ошибки структуры, повреждённая существующая история или настройки завершаются ненулевым кодом до генерации; не заявляй об успешной генерации при ошибке.

Если HTML создан, но запись необязательной истории не удалась, команда возвращает успех с `history_recorded: false` и явным предупреждением. Передай это ограничение пользователю: документ пригоден, но межзадачная диагностика может быть неполной. Не перезапускай генерацию поверх готового файла ради записи истории. HTML сначала полностью записывается во временный файл в папке output, затем публикуется через hard link без перезаписи существующего файла. Если файловая система не поддерживает эту операцию, команда явно завершается ошибкой.
