"""Portable reading-route audit: coverage is structural, time is an estimate."""
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from difflib import SequenceMatcher


def words(value):
    return len(re.findall(r'\S+', value))


def ident(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,79}', value)


def leaves(blocks, hidden=False):
    for block in blocks:
        if block['type'] == 'details':
            yield from leaves(block['blocks'], True)
        else:
            yield block, hidden


def validate_route(doc):
    facts = doc.get('facts')
    if not isinstance(facts, list) or not facts:
        raise ValueError('Version 2 needs a nonempty facts inventory')
    ids = set()
    for fact in facts:
        if not isinstance(fact, dict) or not ident(fact.get('id')) or fact['id'] in ids:
            raise ValueError('Invalid or duplicate fact ID')
        ids.add(fact['id'])
        if type(fact.get('critical')) is not bool or any(not isinstance(fact.get(k), str) or not fact[k].strip() for k in ('statement', 'source')):
            raise ValueError('Fact needs statement, source and critical flag')
    placements = {}
    for section in doc['sections']:
        for block, hidden in leaves(section['blocks']):
            refs = block.get('covers', [])
            if not isinstance(refs, list) or any(not isinstance(r, str) or r not in ids for r in refs):
                raise ValueError('Unknown fact reference')
            for ref in refs:
                if ref in placements:
                    raise ValueError('Fact has more than one canonical placement: ' + ref)
                placements[ref] = not hidden
    if ids != placements.keys():
        raise ValueError('Unplaced facts: ' + ', '.join(sorted(ids - placements.keys())))
    if any(f['critical'] and not placements[f['id']] for f in facts):
        raise ValueError('Critical facts must be visible in the main route')
    for q in doc['quiz']:
        refs = q.get('requires')
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or not placements.get(r, False) for r in refs):
            raise ValueError('Each question requires facts visible in the main route')
    return placements


class Reader(HTMLParser):
    """Count default-visible body content; keep folded content for full-text audit."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.main = []
        self.full = []
        self.code = []
        self.figures = 0
        self.paragraphs = []
        self.paragraph = None
        self.coverage = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        skip = tag in {'script', 'style', 'head', 'nav', 'footer', 'button', 'select', 'textarea'} or 'data-reading-ignore' in a
        hidden = tag == 'details'
        # Summary of a closed details is visible; content remains folded.
        self.stack.append((tag, skip, hidden))
        if tag in {'meta', 'link', 'input', 'br', 'hr', 'img', 'path', 'line', 'rect', 'polyline', 'polygon', 'circle'}:
            self.stack.pop()
        if tag == 'figure' and not self.suppressed() and not self.folded() and a.get('data-kind') != 'code':
            self.figures += 1
        if tag == 'p': self.paragraph = []
        if 'data-covers' in a:
            for ref in a['data-covers'].split():
                self.coverage.setdefault(ref, []).append(not self.folded() and not self.suppressed())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'p' and self.paragraph is not None:
            value = ' '.join(self.paragraph)
            if words(value) >= 12: self.paragraphs.append(value)
            self.paragraph = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def suppressed(self):
        return any(x[1] for x in self.stack) or not any(x[0] == 'body' for x in self.stack)

    def folded(self):
        details = [i for i, x in enumerate(self.stack) if x[2]]
        return bool(details) and not (len(details) == 1 and any(x[0] == 'summary' for x in self.stack[details[0]+1:]))

    def handle_data(self, data):
        if self.suppressed() or not data.strip(): return
        self.full.append(data)
        if self.paragraph is not None: self.paragraph.append(data)
        if not self.folded():
            self.main.append(data)
            if any(x[0] == 'pre' for x in self.stack): self.code.append(data)


def analyze(page, quiz, expected=None, critical=()):
    reader = Reader(); reader.feed(page)
    main_words, full_words = words(' '.join(reader.main)), words(' '.join(reader.full))
    code_words = words(' '.join(reader.code))
    quiz_words = sum(words(q['question']) + sum(words(o['text']) for o in q['options']) + max(words(o['explanation']) for o in q['options']) for q in quiz)
    # Starting heuristic, not a measured reader speed; includes one feedback per question.
    minutes = (main_words-code_words)/160 + code_words/80 + reader.figures*0.5 + quiz_words/180 + len(quiz)*0.15
    warnings = []
    if minutes > 7: warnings.append('Estimated main route exceeds 7 minutes; edit repetition or move secondary detail. Keep critical facts visible.')
    duplicates = []
    normalized = [re.sub(r'\W+', ' ', p.casefold()).strip() for p in reader.paragraphs]
    for i, value in enumerate(normalized[:300]):
        for j in range(i):
            other = normalized[j]
            if value == other or (min(len(value),len(other))/max(len(value),len(other)) >= .8 and SequenceMatcher(None,value,other,autojunk=False).ratio() >= .88):
                duplicates.append({'first_paragraph': j+1, 'second_paragraph': i+1})
                break
    if duplicates: warnings.append('Repeated or near-repeated paragraphs found; review meaning before merging.')
    if len(normalized)>300: warnings.append('Duplicate scan limited to first 300 paragraphs.')
    coverage = {'status':'untracked', 'semantic_verification':False}
    if expected is not None:
        wanted=set(expected); actual=set(reader.coverage)
        missing=sorted(wanted-actual); extra=sorted(actual-wanted)
        repeated=sorted(k for k,v in reader.coverage.items() if len(v)>1)
        hidden=sorted(k for k in critical if not any(reader.coverage.get(k,[])))
        if missing or extra or repeated or hidden:
            raise ValueError('Coverage error: '+json.dumps({'missing':missing,'unknown':extra,'repeated':repeated,'hidden_critical':hidden}))
        coverage={'status':'complete', 'facts':len(wanted), 'main_facts':sum(any(v) for v in reader.coverage.values()), 'semantic_verification':False}
    else:
        warnings.append('Fact coverage is untracked for this legacy document; an editorial audit is required.')
    return {'main_words':main_words,'full_words':full_words,'code_words':code_words,'main_figures':reader.figures,
            'quiz_words':quiz_words,'estimated_minutes':math.ceil(minutes*10)/10,'target_max_minutes':7,
            'method':'160 prose words/min; 80 code; 30 sec/figure; quiz 180 words/min + 9 sec/question',
            'coverage':coverage,'duplicate_candidates':duplicates[:20],'warnings':warnings}


def attach(page, report):
    """Call after all trusted builder fragments are inserted, to avoid stale estimates."""
    estimate=f"{report['estimated_minutes']:g}".replace('.', ',')
    message=f'Основной маршрут с пятью вопросами: примерно {estimate} мин.'
    if report['estimated_minutes']>7: message+=' Превышает целевые 7 минут.'
    badge='<aside class="reading-status" data-reading-ignore><p>'+html.escape(message)+'</p><small>Оценка, а не замер. Детали доступны рядом с тезисами.</small></aside>'
    payload=json.dumps(report,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return page.replace('</header>',badge+'</header>',1).replace('</body>','<script type="application/json" id="reading-report">'+payload+'</script></body>',1)
