#!/usr/bin/env python3
"""Scaffold, validate and build a versioned ML Task Spec with offline visual review."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
from contract import SECTIONS, LABELS, validate, require

HERE=Path(__file__).resolve().parents[1]
SHARED=HERE.parent/'understand-changes/scripts'
sys.path.insert(0,str(SHARED))
import render_explainer as shared
import concise
from delivery import describe
E=html.escape

def load(path):
    def unique(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'duplicate JSON key: '+k);out[k]=v
        return out
    require(path.stat().st_size<=2*1024*1024,'input too large')
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))

def payload(value):
    return json.dumps(value,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')

def document(s):
    doc = {'version':1,'title':s['title'],'scope':f"{s['spec_id']} · revision {s['revision']} · ML Task Spec v1 · Черновик для обсуждения",
      'sections':[{'id':k,'title':t,'blocks':[{'type':'paragraph','text':v}]} for k,t,v in [
       ('background','Как я понял задачу',s['summary']),('intuition','Пробелы и мои временные решения','Проверь открытые вопросы; предложение не означает согласование.'),
       ('changes','Подход, требования и детали','Полные справочные разделы раскрываются на месте.'),
       ('verification','Что проверить перед согласованием','Quiz проверяет понимание черновика. Ответы и отметки не согласовывают постановку и не запускают реализацию.')]],'quiz':s['quiz']}
    doc['sections'][0]['blocks'][0]['covers']=['summary']
    return doc

def check(s):
    result=validate(s);shared.validate(document(s));return result

def diagram(d,index,mobile=False):
    width=360 if mobile else 740
    x=84 if mobile else 160
    w=width-x-12; gap=36
    heights={n['id']:max(120,52+22*len(textwrap.wrap(n['label'],max(10,(w-28)//9)))+19*len(textwrap.wrap(n['detail'],max(10,(w-28)//8)))) for n in d['nodes']}
    positions={};height=15
    for n in d['nodes']:
        positions[n['id']]=height;height+=heights[n['id']]+gap
    prefix=f'd{index}-'+('m' if mobile else 'w')
    edges=[]
    for i,e in enumerate(d['edges']):
        lane=12+i*(5 if mobile else 10)
        start=positions[e['from']]+40+(i%3)*14;end=positions[e['to']]+40+(i%3)*14
        edges.append(f'<g class="connection" data-from="{E(e["from"])}" data-to="{E(e["to"])}"><path d="M{x},{start} H{lane} V{end} H{x-4}" marker-end="url(#{prefix}-arrow)"/><text x="{lane+3}" y="{start-6}">{i+1}</text></g>')
    nodes=[]
    labels={'existing':'Существующее','proposed':'Предлагается','external':'Внешнее'}
    for n in d['nodes']:
        y=positions[n['id']];h=heights[n['id']]
        nodes.append(f'<foreignObject x="{x}" y="{y}" width="{w}" height="{h}"><div xmlns="http://www.w3.org/1999/xhtml" class="node-shell"><button class="graph-node {n["state"]}" type="button" data-node="{n["id"]}" aria-pressed="false"><small>{labels[n["state"]]}</small><strong>{E(n["label"])}</strong><span>{E(n["detail"])}</span></button></div></foreignObject>')
    return f'<svg class="spec-graph {"mobile-graph" if mobile else "wide-graph"}" {"data-reading-ignore" if mobile else ""} viewBox="0 0 {width} {height}" role="group" aria-labelledby="{prefix}-title"><title id="{prefix}-title">{E(d["title"])}. Связи расшифрованы под схемой.</title><defs><marker id="{prefix}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#607b71"/></marker></defs>{"".join(edges+nodes)}</svg>'

def diagrams(s):
    out=[]
    for i,d in enumerate(s['diagrams']):
        nodes={n['id']:n['label'] for n in d['nodes']}
        legend=''.join(f'<li data-from="{e["from"]}" data-to="{e["to"]}"><strong>{E(nodes[e["from"]])} → {E(nodes[e["to"]])}</strong><br>{E(e["label"])}</li>' for e in d['edges'])
        out.append(f'<figure class="spec-map" data-covers="diagram-{i+1}"><h3>{E(d["title"])}</h3><p>{E(d["description"])}</p><p class="hint">Нажми на узел, чтобы выделить его связи. Номера стрелок раскрыты под схемой.</p>{diagram(d,i)}{diagram(d,i,True)}<figcaption><ol class="edge-legend">{legend}</ol></figcaption></figure>')
    return ''.join(out)

def badge(status):return f'<span class="status {status}">{LABELS.get(status,E(status))}</span>'
def cites(ids):return ' '.join(f'<a href="#source-{E(i)}">{E(i)}</a>' for i in ids)
def item_html(item, ref=None):
    links=cites(item['source_ids'])+' '+ ' '.join('<a href="#'+g+'">'+g+'</a>' for g in item['gap_ids'])
    attrs=f' id="{E(ref)}" data-covers="{E(ref)}"' if ref else ''
    return f'<div class="spec-item"{attrs}>{badge(item["status"])}<p>{E(item["text"])}</p><div class="citations">{links}</div></div>'

def gap_html(s):
    if not s['gaps']: return '<p>Явные пробелы не отмечены; проверь полноту сценариев.</p>'
    out=[]
    for g in s['gaps']:
        # Open decisions and their consequences are never folded to meet a time budget.
        content=f'<article class="gap-card" id="{g["id"]}" data-covers="{g["id"]}"><h3>{g["id"]} · {E(g["missing"])}</h3><p class="gap-status">{E(g["status"])} · {"Блокирует реализацию" if g["blocking"] else "Не блокирует первый этап"}</p><dl>'+''.join(f'<dt>{label}</dt><dd>{E(g[key])}</dd>' for key,label in [('resolution','Предложение'),('impact','Последствие ошибки'),('question','Вопрос к тебе'),('basis','Основание')])+f'</dl><label for="note-{g["id"]}">Твоя поправка</label><textarea id="note-{g["id"]}" data-review="{g["id"]}" rows="2"></textarea></article>'
        if g['status']=='confirmed' and not g['blocking'] and g['id'] not in s.get('reading',{}).get('critical_refs',[]):
            content='<details data-detail><summary>'+E(g['id']+' · Согласованное решение: '+g['missing'])+'</summary>'+content+'</details>'
        out.append(content)
    return ''.join(out)


def body_html(s):
    out=[]
    main=set(s.get('reading',{}).get('main_sections',['intent','scope','approach','risks'])) | {'scope','risks','requirements'}
    critical=set(s.get('reading',{}).get('critical_refs',[]))
    for sec in s['sections']:
        if any(f'item-{sec["id"]}-{i+1}' in critical for i in range(len(sec['items']))): main.add(sec['id'])
    for sec,(_,title,_) in zip(s['sections'],SECTIONS):
        content=''.join(item_html(x,f'item-{sec["id"]}-{i+1}') for i,x in enumerate(sec['items']))
        if sec['id']=='requirements':
            content+=''.join(f'<article class="requirement" id="{r["id"]}" data-covers="{r["id"]}"><h4>{r["id"]}</h4>{item_html(r)}<label for="review-{r["id"]}">Проверка понимания</label><select id="review-{r["id"]}" data-review="{r["id"]}"><option value="">Не отмечено</option><option>Понято верно</option><option>Нужна поправка</option><option>Нужен контекст</option></select></article>' for r in s['requirements'])
            for a in s['acceptance']:
                content+=f'<article class="acceptance" id="{a["id"]}" data-covers="{a["id"]}"><h4>{a["id"]} → '+', '.join(f'<a href="#{r}">{r}</a>' for r in a['requirement_ids'])+'</h4>'+badge(a['status'])+'<dl>'+''.join(f'<dt>{label}</dt><dd>{E(a[key])}</dd>' for key,label in [('measure','Измеряем'),('method','Метод и данные'),('threshold','Порог / условие'),('artifact','Evidence-артефакт')])+'</dl>'+cites(a['source_ids'])+' '+ ' '.join('<a href="#'+g+'">'+g+'</a>' for g in a['gap_ids'])+'</article>'
        if sec['id'] in main:
            out.append(f'<section class="spec-section" id="spec-{sec["id"]}"><h3>{E(title)}</h3>{content}</section>')
        else:
            out.append(f'<details data-detail id="spec-{sec["id"]}"><summary>{E(title)}</summary>{content}</details>')
    out.append('<p data-search-block data-covers="scouting">Разведка: '+E(s['scouting']['status']+': '+s['scouting']['notes'])+'</p>')
    sources=[];visible_sources=[]
    for src in s['sources']:
        loc=f'<a href="{E(src["locator"])}" rel="noreferrer">{E(src["locator"])}</a>' if src['kind']=='web' else E(src['locator'])
        (visible_sources if 'source-'+src['id'] in critical else sources).append(f'<article id="source-{src["id"]}" class="source" data-covers="source-{src["id"]}"><strong>{src["id"]} · {E(src["kind"])}</strong><p>{loc}</p><p>{E(src["note"])}</p></article>')
    out.extend(visible_sources)
    out.append('<details data-detail><summary>Источники и идентификаторы разведки</summary><p>Task: '+E(s['scouting']['task_id'])+' · packet: '+E(s['scouting']['packet_id'])+'</p>'+''.join(sources)+'</details>')
    request='<pre data-search-block data-covers="request">'+E(s['request'])+'</pre>'
    out.append(request if 'request' in critical else '<details data-detail><summary>Исходное описание задачи</summary>'+request+'</details>')
    return ''.join(out)


def reading_inventory(s):
    expected=['summary','request','scouting']
    critical=['summary','scouting']
    for sec in s['sections']:
        refs=[f'item-{sec["id"]}-{i+1}' for i in range(len(sec['items']))]
        expected.extend(refs)
        if sec['id'] in {'scope','risks'}: critical.extend(refs)
    for name in ('requirements','acceptance','gaps'):
        expected.extend(x['id'] for x in s[name])
        critical.extend(x['id'] for x in s[name] if name!='gaps' or x['status']!='confirmed' or x['blocking'])
    expected.extend('source-'+x['id'] for x in s['sources'])
    expected.extend('diagram-'+str(i+1) for i in range(len(s['diagrams'])))
    critical.append('diagram-1')
    critical.extend(s.get('reading',{}).get('critical_refs',[]))
    require(set(critical)<=set(expected),'unknown critical reading reference')
    return expected,critical


def markdown(s,digest):
    lines=[f'# {s["title"]}',f'ML Task Spec v1 · {s["spec_id"]} · revision {s["revision"]} · DRAFT',f'SHA-256: {digest}','',s['summary'],'','## Исходный запрос',s['request']]
    for sec,(_,title,_) in zip(s['sections'],SECTIONS):
        lines+=['',f'## {title}']
        for i in sec['items']:lines+=['',f'[{LABELS[i["status"]]}] {i["text"]}', 'Источники: '+', '.join(i['source_ids']), 'Пробелы: '+', '.join(i['gap_ids'])]
        if sec['id']=='requirements':
            for r in s['requirements']:lines+=['',f'### {r["id"]} [{LABELS[r["status"]]}]',r['text'],'Источники: '+', '.join(r['source_ids']), 'Пробелы: '+', '.join(r['gap_ids'])]
            for a in s['acceptance']:
                lines+=['',f'### {a["id"]} → '+', '.join(a['requirement_ids']),f'Статус: {LABELS[a["status"]]}']+[f'{k}: {a[k]}' for k in ['measure','method','threshold','artifact']]+['Источники: '+', '.join(a['source_ids']), 'Пробелы: '+', '.join(a['gap_ids'])]
    lines+=['','## Пробелы и принятые для черновика предположения']
    for g in s['gaps']:lines+=['',f'### {g["id"]}: {g["missing"]}']+[f'{k}: {g[k]}' for k in ['status','resolution','basis','impact','blocking','question']]
    lines+=['','## Схемы (визуализация в review.html)']
    for d in s['diagrams']:
        lines+=[d['title'],d['description']]+[f'{n["id"]} [{n["state"]}] {n["label"]}: {n["detail"]}' for n in d['nodes']]+[f'{e["from"]} → {e["to"]}: {e["label"]}' for e in d['edges']]
    lines+=['','## Scouting',json.dumps(s['scouting'],ensure_ascii=False),'','## Источники']
    for src in s['sources']:lines+=[f'{src["id"]} [{src["kind"]}]: {src["locator"]} — {src["note"]}']
    return '\n'.join(lines)+'\n'

def normalize(quiz):
    return sorted([{**q,'options':sorted(q['options'],key=lambda o:o['id'])} for q in quiz],key=lambda q:q['id'])

def build(s,out,quiz_from=None,packet_path=None):
    validation=check(s);require(not out.exists(),'output exists; choose a new revision directory')
    sc=s['scouting']
    knowledge=[x for x in s['sources'] if x['kind']=='knowledge']
    if sc['status'] in {'ready','empty'}:
        require(packet_path is not None,'ready/empty scouting requires --packet')
        packet=load(packet_path)
        require(packet.get('packet_id')==sc['packet_id'] and packet.get('task_id')==sc['task_id'] and packet.get('role')=='developer','packet binding mismatch')
        records=packet.get('sources',[])
        require(all(r.get('scope')=='general' or r.get('project_id')==s['project_id'] for r in records),'packet project mismatch')
        refs={str(r['entry_id'])+'@'+str(r['revision']) for r in records}
        require(all(k['locator'] in refs for k in knowledge),'knowledge source outside packet')
        require((sc['status']=='empty')== (len(records)==0),'empty/ready status disagrees with packet')
    else:require(not knowledge,'unavailable scouting cannot claim knowledge packet sources')
    doc=document(s);warnings=[]
    if quiz_from:
        match=re.search(r'<script id="quiz-data"[^>]*>(.*?)</script>',quiz_from.read_text(),re.S)
        require(match is not None,'quiz-from missing payload');quiz=json.loads(match[1])
        require(normalize(quiz)==normalize(s['quiz']),'quiz-from does not match source quiz')
        page=shared.render(doc,quiz)
    else:
        quiz,record=shared.prepare(doc)
        warnings=shared.audit(record,[])
        page=shared.render(doc,quiz)
    raw=json.dumps(s,ensure_ascii=False,sort_keys=True,indent=2)+'\n';digest=hashlib.sha256(raw.encode()).hexdigest()
    for section,fragment in [('background',diagrams(s)),('intuition',gap_html(s)),('changes',body_html(s))]:
        page,count=re.subn(r'(<section id="'+section+r'">.*?)(</section>)',lambda m:m[1]+fragment+m[2],page,count=1,flags=re.S)
        require(count==1,'missing shared section')
    page=page.replace('</style>',(HERE/'assets/review.css').read_text()+'\n</style>',1)
    feedback='<div class="review-export"><h3>Текст правок для чата</h3><p id="feedback-help">Блок автоматически собирает твои замечания и отметки выше. Скопируй его и вставь в чат. Правки остаются в этой вкладке до закрытия.</p><label for="general-note">Общая поправка</label><textarea id="general-note" data-review="general" rows="4"></textarea><label for="feedback-text">Готовый текст</label><textarea id="feedback-text" readonly rows="10" aria-describedby="feedback-help" placeholder="Добавь замечание или отметку — здесь появится текст для копирования."></textarea><button type="button" id="copy-review" disabled>Скопировать</button><p id="copy-status" role="status"></p><noscript>Автоматическая сборка правок требует JavaScript. Можно написать поправки прямо в чат.</noscript></div>'
    page=page.replace('<section id="quiz">',feedback+'<section id="quiz">',1)
    metadata={'spec_id':s['spec_id'],'revision':s['revision'],'sha256':digest,'status':'draft'}
    page=page.replace('</body>','<script id="spec-review-meta" type="application/json">'+payload(metadata)+'</script><script>'+(HERE/'assets/review.js').read_text()+'</script></body>',1)
    expected,critical=reading_inventory(s)
    reading=concise.analyze(page,quiz if quiz_from else s['quiz'],expected,critical)
    if 'reading' in s:
        refs=s['reading']['quiz_requires'];require(set(refs)=={q['id'] for q in s['quiz']},'quiz_requires must cover all five questions')
        reader=concise.Reader();reader.feed(page)
        for q in s['quiz']:
            required=refs[q['id']]
            require(isinstance(required,list) and bool(required) and all(isinstance(r,str) and any(reader.coverage.get(r,[])) for r in required),'quiz needs visible source facts')
    else: reading['warnings'].append('Legacy spec: quiz support needs editorial verification against the main route.')
    warnings.extend(reading['warnings'])
    page=concise.attach(page,reading)
    out.mkdir(parents=True,exist_ok=False)
    for name,content in [('spec.json',raw),('SPEC.md',markdown(s,digest)),('review.html',page)]:
        with (out/name).open('x',encoding='utf-8') as f:f.write(content)
    manifest={**metadata,'validation':validation,'reading':reading,'warnings':warnings,'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [out/'spec.json',out/'SPEC.md',out/'review.html']}}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return {**manifest,'output':str(out.resolve()),'delivery':describe(out/'review.html')}

def scaffold(args):
    request=args.request.read_text()
    s={'version':1,'spec_id':args.id,'revision':1,'project_id':args.project,'title':args.title,'request':request,'summary':'Заполни понимание задачи после scouting.',
       'scouting':{'status':'unavailable','task_id':'','packet_id':'','notes':'Scouting ещё не выполнен; заполни фактический результат.'},
       'sources':[{'id':'U1','kind':'user','locator':str(args.request),'note':'Исходное описание пользователя.'}],
       'sections':[{'id':k,'items':[{'text':hint,'status':'unknown','source_ids':[],'gap_ids':[]}]} for k,_,hint in SECTIONS],
       'requirements':[],'acceptance':[],'gaps':[],'diagrams':[],'quiz':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(s,f,ensure_ascii=False,indent=2)
    return {'output':str(args.output.resolve()),'status':'skeleton_requires_authoring'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('scaffold')
    for key in ['request','output']:p.add_argument('--'+key,type=Path,required=True)
    for key in ['id','project','title']:p.add_argument('--'+key,required=True)
    p=sub.add_parser('validate');p.add_argument('input',type=Path)
    p=sub.add_parser('build');p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--quiz-from',type=Path);p.add_argument('--packet',type=Path)
    a=parser.parse_args()
    try:
        if a.command=='scaffold':result=scaffold(a)
        else:
            s=load(a.input);result=check(s) if a.command=='validate' else build(s,a.output,a.quiz_from,a.packet)
        print(json.dumps(result,ensure_ascii=False))
    except (ValueError,OSError,TypeError,KeyError,AttributeError) as ex:parser.exit(2,f'Spec error: {ex}\n')

if __name__=='__main__':main()
