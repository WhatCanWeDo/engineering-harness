#!/usr/bin/env python3
"""Validate an explanation, shuffle choices, and render an offline HTML document."""
import argparse
import copy
import hashlib
import html
import json
import os
from pathlib import Path
import random
import re
import tempfile
from delivery import default_output, describe

ROOT = Path(__file__).resolve().parents[1]
SECTION_IDS = ['background', 'intuition', 'changes', 'verification']


def string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty string')


def validate(doc):
    if not isinstance(doc, dict) or type(doc.get('version')) is not int or doc['version'] != 1:
        raise ValueError('Document version must be 1')
    for key in ('title', 'scope'):
        string(doc.get(key), key)
    sections = doc.get('sections')
    if not isinstance(sections, list) or len(sections) != 4 or any(not isinstance(s, dict) for s in sections):
        raise ValueError('Expected four sections')
    if [s.get('id') for s in sections] != SECTION_IDS:
        raise ValueError('Sections must be background, intuition, changes, verification in order')
    for section in sections:
        string(section.get('title'), 'section title')
        if not isinstance(section.get('blocks'), list) or not section['blocks']:
            raise ValueError('Section blocks must be a nonempty list')
        for block in section['blocks']:
            if not isinstance(block, dict):
                raise ValueError('Block must be an object')
            kind = block.get('type')
            if kind in ('paragraph', 'code'):
                string(block.get('text'), 'block text')
                if kind == 'code':
                    string(block.get('label'), 'code label')
            elif kind in ('list', 'flow'):
                if not isinstance(block.get('items'), list) or not block['items']:
                    raise ValueError('Block items must be a nonempty list')
                for item in block['items']:
                    string(item, 'block item')
            else:
                raise ValueError(f'Unknown block type: {kind!r}')
    quiz = doc.get('quiz')
    if not isinstance(quiz, list) or len(quiz) != 5:
        raise ValueError('Quiz must contain exactly five questions')
    seen_ids, seen_questions = set(), set()
    for q in quiz:
        if not isinstance(q, dict):
            raise ValueError('Question must be an object')
        for key in ('id', 'question', 'concept', 'correct_option_id'):
            string(q.get(key), key)
        normalized = q['question'].strip().casefold()
        if q['id'] in seen_ids or normalized in seen_questions:
            raise ValueError('Duplicate question id or wording')
        seen_ids.add(q['id'])
        seen_questions.add(normalized)
        options = q.get('options')
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError('Each question needs exactly four options')
        ids, texts = set(), set()
        for option in options:
            if not isinstance(option, dict):
                raise ValueError('Option must be an object')
            for key in ('id', 'text', 'explanation'):
                string(option.get(key), 'option ' + key)
            text_key = option['text'].strip().casefold()
            if option['id'] in ids or text_key in texts:
                raise ValueError('Duplicate option id or text')
            ids.add(option['id'])
            texts.add(text_key)
        if q['correct_option_id'] not in ids:
            raise ValueError('Correct option does not exist')


