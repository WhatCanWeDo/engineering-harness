#!/usr/bin/env python3
"""Standalone setup/resource explanation using the existing readable quiz renderer."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRIPTS = ROOT / 'skills/understand-changes/scripts'
sys.path.insert(0, str(SCRIPTS))
from delivery import default_output, describe
with tempfile.TemporaryDirectory() as folder:
    base = Path(folder) / 'base.html'
    process = subprocess.run([sys.executable, str(SCRIPTS / 'render_explainer.py'), str(HERE/'content.json'), '--output', str(base)],capture_output=True,text=True,check=True)
    info=json.loads(process.stdout); html=base.read_text()
fragment='''<aside class="resource-panel" aria-label="Плановый запас ресурсов"><h3>Сколько embedding-процессов одновременно?</h3><label for="workers">Процессы: <output id="worker-count">1</output></label><input id="workers" type="range" min="1" max="4" value="1"><p id="ram-estimate">Плановый запас RAM: около 2 GiB.</p><p>Дисковый bundle может быть общим: около 255 MiB. Это иллюстрация запаса, не прогноз RSS или гарантия отсутствия OOM.</p></aside>'''
html=html.replace('<section id="changes">',fragment+'<section id="changes">',1)
html=html.replace('</style>','''.resource-panel{padding:24px;margin:32px 0;border:1px solid #bed2cb;border-radius:16px;background:#edf5f2;color:#203b32}.resource-panel h3{margin-top:0}.resource-panel label{display:block;font-weight:650}.resource-panel input{display:block;width:100%;margin:20px 0;accent-color:#267561}.resource-panel p{overflow-wrap:anywhere} @media(max-width:600px){.resource-panel{padding:16px}}\n</style>''',1)
html=html.replace('</body>','''<script>const workers=document.getElementById('workers');workers.addEventListener('input',()=>{document.getElementById('worker-count').textContent=workers.value;document.getElementById('ram-estimate').textContent='Плановый запас RAM: около '+(Number(workers.value)*2)+' GiB.';});</script></body>''',1)
output=default_output();output.parent.mkdir(parents=True,exist_ok=True)
with output.open('x',encoding='utf-8') as stream:stream.write(html)
print(json.dumps({'output':str(output),'warnings':info['warnings'],'delivery':describe(output)},ensure_ascii=False))
