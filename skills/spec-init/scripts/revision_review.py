"""Render only revision changes; the complete specification remains canonical."""
from difflib import SequenceMatcher
import hashlib
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

from contract import SECTIONS, LABELS
import concise
import render_explainer as shared

HERE = Path(__file__).resolve().parents[1]
E = html.escape
MISSING = object()
NAMES = {
    'title': 'Название', 'request': 'Исходный запрос', 'summary': 'Понимание задачи',
    'sections': 'Разделы', 'items': 'Пункты', 'text': 'Формулировка',
    'requirements': 'Требования', 'acceptance': 'Приёмка', 'gaps': 'Пробелы',
    'sources': 'Источники', 'scouting': 'Разведка', 'diagrams': 'Схемы',
    'status': 'Статус', 'source_ids': 'Источники', 'gap_ids': 'Связанные пробелы',
    'requirement_ids': 'Связанные требования', 'measure': 'Измеряем',
    'method': 'Метод', 'threshold': 'Порог', 'artifact': 'Артефакт',
    'missing': 'Чего не хватает', 'resolution': 'Решение', 'basis': 'Основание',
    'impact': 'Последствия', 'blocking': 'Блокирует', 'question': 'Вопрос',
    'description': 'Описание', 'nodes': 'Узлы', 'edges': 'Связи',
    'label': 'Подпись', 'detail': 'Детали', 'state': 'Состояние',
    'from': 'Откуда', 'to': 'Куда', 'kind': 'Тип', 'locator': 'Расположение',
    'note': 'Примечание', 'notes': 'Оговорки', 'reading': 'Маршрут чтения',
    'main_sections': 'Основные разделы', 'critical_refs': 'Обязательные пункты',
    'quiz_requires': 'Опоры вопросов', 'order': 'Порядок',
    **{key: title for key, title, _ in SECTIONS},
}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def changes(before, after, path=()):
    """Match stable IDs and unchanged list items before comparing their fields."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        return [row for key in dict.fromkeys([*before, *after])
                for row in changes(before.get(key, MISSING), after.get(key, MISSING), path + (key,))]
    if isinstance(before, list) and isinstance(after, list):
        if all(isinstance(x, dict) and 'id' in x for x in before + after):
            old = {x['id']: x for x in before}; new = {x['id']: x for x in after}
            rows = changes(old, new, path)
            if old.keys() == new.keys() and list(old) != list(new):
                rows.append((path + ('order',), list(old), list(new)))
            return rows
        rows = []
        matcher = SequenceMatcher(a=[encode(x) for x in before], b=[encode(x) for x in after], autojunk=False)
        for tag, i, j, k, l in matcher.get_opcodes():
            if tag == 'equal':
                continue
            for offset in range(max(j-i, l-k)):
                old = before[i+offset] if i+offset < j else MISSING
                new = after[k+offset] if k+offset < l else MISSING
                label = str((k if new is not MISSING else i) + offset + 1)
                rows.extend(changes(old, new, path + (label,)))
        return rows
    return [(path, before, after)]


def value_html(value):
    if value is MISSING:
        return '<p>Отсутствует</p>'
    if isinstance(value, dict):
        return '<dl>' + ''.join('<dt>' + E(NAMES.get(k, k)) + '</dt><dd>' + value_html(v) + '</dd>' for k, v in value.items()) + '</dl>'
    if isinstance(value, list):
        return '<ul>' + ''.join('<li>' + value_html(v) + '</li>' for v in value) + '</ul>' if value else '<p>Нет</p>'
    text = ('Да' if value else 'Нет') if isinstance(value, bool) else str(value)
    return '<p>' + E(LABELS.get(text, text)) + '</p>'


def render(current, previous, previous_path, out, feedback, metadata):
    # Revision/binding are displayed in the header; unchanged quiz is not repeated.
    ignored = {'version', 'spec_id', 'project_id', 'revision', 'quiz'}
    rows = changes({k: v for k, v in previous.items() if k not in ignored},
                   {k: v for k, v in current.items() if k not in ignored})
    old_quiz = {q['id']: q for q in previous['quiz']}
    new_quiz = {q['id']: q for q in current['quiz']}
    quiz_ids = [key for key in dict.fromkeys([*old_quiz, *new_quiz]) if old_quiz.get(key) != new_quiz.get(key)]
    review = {'mode': 'changes', 'base_revision': previous['revision'],
              'base_sha256': hashlib.sha256(previous_path.read_bytes()).hexdigest(),
              'changed_paths': ['/'.join(path) for path, _, _ in rows], 'changed_quiz_ids': quiz_ids}
    cards = []
    for index, (path, old, new) in enumerate(rows, 1):
        ref = 'change-' + str(index)
        title = ' → '.join(NAMES.get(part, part) for part in path)
        status = 'Добавлено' if old is MISSING else 'Удалено' if new is MISSING else 'Изменено'
        cards.append(f'<article class="gap-card" data-covers="{ref}"><h3>{E(title)}</h3><p>{status}</p>'
                     + '<h4>Было</h4>' + value_html(old) + '<h4>Стало</h4>' + value_html(new)
                     + f'<label for="note-{ref}">Твоя поправка</label><textarea id="note-{ref}" data-review="{E("/".join(path))}" rows="2"></textarea></article>')
    intro = f'Правки относительно ревизии {previous["revision"]}. Неизменённые части системы здесь не повторяются.'
    if not rows:
        intro += ' Изменений в содержании спецификации нет.'
    if quiz_ids:
        intro += ' В полной спецификации обновлены вопросы: ' + ', '.join(quiz_ids) + '.'
    doc = {'title': current['title'], 'scope': f'{current["spec_id"]} · revision {current["revision"]} · DRAFT · Изменения',
           'sections': [{'id': 'changes', 'title': 'Что изменилось', 'blocks': [{'type': 'paragraph', 'text': intro}]}]}
    page = shared.render(doc, [])
    page = page.replace('<li><a href="#quiz">Пять вопросов на понимание</a></li>', '')
    # Keep the shared JS mount point, without a repeated quiz or its heading.
    start = page.index('<section id="quiz">'); end = page.index('</section>', start) + len('</section>')
    links = '<p><a href="SPEC.md">Полная текущая спецификация</a> · <a href="spec.json">Канонический JSON</a>'
    previous_html = previous_path.with_name('review.html')
    if previous_html.is_file():
        href = quote(os.path.relpath(previous_html, out), safe='/')
        links += ' · <a href="' + E(href) + '">Предыдущее ревью</a>'
    links += '</p><p>Сравнение не означает согласования. Для передачи в реализацию нужен явный ответ по текущей ревизии.</p>'
    page = page[:start] + ''.join(cards) + links + feedback + '<div id="questions" hidden></div>' + page[end:]
    page = page.replace('</style>', (HERE/'assets/review.css').read_text() + '\n</style>', 1)
    meta = json.dumps({**metadata, 'review': review}, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    page = page.replace('</body>', '<script id="spec-review-meta" type="application/json">' + meta + '</script><script>' + (HERE/'assets/review.js').read_text() + '</script></body>', 1)
    refs = ['change-' + str(i+1) for i in range(len(rows))]
    reading = concise.analyze(page, [], refs, refs)
    reading['coverage']['scope'] = 'revision_changes'
    page = concise.attach(page, reading).replace('Основной маршрут с пятью вопросами:', 'Обзор правок:')
    return page, reading, review