def prepare(doc):
    quiz = copy.deepcopy(doc['quiz'])
    for q in quiz:
        random.SystemRandom().shuffle(q['options'])
    signature = hashlib.sha256(json.dumps(doc['quiz'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    stats = []
    for q in quiz:
        lengths = [len(o['text']) for o in q['options']]
        correct = next(i for i, o in enumerate(q['options']) if o['id'] == q['correct_option_id'])
        stats.append({'position': correct, 'lengths': lengths})
    return quiz, {'quiz_hash': signature, 'questions': stats}


def read_history(path):
    if path is None or not path.exists():
        return []
    records = []
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get('quiz_hash'), str):
            raise ValueError('Malformed quiz history')
        questions = row.get('questions')
        if not isinstance(questions, list) or len(questions) != 5:
            raise ValueError('Malformed history questions')
        for q in questions:
            if not isinstance(q, dict) or type(q.get('position')) is not int or q['position'] not in range(4):
                raise ValueError('Malformed history position')
            lengths = q.get('lengths')
            if not isinstance(lengths, list) or len(lengths) != 4 or any(type(n) is not int or n <= 0 for n in lengths):
                raise ValueError('Malformed history lengths')
        records.append(row)
    return records


def strict_longest(q):
    return all(q['lengths'][q['position']] > n for i, n in enumerate(q['lengths']) if i != q['position'])


def audit(record, history):
    warnings = []
    current = record['questions']
    if sum(strict_longest(q) for q in current) >= 4:
        warnings.append('Correct option is strictly longest in at least 4/5 questions; review wording.')
    if len({q['position'] for q in current}) == 1:
        warnings.append('All five correct positions coincide by chance; do not reshuffle just to balance.')
    # A repeated render does not gain additional weight in historical diagnostics.
    distinct = {row['quiz_hash']: row for row in history}
    distinct[record['quiz_hash']] = record
    recent = [q for row in list(distinct.values())[-20:] for q in row['questions']]
    if len(recent) >= 20:
        if sum(strict_longest(q) for q in recent) / len(recent) > 0.65:
            warnings.append('History: correct answers are strictly longest in over 65% of questions; review wording.')
        if max(sum(q['position'] == p for q in recent) for p in range(4)) / len(recent) > 0.5:
            warnings.append('History: one correct position exceeds 50%; investigate, not a proof of bias.')
    return warnings


def render(doc, quiz):
    esc = html.escape
    sections = []
    for section in doc['sections']:
        blocks = []
        for block in section['blocks']:
            kind = block['type']
            if kind == 'paragraph':
                blocks.append('<p>' + esc(block['text']) + '</p>')
            elif kind == 'code':
                blocks.append('<figure><figcaption>' + esc(block['label']) + '</figcaption><pre><code>' + esc(block['text']) + '</code></pre></figure>')
            else:
                cls = ' class="flow"' if kind == 'flow' else ''
                blocks.append('<ol' + cls + '>' + ''.join('<li>' + esc(i) + '</li>' for i in block['items']) + '</ol>')
        sections.append('<section id="' + section['id'] + '"><h2>' + esc(section['title']) + '</h2>' + ''.join(blocks) + '</section>')
    toc = ''.join('<li><a href="#' + s['id'] + '">' + esc(s['title']) + '</a></li>' for s in doc['sections'])
    payload = json.dumps(quiz, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    values = {'TITLE': esc(doc['title']), 'SCOPE': esc(doc['scope']), 'CONTENTS': ''.join(sections), 'TOC': toc, 'QUIZ': payload}
    template = (ROOT / 'assets/explainer.html').read_text(encoding='utf-8')
    return re.sub(r'@@(TITLE|SCOPE|CONTENTS|TOC|QUIZ)@@', lambda m: values[m[1]], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, help='Optional explicit path; otherwise create a unique persistent artifact')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--history', type=Path, default=Path.home() / '.local/state/engineering-harness/understand-changes/quiz-history.jsonl')
    group.add_argument('--no-history', action='store_true')
    args = parser.parse_args()
    if args.output is None:
        args.output = default_output()
    try:
        doc = json.loads(args.input.read_text(encoding='utf-8'))
        validate(doc)
        history_path = None if args.no_history else args.history
        if args.output.resolve() == args.input.resolve() or (history_path and history_path.resolve() in (args.output.resolve(), args.input.resolve())):
            raise ValueError('Input, output, and history must have distinct paths')
        if args.output.suffix.lower() not in ('.html', '.htm') or any(ord(c) < 32 or ord(c) == 127 for c in str(args.output)):
            raise ValueError('Output must be an HTML path without control characters')
        history = read_history(history_path)
        quiz, record = prepare(doc)
        warnings = audit(record, history)
        content = render(doc, quiz)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        staged = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent, delete=False) as f:
                staged = Path(f.name)
                f.write(content)
            # Publish the complete file atomically without replacing an existing path.
            os.link(staged, args.output)
        finally:
            if staged is not None:
                staged.unlink()
        recorded = False
        if history_path is not None and not any(r['quiz_hash'] == record['quiz_hash'] for r in history):
            try:
                history_path.parent.mkdir(parents=True, exist_ok=True)
                with history_path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(record) + '\n')
                recorded = True
            except OSError as exc:
                warnings.append(f'HTML created, but optional history was not recorded: {exc}. Cross-quiz diagnostics may be incomplete.')
        print(json.dumps({'output': str(args.output.resolve()), 'warnings': warnings, 'history_recorded': recorded, 'delivery': describe(args.output)}, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Render error: {exc}\n')


if __name__ == '__main__':
    main()
