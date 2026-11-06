#!/usr/bin/env python3
"""Add responsive system diagrams; --base-html preserves an existing quiz verbatim."""
import argparse
import hashlib
import html as escape_html
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[2] / 'skills/understand-changes/scripts'
sys.path.insert(0, str(SCRIPTS))
from delivery import default_output, describe


def esc(text):
    return escape_html.escape(text)


def diagram(kind, mobile):
    # Authored coordinates and labels, never interpolated repository HTML.
    width = 360 if mobile else 740
    parts = []
    prefix = kind + ('-mobile' if mobile else '-wide')
    def node(x, y, w, title, lines=(), new=False, optional=False):
        height = 52 + 22 * len(lines)
        style = ' changed' if new else ' optional' if optional else ''
        parts.append(f'<g class="map-node{style}"><rect x="{x}" y="{y}" width="{w}" height="{height}" rx="12"/>')
        parts.append(f'<text x="{x+16}" y="{y+29}" class="node-title">{esc(title)}</text>')
        for i, line in enumerate(lines):
            parts.append(f'<text x="{x+16}" y="{y+54+i*22}" class="node-detail">{esc(line)}</text>')
        parts.append('</g>')
        return (x, y, w, height)
    def edge(points, label, lx, ly, optional=False):
        points_s = ' '.join(f'{x},{y}' for x,y in points)
        parts.append(f'<polyline class="map-edge{" optional" if optional else ""}" points="{points_s}" marker-end="url(#{prefix}-arrow)"/>')
        parts.append(f'<text class="edge-label" x="{lx}" y="{ly}">{esc(label)}</text>')
    if kind == 'overview':
        if mobile:
            node(30,15,300,'Ты', ['Цель, ограничения, review'])
            node(30,135,300,'Нативная сессия', ['Codex / Claude • разработчик'])
            node(30,255,300,'Общие skills', ['Память • объяснение + quiz', 'Тесты по запросу • A/B'])
            node(30,400,300,'CLI → Harness Core', ['Общие правила и форматы'])
            node(30,545,300,'Память проекта · SQLite', ['НОВОЕ: подпроекты внутри БД', 'Scout / Curator — схема ниже'],new=True)
            node(30,690,300,'Рабочая среда', ['Код, команды, результаты', 'Агент работает здесь нативно'])
            node(30,835,300,'Артефакты → тебе', ['Изменения, evidence, HTML', 'Review + 5 вопросов'])
            for a,b,label in [(89,135,'задача'),(209,255,'применяет'),(351,400,'вызывает'),(474,545,'читает / записывает')]:
                edge([(180,a),(180,b)],label,190,(a+b)//2+4)
            edge([(30,172),(10,172),(10,727),(30,727)],'исполняет',17,668)
            edge([(180,786),(180,835)],'сохраняет',190,817)
            edge([(330,592),(350,592),(350,448),(330,448)],'контекст',278,536)
            height=951
        else:
            node(220,15,300,'Ты', ['Цель, ограничения, review'])
            node(220,140,300,'Нативная сессия', ['Codex / Claude • разработчик'])
            node(220,265,300,'Общие skills', ['Память • объяснение + quiz', 'Тесты по запросу • A/B'])
            node(220,415,300,'CLI → Harness Core', ['Общие правила и форматы'])
            node(15,570,340,'Память проекта · SQLite', ['НОВОЕ: подпроекты внутри БД', 'Scout / Curator — схема ниже'],new=True)
            node(405,570,320,'Рабочая среда', ['Код, команды, результаты', 'Нативное выполнение агентом'])
            node(405,730,320,'Артефакты → тебе', ['Evidence, HTML + 5 вопросов'])
            for a,b,label in [(89,140,'задача'),(214,265,'применяет'),(361,415,'вызывает')]:
                edge([(370,a),(370,b)],label,383,(a+b)//2+4)
            edge([(290,489),(290,530),(185,530),(185,570)],'читает / записывает',32,520)
            edge([(355,617),(385,617),(385,502),(420,502),(420,489)],'контекст',393,545)
            edge([(520,177),(640,177),(640,570)],'исполняет',548,245)
            edge([(565,666),(565,730)],'сохраняет',579,706)
            height=827
        desc='Пользователь задаёт цель нативному агенту. Агент применяет общие skills и CLI/Core, работает с кодом. Core читает и обновляет память проекта; артефакты и объяснение возвращаются пользователю. Подпроекты находятся внутри общей базы.'
    else:
        if mobile:
            x,w=30,300
            specs=[(15,'Начало задачи',['Цель + paths + инструкции']),
                   (145,'Core: snapshot + группы',['НОВОЕ: автоматический каталог','Файлы → компоненты; tags → темы']),
                   (300,'Поиск в общей SQLite',['Lexical + optional semantic','Embedding-модель → индекс']),
                   (455,'Свежий Scout',['Отбирает refs; уточняет группы']),
                   (585,'Core: context packets',['Фиксирует routing всех ролей','Компилирует короткий контекст']),
                   (740,'Разработчик / тестировщик*',['* Тестировщик — по запросу','Свой packet для каждой роли']),
                   (895,'Результат → evidence',['Реальный outcome + артефакты']),
                   (1025,'Свежий Curator',['Предлагает записи с источниками']),
                   (1155,'Core → та же SQLite',['Валидация → revisions / очередь','Кандидаты не становятся истиной'])]
            for y,title,lines in specs:
                node(x,y,w,title,lines,new=y==145,optional=y==740)
            for a,b,label in [(89,145,'workflow start'),(241,300,'снимок + приоритет'),(396,455,'краткий brief'),(529,585,'selected_refs'),(681,740,'готовые packets'),(836,895,'выполняют задачу'),(969,1025,'workflow finish'),(1099,1155,'proposals → ingest')]:
                edge([(180,a),(180,b)],label,190,(a+b)//2+4)
            edge([(30,1203),(8,1203),(8,348),(30,348)],'следующим задачам',35,1295)
            height=1320
        else:
            node(20,15,310,'Начало задачи', ['Цель + paths + инструкции'])
            node(410,15,310,'Core: snapshot + группы', ['НОВОЕ: автоматический каталог', 'Файлы → компоненты; tags → темы'],new=True)
            node(410,180,310,'Поиск в общей SQLite', ['Lexical + optional semantic', 'Embedding-модель → индекс'])
            node(20,180,310,'Свежий Scout', ['Отбирает refs; уточняет группы'])
            node(20,345,310,'Core: context packets', ['Фиксирует routing всех ролей', 'Компилирует короткий контекст'])
            node(410,345,310,'Разработчик / тестировщик*', ['* Тестировщик — по запросу', 'Свой packet для каждой роли'],optional=True)
            node(410,510,310,'Результат → evidence', ['Реальный outcome + артефакты'])
            node(20,510,310,'Свежий Curator', ['Предлагает записи с источниками'])
            node(20,675,310,'Core → та же SQLite', ['Валидация → revisions / очередь', 'Кандидаты не становятся истиной'])
            edge([(330,52),(410,52)],'start',349,40)
            edge([(565,111),(565,180)],'снимок + приоритет',420,153)
            edge([(410,220),(330,220)],'brief',350,206)
            edge([(175,254),(175,345)],'selected_refs',188,304)
            edge([(330,390),(410,390)],'packets',340,374)
            edge([(565,441),(565,510)],'выполняют задачу',424,485)
            edge([(410,549),(330,549)],'finish',347,534)
            edge([(175,584),(175,675)],'proposals → ingest',188,632)
            edge([(330,723),(738,723),(738,228),(720,228)],'следующим задачам',422,705)
            height=793
        desc='Core фиксирует snapshot и группы, готовит поиск. Scout отбирает контекст; Core выдаёт packets разработчику и при запросе тестировщику. После выполнения evidence передаётся Curator; Core сохраняет предложения в ту же базу для следующих задач.'
    return f'<svg class="system-map {"mobile-map" if mobile else "wide-map"}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{prefix}-title {prefix}-desc"><title id="{prefix}-title">{esc("Общая система" if kind=="overview" else "Цикл памяти")}</title><desc id="{prefix}-desc">{esc(desc)}</desc><defs><marker id="{prefix}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#647b72"/></marker></defs>{"".join(parts)}</svg>'


def visuals():
    return '''<div id="system-overview" class="visual-block"><h3>1. Где память находится в harness</h3><p>Сессией управляет нативный агент. Skills задают способы работы, общий CLI выполняет механические операции. Ниже показан локальный реализованный контур.</p>''' + diagram('overview',False)+diagram('overview',True)+'''<p class="map-legend"><span>Зелёный + «НОВОЕ» — место изменения.</span> Сплошные связи — передача запроса, данных или результата.</p><p class="map-note">Стрелки показывают логические вызовы: CLI/Core не управляет собственным agent loop. Для общей памяти выделим Scout и Curator на следующей схеме. A/B включается отдельным запросом; обязательного orchestrator здесь нет.</p></div>
<div id="memory-overview" class="visual-block"><h3>2. Увеличение: один цикл памяти</h3><p>Scout и Curator — отдельные агенты с короткими заданиями. Core делает детерминированную работу: ограничения поиска, сборку packets, сохранение evidence и revisions.</p>''' + diagram('memory',False)+diagram('memory',True)+'''<p class="map-legend">Пунктирная рамка — исполнительская стадия с дополнительным тестировщиком по запросу. Его packet отдельный; snapshot и routing согласованы с задачей.</p><p class="map-note">Каждый шаг выполняется явной командой workflow. Сохранять спорные обобщения можно как candidate; их подтверждение и публикация между проектами требуют решения человека. Semantic индекс производный, модель общая для устройства; при недоступности semantic используется явный lexical fallback.</p></div>
<div class="visual-block"><h3>3. Что именно делят подпроекты</h3><div class="project-boundary"><strong>Проект ML Platform · одна SQLite</strong><div class="shared-record">Общие факты и процедуры проекта</div><div class="subproject-pair"><div>Компонент<br><strong>training</strong></div><div>Компонент<br><strong>evaluation</strong></div></div><div class="topic">Сквозная тема <strong>telemetry</strong> связывает знания разных задач</div><div class="shared-record">Задача «согласовать метрики» → training + evaluation</div></div><p>Это иллюстративные названия. Метки влияют на порядок поиска, а не запрещают читать соседние группы. Задача может иметь несколько меток; общие записи — ни одной.</p><p class="map-note">Новый проект после project init получает свою пустую БД. Внутри проекта подпроектам отдельный init не нужен. Автоматическая федерация общих знаний между разными БД пока не реализована. Текущий репозиторий продолжает использовать существующий legacy store; этот разбор его не мигрирует.</p></div>'''

CSS = '''
.visual-block { margin: 36px 0 44px; }
.visual-block h3 { font-size: 1.2rem; margin-bottom: 12px; }
.system-map { width:100%; height:auto; display:block; background:#f0f4f0; border-radius:16px; margin:20px 0; }
.mobile-map { display:none; }
.map-node rect { fill:#fff; stroke:#c2d1c8; stroke-width:1.5; }
.map-node.changed rect { fill:#dbefe5; stroke:#28775a; stroke-width:2; }
.map-node.optional rect { stroke-dasharray:6 4; }
.node-title { font:600 16px system-ui,sans-serif; fill:#20332e; }
.node-detail { font:14px system-ui,sans-serif; fill:#465e53; }
.map-edge { fill:none; stroke:#647b72; stroke-width:1.6; }
.edge-label { font:13px system-ui,sans-serif; fill:#405b4e; paint-order:stroke; stroke:#f0f4f0; stroke-width:5px; stroke-linejoin:round; }
.map-legend, .map-note { font-size:.9rem; line-height:1.6; }
.map-legend span { color:#216548; font-weight:650; }
.map-note { padding:16px 20px; border-left:3px solid #9aab9f; background:#edf1ec; }
.project-boundary { border:2px solid #28775a; border-radius:14px; padding:24px; background:#f0f7f2; margin:24px 0; }
.shared-record, .topic { padding:16px; border:1px solid #c2d1c8; border-radius:8px; background:white; margin-top:16px; }
.subproject-pair { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }
.subproject-pair div { padding:16px; border:1px solid #7dad98; background:#dbefe5; border-radius:8px; }
.topic { border-style:dashed; }
@media(max-width:650px) { .wide-map {display:none;} .mobile-map {display:block; min-width:320px;} .visual-block {overflow-x:auto;} .project-boundary{padding:16px;} .subproject-pair{grid-template-columns:1fr;} }
@media print { .system-map {break-inside:avoid;} }
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-html',type=Path)
    args=parser.parse_args()
    warnings=[]
    if args.base_html:
        base=args.base_html.read_text()
    else:
        with tempfile.TemporaryDirectory(prefix='subprojects-explainer-') as tmp:
            out=Path(tmp)/'base.html'
            process=subprocess.run([sys.executable,str(SCRIPTS/'render_explainer.py'),str(HERE/'content.json'),'--output',str(out)],capture_output=True,text=True,check=True)
            warnings=json.loads(process.stdout)['warnings']
            base=out.read_text()
    if 'id="system-overview"' in base:
        raise ValueError('Base already contains diagrams')
    pattern=r'(<section id="background"><h2>.*?</h2><p>.*?</p>)'
    final,count=re.subn(pattern,lambda m:m[1]+visuals(),base,count=1,flags=re.S)
    if count!=1: raise ValueError('Missing background insertion point')
    # The visual model above replaces the old text-only tree.
    final=re.sub(r'<figure><figcaption>Пример структуры, формируемой по фактическим сигналам</figcaption>.*?</figure>','',final,count=1,flags=re.S)
    final=final.replace('</style>',CSS+'\n</style>',1)
    final=final.replace('Выполнен авторский технический прогон из 25 CLI шагов','При реализации подпроектов ранее выполнен авторский технический прогон из 25 CLI шагов',1)
    quiz=lambda s:re.search(r'<script id="quiz-data"[^>]*>(.*?)</script>',s,re.S).group(1)
    if quiz(final)!=quiz(base):raise ValueError('Quiz changed while adding visuals')
    output=default_output();output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:stream.write(final)
    print(json.dumps({'output':str(output),'warnings':warnings,'quiz_preserved':True,'quiz_sha256':hashlib.sha256(quiz(final).encode()).hexdigest(),'delivery':describe(output)},ensure_ascii=False))

if __name__=='__main__': main()
