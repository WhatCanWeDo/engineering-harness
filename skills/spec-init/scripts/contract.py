"""ML Task Spec v1: canonical field and section definitions, stdlib validation."""
import re

SECTIONS = [
 ('intent','01 · Задача и ожидаемый результат','Пользователь, проблема, сценарий до/после, deliverable, что значит успех.'),
 ('context','02 · Контекст и границы системы','Факты из Scout, актуальные paths/services, внешние зависимости, что проверено.'),
 ('scope','03 · Scope и non-goals','Что меняется, что исключено, сценарии и ограничения.'),
 ('requirements','04 · Требования и приёмка','Функциональные и качественные требования; точная связь R → AC.'),
 ('data','05 · Данные и контракты','Источники, schema/labels, доступ, версии, splits по времени/entity, leakage, slices.'),
 ('approach','06 · Подход и альтернативы','Простой baseline, предлагаемая архитектура, интерфейсы, компромиссы.'),
 ('evaluation','07 · Эксперименты и оценка','Гипотеза, baseline, метрики и определения, slices, protocol, seeds/repeats/CI, stop rule, holdout.'),
 ('reproducibility','08 · Воспроизводимость и артефакты','Code/data/model/config/environment versions, hardware, commands, lineage и storage.'),
 ('resources','09 · Ресурсы и ограничения','CPU/GPU/VRAM/RAM/disk, time/cost/network budget, оценка и основание, лимиты/остановка.'),
 ('operations','10 · Эксплуатация','Если применимо: deployment, monitoring/drift, rollback, доступ, ответственность.'),
 ('delivery','11 · Этапы и передача','Этапы с outcomes/dependencies; smallest vertical slice; конкретные outputs и handoff.'),
 ('risks','12 · Риски и открытые решения','Неопределённость, последствия, mitigations, gaps и решения пользователя.')]
STATES={'user_statement','evidence','proposal','unknown','not_applicable'}
LABELS={'user_statement':'Из запроса','evidence':'По источнику','proposal':'Предложение','unknown':'Неизвестно','not_applicable':'Неприменимо'}

def require(ok, message):
    if not ok: raise ValueError(message)

def text(v, name):
    require(isinstance(v,str) and bool(v.strip()), f'{name}: expected nonempty text')

def fields(obj, expected, name):
    require(isinstance(obj,dict) and set(obj)==set(expected.split()),f'{name}: fields must be {expected}')

