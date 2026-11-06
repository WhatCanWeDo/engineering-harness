import json, subprocess, sys, re
from pathlib import Path
from html.parser import HTMLParser
R=Path('/tmp/harness-skill-eval-20261103/independent'); S=Path('/Users/mshekhunov/engineering-harness/skills/understand-changes'); I=R.parent/'input'
results=[]
def check(name, condition, detail=''):
 results.append(dict(test=name,passed=bool(condition),detail=detail)); assert condition, name
ns={};exec(compile((I/'before.py').read_text(),str(I/'before.py'),'exec'),ns); Before=ns['FeatureCache']
ns={};exec(compile((I/'after.py').read_text(),str(I/'after.py'),'exec'),ns); After=ns['FeatureCache']
t=[0]; calls=[]
def clock():return t[0]
def loader():calls.append(t[0]);return len(calls)
c=After(10,2,clock); check('initial miss',c.get('A',loader)==1)
t[0]=6;check('fresh hit does not load',c.get('A',loader)==1 and len(calls)==1)
t[0]=10;check('TTL boundary reload',c.get('A',loader)==2 and len(calls)==2)
c=After(10,2,clock)
for key in ['A','B','A','C']:c.get(key,lambda:key)
check('LRU reading changes eviction',list(c.entries)==['A','C'])
c=After(10,2,clock);c.get('A',lambda:None)
check('None invalidate semantics',(c.invalidate('A'),c.invalidate('A'))==(True,False))
c=After(10,2,clock);c.get('A',lambda:1);t[0]=20
try:c.get('A',lambda:(_ for _ in ()).throw(RuntimeError('failed')))
except RuntimeError:check('expired loader error removes key','A' not in c.entries)
else:check('loader error raised',False)
t[0]=0;c=After(10,2,clock)
def slow():t[0]=4;return 1
c.get('A',slow);check('expiration measured after load',c.entries['A'][1]==14)
b=Before();check('baseline retains value',b.get('A',lambda:1)==1 and b.get('A',lambda:2)==1)
for args in [(0,1),(1,0),(-1,1),(1,-1)]:
 try:After(*args)
 except ValueError:pass
 else:check('positive parameter check',False)
check('positive parameter checks',True)
medium=json.loads((R/'medium.json').read_text());after=(I/'after.py').read_text()
for s in medium['sections']:
 for block in s['blocks']:
  if block['type']=='code':check('code excerpt matches source',block['text'] in after,block['label'])
class Parse(HTMLParser):
 def __init__(self):super().__init__();self.tags=[];self.ids=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs);self.tags.append((tag,d))
  if 'id'in d:self.ids.append(d['id'])
for name in ['medium','brief']:
 html=(R/(name+'.html')).read_text();p=Parse();p.feed(html)
 check(name+' no external resource refs',not any('src' in d or (tag=='link' and 'href'in d) for tag,d in p.tags))
 check(name+' unique HTML ids',len(p.ids)==len(set(p.ids)))
 payload=re.search(r'<script id="quiz-data" type="application/json">(.*?)</script>',html,re.S).group(1)
 quiz=json.loads(payload);check(name+' quiz dimensions',len(quiz)==5 and all(len(q['options'])==4 for q in quiz))
 (R/(name+'-quiz.json')).write_text(payload)
 (R/(name+'-quiz.js')).write_text(re.findall(r'<script>(.*?)</script>',html,re.S)[0])
 check(name+' no unresolved template tokens',not re.search(r'@@(?:TITLE|SCOPE|CONTENTS|TOC|QUIZ)@@',html))
def run(*args):return subprocess.run([sys.executable,*map(str,args)],capture_output=True,text=True)
prefs=S/'scripts/preferences.py';renderer=S/'scripts/render_explainer.py'
a=run(prefs,'--path',R/'preferences.json','show','--depth','brief','--frequency','on_request')
check('one-shot brief/on_request',a.returncode==0 and json.loads(a.stdout)['frequency']=='on_request')
a=run(prefs,'--path',R/'preferences.json','show'); check('override not persisted',json.loads(a.stdout)['depth']=='medium' and json.loads(a.stdout)['frequency']=='task_end' and not (R/'preferences.json').exists())
(R/'bad-preferences.json').write_text('{"depth":"invalid"}')
a=run(prefs,'--path',R/'bad-preferences.json','show','--depth','brief');check('bad stored preference rejects even override',a.returncode==2,a.stderr.strip())
before=(R/'medium.html').read_bytes();a=run(renderer,R/'medium.json','--output',R/'medium.html','--history',R/'history.jsonl');check('refuses overwrite',a.returncode==2 and (R/'medium.html').read_bytes()==before,a.stderr.strip())
check('identical quiz no duplicate history',len((R/'history.jsonl').read_text().splitlines())==1)
mal=json.loads(json.dumps(medium));mal['quiz']=mal['quiz'][:4];(R/'invalid.json').write_text(json.dumps(mal))
a=run(renderer,R/'invalid.json','--output',R/'invalid.html','--no-history');check('reject four questions',a.returncode==2 and not (R/'invalid.html').exists())
mal=json.loads(json.dumps(medium));mal['sections'][0]['blocks'][0]['text']='<script>globalThis.injected=true</script> & @@QUIZ@@';mal['quiz'][0]['question']='</script><script>globalThis.injected=true</script>'
(R/'escaping.json').write_text(json.dumps(mal));a=run(renderer,R/'escaping.json','--output',R/'escaping.html','--no-history');check('escape fixture rendered',a.returncode==0)
h=(R/'escaping.html').read_text();check('source markup is escaped','<script>globalThis.injected=true</script>' not in h and '&lt;script&gt;'in h and '\\u003c/script\\u003e'in h)
(R/'python-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2))
