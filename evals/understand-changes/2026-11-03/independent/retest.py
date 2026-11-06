from pathlib import Path
import json,subprocess,sys,re,hashlib
R=Path('/tmp/harness-skill-eval-20261103/independent'); S=Path('/Users/mshekhunov/engineering-harness/skills/understand-changes'); renderer=S/'scripts/render_explainer.py'
results=[]
def check(name,cond,**detail):
 results.append(dict(test=name,passed=bool(cond),**detail));assert cond,name
def run(data,output,history):
 return subprocess.run([sys.executable,str(renderer),str(data),'--output',str(output),'--history',str(history)],capture_output=True,text=True)
a=run(R/'medium.json',R/'retest-history-failure.html',R/'history-parent-file'/'history.jsonl');m=json.loads(a.stdout)
check('history failure yields usable success',a.returncode==0 and (R/'retest-history-failure.html').exists() and not m['history_recorded'] and any('optional history was not recorded' in w for w in m['warnings']),result=m,stderr=a.stderr)
before=(R/'retest-history-failure.html').read_bytes();a=run(R/'medium.json',R/'retest-history-failure.html',R/'retest-new-history.jsonl')
check('overwrite still rejected',a.returncode==2 and (R/'retest-history-failure.html').read_bytes()==before and not (R/'retest-new-history.jsonl').exists(),stderr=a.stderr.strip())
history=(R/'history.jsonl').read_bytes();a=run(R/'medium.json',R/'retest-existing-history.html',R/'history.jsonl')
check('existing history preserved and deduplicated',a.returncode==0 and (R/'history.jsonl').read_bytes()==history and not json.loads(a.stdout)['history_recorded'])
(R/'retest-corrupt-history.jsonl').write_text('{broken\n');a=run(R/'medium.json',R/'retest-corrupt-output.html',R/'retest-corrupt-history.jsonl')
check('corrupt history fails before output',a.returncode==2 and not (R/'retest-corrupt-output.html').exists() and (R/'retest-corrupt-history.jsonl').read_text()=='{broken\n',stderr=a.stderr.strip())
doc=json.loads((R/'medium.json').read_text());doc['quiz'][4]={
'id':'q5','question':'В итоговом коде вызван FeatureCache(ttl_seconds=10, max_entries=1.5), затем загружены A и B. Все записи свежие. Каков результат?',
'concept':'Граница проверки параметров',
'options':[
 {'id':'reject','text':'Конструктор выдаст ValueError: ёмкость должна быть целой.','explanation':'В конструкторе проверяется только max_entries <= 0; положительное 1.5 проходит, проверки целочисленности нет.'},
 {'id':'ceil','text':'Останутся A и B: дробная ёмкость округляется вверх до двух.','explanation':'Округления нет. После записи B условие len(entries) > max_entries сравнивает 2 с 1.5 и запускает удаление.'},
 {'id':'remove','text':'Останется B: при размере 2 цикл вытеснит давнюю запись A.','explanation':'1.5 проходит проверку положительности. B сначала вставляется; 2 > 1.5 истинно, поэтому popitem(last=False) удаляет A, после чего 1 > 1.5 ложно.'},
 {'id':'keep','text':'Останется A: для второго ключа уже недостаточно ёмкости.','explanation':'Вставка не отклоняется при достижении лимита: B сохраняется перед циклом вытеснения, который удаляет старый A.'}],
'correct_option_id':'remove'}
(R/'corrected.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2))
a=run(R/'corrected.json',R/'corrected.html',R/'corrected-history.jsonl');check('corrected document rendered',a.returncode==0,result=json.loads(a.stdout))
ns={};src=R.parent/'input'/'after.py';exec(compile(src.read_text(),str(src),'exec'),ns);c=ns['FeatureCache'](10,1.5,lambda:0);c.get('A',lambda:'A');c.get('B',lambda:'B');check('new q5 runtime semantics',list(c.entries)==['B'],entries=list(c.entries))
h=(R/'corrected.html').read_text();payload=re.search(r'<script id="quiz-data" type="application/json">(.*?)</script>',h,re.S).group(1);(R/'corrected-quiz.json').write_text(payload);(R/'corrected-quiz.js').write_text(re.findall(r'<script>(.*?)</script>',h,re.S)[0])
# Run the same independently built DOM assertions against the new document without changing the original test.
test=(R/'check-dom.js').read_text().replace("['medium','brief']","['corrected']").replace('/dom-results.json','/corrected-dom-results.json');(R/'check-corrected-dom.js').write_text(test)
a=subprocess.run(['node',str(R/'check-corrected-dom.js')],capture_output=True,text=True);check('corrected interactive quiz 20 paths',a.returncode==0,details=a.stdout)
check('no staged temporary files remain',not any(p.name.startswith('tmp') for p in R.iterdir()))
(R/'retest-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2))