def validate(s):
    fields(s,'version spec_id revision project_id title request summary scouting sources sections requirements acceptance gaps diagrams quiz','spec')
    require(type(s['version']) is int and s['version']==1,'version must be 1')
    require(type(s['revision']) is int and s['revision']>0,'revision must be positive integer')
    for k in ['spec_id','project_id','title','request','summary']:text(s[k],k)
    require(bool(re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',s['spec_id'])),'spec_id: unsafe ID')
    ids=set()
    def identifier(v):
        text(v,'id');require(bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,79}',v)) and v not in ids,'invalid or duplicate ID: '+str(v));ids.add(v)
    for key in ['sources','sections','requirements','acceptance','gaps','diagrams','quiz']:
        require(isinstance(s[key],list),key+' must be a list')
    sources={}
    for src in s['sources']:
        fields(src,'id kind locator note','source');identifier(src['id'])
        require(src['kind'] in {'user','knowledge','code','web','artifact'},'source kind')
        for k in ['locator','note']:text(src[k],k)
        if src['kind']=='web':require(src['locator'].startswith(('https://','http://')),'web URL must be HTTP(S)')
        sources[src['id']]=src
    def refs(v):
        require(isinstance(v,list) and all(isinstance(x,str) and x in sources for x in v),'dangling source reference')
    def state(obj):
        require(obj['status'] in STATES,'unknown status');refs(obj['source_ids'])
        if obj['status'] in {'user_statement','evidence'}:require(bool(obj['source_ids']),'assertion needs sources')
        if obj['status']=='user_statement':require(any(sources[x]['kind']=='user' for x in obj['source_ids']),'user statement needs user source')
    sc=s['scouting'];fields(sc,'status task_id packet_id notes','scouting')
    require(sc['status'] in {'ready','empty','unavailable'},'scouting must be ready/empty/unavailable, not pending')
    for k in ['task_id','packet_id','notes']:require(isinstance(sc[k],str),'scouting '+k)
    text(sc['notes'],'scouting notes')
    if sc['status'] in {'ready','empty'}:text(sc['task_id'],'task_id');text(sc['packet_id'],'packet_id')
    if sc['status']=='unavailable':require(not sc['packet_id'],'unavailable cannot claim packet')
    require([x.get('id') for x in s['sections']]==[x[0] for x in SECTIONS],'expected all 12 sections in canonical order')
    for sec in s['sections']:
        fields(sec,'id items','section');require(isinstance(sec['items'],list) and bool(sec['items']),'section needs items')
        for item in sec['items']:
            fields(item,'text status source_ids gap_ids','item');text(item['text'],'item.text');state(item)
    reqids=set()
    require(bool(s['requirements']) and bool(s['acceptance']),'requirements and acceptance cannot be empty')
    for r in s['requirements']:
        fields(r,'id text status source_ids gap_ids','requirement');identifier(r['id']);reqids.add(r['id']);text(r['text'],'requirement');state(r)
    covered=set()
    for a in s['acceptance']:
        fields(a,'id requirement_ids measure method threshold artifact status source_ids gap_ids','acceptance');identifier(a['id'])
        require(isinstance(a['requirement_ids'],list) and bool(a['requirement_ids']) and all(isinstance(x,str) and x in reqids for x in a['requirement_ids']),'acceptance dangling requirement')
        covered.update(a['requirement_ids']);state(a)
        for k in ['measure','method','threshold','artifact']:text(a[k],k)
    require(covered==reqids,'every requirement needs acceptance criterion')
    for g in s['gaps']:
        fields(g,'id missing resolution basis impact blocking status question','gap');identifier(g['id'])
        for k in ['missing','resolution','basis','impact','question']:text(g[k],k)
        require(type(g['blocking']) is bool,'blocking must be boolean')
        require(g['status'] in {'open','proposed','confirmed'},'gap status')
        if g['status']=='confirmed':require(any(x['kind']=='user' and x['id'] in g['basis'].split() for x in sources.values()),'confirmed gap basis must name user source ID')
    gapids={g['id'] for g in s['gaps']}
    assertions=[i for sec in s['sections'] for i in sec['items']]+s['requirements']+s['acceptance']
    for item in assertions:
        require(isinstance(item['gap_ids'],list) and all(isinstance(g,str) and g in gapids for g in item['gap_ids']),'dangling gap reference')
        if item['status']=='unknown':require(bool(item['gap_ids']),'unknown needs linked gap')
    require(1<=len(s['diagrams'])<=2,'one or two diagrams required')
    for d in s['diagrams']:
        fields(d,'title description nodes edges','diagram');text(d['title'],'diagram title');text(d['description'],'diagram description')
        require(isinstance(d['nodes'],list) and 2<=len(d['nodes'])<=9,'diagram needs 2..9 nodes')
        require(isinstance(d['edges'],list) and 1<=len(d['edges'])<=12,'diagram needs 1..12 edges')
        nodes=set()
        for n in d['nodes']:
            fields(n,'id label detail state','node');identifier(n['id']);nodes.add(n['id'])
            for k in ['label','detail']:text(n[k],k)
            require(len(n['label'])<=55 and len(n['detail'])<=160,'node labels too long; move detail into prose')
            require(n['state'] in {'existing','proposed','external'},'node state')
        connected=set()
        for e in d['edges']:
            fields(e,'from to label','edge');text(e['label'],'edge label')
            require(e['from'] in nodes and e['to'] in nodes and e['from']!=e['to'],'dangling/self edge')
            connected.update([e['from'],e['to']])
        require(connected==nodes,'diagram contains unconnected nodes')
    # Common renderer owns quiz shape, shuffling and anti-cue diagnostics.
    return {'status':'draft','gaps':len(s['gaps']),'blocking_gaps':sum(g['blocking'] and g['status']!='confirmed' for g in s['gaps']), 'scope':'structural validation only; not user approval'}
