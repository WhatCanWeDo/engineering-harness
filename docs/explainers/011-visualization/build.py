#!/usr/bin/env python3
"""Build RFC 005's interactive prototypes on the shared explainer/quiz shell."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
HERE=Path(__file__).resolve().parent
SCRIPTS=HERE.parents[2]/'skills/understand-changes/scripts'
sys.path.insert(0,str(SCRIPTS))
from delivery import default_output,describe
import render_explainer as shared
parser=argparse.ArgumentParser();parser.add_argument('--quiz-from',type=Path);args=parser.parse_args()
doc=json.loads((HERE/'content.json').read_text());shared.validate(doc)
warnings=[]
if args.quiz_from:
    base=args.quiz_from.read_text();quiz=json.loads(re.search(r'<script id="quiz-data"[^>]*>(.*?)</script>',base,re.S)[1])
    norm=lambda qs:sorted([{**q,'options':sorted(q['options'],key=lambda o:o['id'])} for q in qs],key=lambda q:q['id'])
    if norm(quiz)!=norm(doc['quiz']):raise ValueError('Quiz differs from source')
    page=shared.render(doc,quiz)
else:
    with tempfile.TemporaryDirectory(prefix='visualization-design-') as tmp:
        target=Path(tmp)/'base.html'
        proc=subprocess.run([sys.executable,str(SCRIPTS/'render_explainer.py'),str(HERE/'content.json'),'--output',str(target)],capture_output=True,text=True,check=True)
        info=json.loads(proc.stdout);warnings=info['warnings'];page=target.read_text()
for section,fragment in re.findall(r'<!-- visual:([a-z]+) -->(.*?)<!-- /visual -->',(HERE/'visuals.html').read_text(),re.S):
    pattern=r'(<section id="'+section+r'">.*?)(</section>)'
    page,count=re.subn(pattern,lambda m:m[1]+fragment+m[2],page,count=1,flags=re.S)
    if count!=1:raise ValueError('Missing target '+section)
page=page.replace('</style>',(HERE/'visuals.css').read_text()+'\n</style>',1)
page=page.replace('</body>','<script>\n'+(HERE/'visuals.js').read_text()+'\n</script></body>',1)
output=default_output();output.parent.mkdir(parents=True,exist_ok=True)
with output.open('x',encoding='utf-8') as f:f.write(page)
print(json.dumps({'output':str(output),'warnings':warnings,'delivery':describe(output)},ensure_ascii=False))
