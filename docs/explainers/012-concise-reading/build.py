#!/usr/bin/env python3
"""Build a shorter reading route from the historical Knowledge design, preserving demos."""
import argparse
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SCRIPTS=ROOT/'skills/understand-changes/scripts'
sys.path.insert(0,str(SCRIPTS))
import render_explainer as renderer
import concise
from delivery import default_output, describe


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    old_dir=HERE.parent/'004-knowledge-context'
    old=json.loads((old_dir/'content.json').read_text())
    doc=json.loads((HERE/'content.json').read_text())
    renderer.validate(doc)
    quiz,record=renderer.prepare(doc)
    # One shuffle is used for both views; the five questions and their choices are unchanged.
    page=renderer.render(doc,quiz)
    baseline=renderer.render(old,quiz)
    fragments=re.findall(r'<!-- visual:([a-z]+) -->(.*?)<!-- /visual -->',(old_dir/'visuals.html').read_text(),re.S)
    for target,fragment in fragments:
        pattern=r'(<section id="'+target+r'">.*?)(</section>)'
        baseline=re.sub(pattern,lambda m:m[1]+fragment+m[2],baseline,count=1,flags=re.S)
        # Flatten legacy disclosure inside the one new details level.
        fragment=re.sub(r'<details[^>]*>\s*<summary>(.*?)</summary>',r'<article><h4>\1</h4>',fragment,flags=re.S).replace('</details>','</article>')
        fragment=re.sub(r'<(p|li|pre)(?=[\s>])',r'<\1 data-search-block',fragment)
        wrapped='<details data-detail><summary>Исходная демонстрация: '+{'background':'общий контур','intuition':'поиск и роли','changes':'обновление и восстановление','verification':'сценарии и источники'}[target]+'</summary>'+fragment+'</details>'
        page=re.sub(pattern,lambda m:m[1]+wrapped+m[2],page,count=1,flags=re.S)
    # The main-route map explains the complete proposed loop; original demos remain in details.
    graph='''<figure class="route-map"><figcaption>Предлагаемый контур: от задачи к опыту следующей задачи</figcaption><div style="overflow-x:auto"><svg xmlns="http://www.w3.org/2000/svg" width="680" height="320" viewBox="0 0 680 320" role="img" aria-label="Задача передаётся Scout, затем разработчику; outcome и evidence идут Curator и Knowledge Core, из которого Scout читает разрешённые записи."><defs><marker id="route-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#17624e"/></marker></defs><g fill="none" stroke="#17624e" stroke-width="2" marker-end="url(#route-arrow)"><path d="M190 65H245"/><path d="M435 65H490"/><path d="M585 100V220"/><path d="M490 255H435"/><path d="M245 255H190"/><path d="M95 220V145H340V100"/></g><g fill="#edf2ed" stroke="#92ab9d"><rect x="0" y="30" width="190" height="70" rx="8"/><rect x="245" y="30" width="190" height="70" rx="8"/><rect x="490" y="30" width="190" height="70" rx="8"/><rect x="0" y="220" width="190" height="70" rx="8"/><rect x="245" y="220" width="190" height="70" rx="8"/><rect x="490" y="220" width="190" height="70" rx="8"/></g><g text-anchor="middle" fill="#20332e" font-family="system-ui,sans-serif" font-size="15"><text x="95" y="60">Задача</text><text x="95" y="83">Native сессия</text><text x="340" y="60">Context Scout</text><text x="340" y="83">Свежий контекст</text><text x="585" y="60">Разработчик</text><text x="585" y="83">Role packet</text><text x="95" y="248">Knowledge Core</text><text x="95" y="271">SQLite · версии · поиск</text><text x="340" y="248">Knowledge Curator</text><text x="340" y="271">Проверка proposals</text><text x="585" y="248">TaskOutcome</text><text x="585" y="271">Evidence / результат</text><text x="215" y="49" font-size="12">цель</text><text x="461" y="49" font-size="12">пакет</text><text x="622" y="164" font-size="12">исход</text><text x="462" y="239" font-size="12">факты</text><text x="214" y="239" font-size="12">версии</text><text x="215" y="137" font-size="12">разрешённые записи</text></g></svg></div></figure>'''
    page=page.replace('<section id="intuition">',graph+'<section id="intuition">',1)
    for name in ('page','baseline'):
        value=locals()[name]
        value=value.replace('</style>',(old_dir/'visuals.css').read_text()+'\n</style>',1)
        value=value.replace('</body>','<script>\n'+(old_dir/'visuals.js').read_text()+'\n</script></body>',1)
        if name=='page':page=value
        else:baseline=value
    before=concise.analyze(baseline,quiz)
    after=concise.analyze(page,quiz,[f['id'] for f in doc['facts']],[f['id'] for f in doc['facts'] if f['critical']])
    page=concise.attach(page,after)
    output=args.output or default_output();output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:stream.write(page)
    report={'output':str(output),'before':before,'after':after,'same_quiz':all({k:v for k,v in a.items() if k!='requires'}==b for a,b in zip(doc['quiz'],old['quiz'])),'warnings':renderer.audit(record,[]),'delivery':describe(output)}
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
