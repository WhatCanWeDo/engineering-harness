#!/usr/bin/env python3
"""Build this standalone design document using the shared readable quiz template."""
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

with tempfile.TemporaryDirectory(prefix='knowledge-design-') as folder:
    intermediate = Path(folder) / 'base.html'
    process = subprocess.run([sys.executable, str(SCRIPTS / 'render_explainer.py'),
                              str(HERE / 'content.json'), '--output', str(intermediate)],
                             capture_output=True, text=True, check=True)
    info = json.loads(process.stdout)
    html = intermediate.read_text()

for target, fragment in re.findall(r'<!-- visual:([a-z]+) -->(.*?)<!-- /visual -->',
                                   (HERE / 'visuals.html').read_text(), re.S):
    pattern = re.compile(r'(<section id="' + target + r'">.*?)(</section>)', re.S)
    html, count = pattern.subn(lambda m: m[1] + fragment + m[2], html, count=1)
    if count != 1:
        raise ValueError('Missing insertion section: ' + target)
html = html.replace('</style>', (HERE / 'visuals.css').read_text() + '\n</style>', 1)
html = html.replace('</body>', '<script>\n' + (HERE / 'visuals.js').read_text() + '\n</script></body>', 1)
output = default_output()
output.parent.mkdir(parents=True, exist_ok=True)
with output.open('x', encoding='utf-8') as stream:
    stream.write(html)
print(json.dumps({'output': str(output), 'warnings': info['warnings'],
                  'delivery': describe(output)}, ensure_ascii=False))
