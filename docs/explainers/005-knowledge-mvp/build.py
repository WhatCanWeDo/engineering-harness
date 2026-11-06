#!/usr/bin/env python3
"""Build a readable report from actual receipts and the independent retrieval fixture."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRIPTS = ROOT / 'skills' / 'understand-changes' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from delivery import default_output, describe

benchmark = json.loads((ROOT / 'evals/knowledge-mvp/2026-11-03/mvp2/benchmark-final/results.json').read_text())
gate = ROOT / 'evals/knowledge-mvp/2026-11-03/mvp2/gate-final'
receipt = json.loads((gate / 'receipt.json').read_text())
if receipt['status'] != 'pass' or benchmark['status'] != 'pass':
    raise SystemExit('Report requires passing saved receipts; inspect actual failures.')
log = (gate / 'test_*.py.log').read_text()
count = re.search(r'Ran (\d+) tests', log).group(1)
content = (HERE / 'content.json').read_text().replace('{{total_tests}}', count)
with tempfile.TemporaryDirectory(prefix='knowledge-mvp-report-') as folder:
    source = Path(folder) / 'content.json'
    source.write_text(content)
    intermediate = Path(folder) / 'base.html'
    result = subprocess.run([sys.executable, str(SCRIPTS / 'render_explainer.py'), str(source), '--output', str(intermediate)],
                            capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    html = intermediate.read_text()
for target, fragment in re.findall(r'<!-- visual:([a-z]+) -->(.*?)<!-- /visual -->', (HERE / 'visuals.html').read_text(), re.S):
    pattern = re.compile(r'(<section id="' + target + r'">.*?)(</section>)', re.S)
    html, n = pattern.subn(lambda m: m[1] + fragment + m[2], html, count=1)
    if n != 1: raise ValueError('Missing section ' + target)
html = html.replace('</style>', (HERE / 'visuals.css').read_text() + '\n</style>', 1)
# Escape JSON for safe embedding in a script data block.
data = json.dumps(benchmark, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
html = html.replace('</body>', '<script type="application/json" id="retrieval-results">' + data + '</script><script>\n' + (HERE / 'visuals.js').read_text() + '\n</script></body>', 1)
output = default_output()
output.parent.mkdir(parents=True, exist_ok=True)
with output.open('x', encoding='utf-8') as stream: stream.write(html)
print(json.dumps({'output': str(output), 'warnings': info['warnings'], 'delivery': describe(output)}, ensure_ascii=False))
