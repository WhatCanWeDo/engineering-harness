"""Project-local knowledge routing and explicit, source-bound code navigation."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from .knowledge import KnowledgeStore, fail, ident, now, sha

CONFIG = Path('.harness/knowledge/project.json')


def load_json(path):
    path = Path(path)
    if path.stat().st_size > 4 * 1024**2: fail('validation', 'Project JSON exceeds 4 MiB')
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        try: os.link(name, path)
        except FileExistsError: fail('conflict', 'Output exists; choose a new path')
    finally: os.unlink(name)


def ancestors(start):
    start = Path(start).expanduser().resolve()
    for root in (start, *start.parents):
        yield root
        if (root / '.git').exists(): break


def find_root(start=None):
    for root in ancestors(start or Path.cwd()):
        if (root / CONFIG).exists(): return root
    return None


def config(root):
    root = Path(root).expanduser().resolve()
    value = load_json(root / CONFIG)
    if not isinstance(value, dict) or value.get('version') != 1: fail('validation', 'Unsupported project profile')
    ident(value.get('project_id'), 'project ID')
    if value.get('database') != 'knowledge.sqlite3': fail('validation', 'Project database must be local knowledge.sqlite3')
    if value.get('mode') not in ('lexical', 'semantic', 'hybrid'): fail('validation', 'Invalid project retrieval mode')
    return value


def database(root):
    return Path(root) / CONFIG.parent / 'knowledge.sqlite3'


def status(root):
    root = Path(root).expanduser().resolve(); value = config(root); db = database(root)
    if not db.is_file(): fail('not_initialized', 'Project profile exists but database is missing; no global fallback')
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        binding = conn.execute("SELECT value FROM meta WHERE key='project_id'").fetchone()
        if not binding or binding[0] != value['project_id']: fail('conflict', 'Project DB binding mismatch')
        counts = {name: conn.execute('SELECT count(*) FROM ' + name).fetchone()[0] for name in ('tasks','entries','evidence','jobs','packets')}
    return {'status':'ready','project_id':value['project_id'],'root':str(root),'db':str(db),'mode':value['mode'],'counts':counts,'empty':not any(counts.values()),'shared_retrieval':'disabled; no implicit cross-database queries','profile':str(root/CONFIG)}


def initialize(root, project_id, mode='lexical'):
    root = Path(root).expanduser().resolve(); ident(project_id, 'project ID')
    if not root.is_dir(): fail('not_found', 'Project root must be an existing directory')
    if mode not in ('lexical', 'semantic', 'hybrid'): fail('validation', 'Invalid retrieval mode')
    destination = root / CONFIG.parent
    if destination.exists():
        if not (root/CONFIG).is_file(): fail('conflict', 'Knowledge directory already exists without profile; no files overwritten')
        existing = config(root)
        if existing['project_id'] != project_id or existing['mode'] != mode:
            fail('conflict', 'Project already initialized with different settings; no reset performed')
        if not database(root).exists():
            if any(destination.glob('knowledge.sqlite3-*')):
                fail('conflict', 'Database missing but journal files exist; inspect recovery first')
            with tempfile.TemporaryDirectory(prefix='.knowledge-empty-', dir=destination.parent) as temporary:
                staged = Path(temporary)/'knowledge.sqlite3'
                with KnowledgeStore(staged) as store:
                    store.db.execute("INSERT INTO meta VALUES('project_id',?)", (project_id,))
                    store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                try: os.link(staged, database(root))
                except FileExistsError: fail('conflict','Database appeared concurrently; no overwrite')
            ignore = destination/'.gitignore'
            if not ignore.exists():
                with ignore.open('x') as f: f.write('*.sqlite3\n*.sqlite3-*\n')
            return dict(status(root), initialized=True, recreated_empty=True)
        return dict(status(root), initialized=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.knowledge-init-', dir=destination.parent))
    try:
        with KnowledgeStore(stage/'knowledge.sqlite3') as store:
            store.db.execute("INSERT INTO meta VALUES('project_id',?)", (project_id,))
            store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        write_new(stage/'project.json', {'version':1,'project_id':project_id,'database':'knowledge.sqlite3','mode':mode})
        (stage/'.gitignore').write_text('*.sqlite3\n*.sqlite3-*\n')
        try: stage.rename(destination)
        except FileExistsError: fail('conflict', 'Project initialized concurrently; rerun without deleting files')
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return dict(status(root), initialized=True, agent_activation='Invoke knowledge-cycle or enable it in project instructions; native files not overwritten')


def runtime_settings(explicit_root=None):
    """CLI > real env > project profile > runtime model profile > legacy global DB."""
    settings = {}
    runtime = os.environ.get('HARNESS_RUNTIME_PROFILE')
    if runtime and Path(runtime).is_file(): settings.update(load_json(runtime))
    root = Path(explicit_root).expanduser().resolve() if explicit_root else find_root()
    if explicit_root and not (root/CONFIG).is_file(): fail('not_initialized', 'Explicit project root has no project profile')
    for folder in ancestors(root or Path.cwd()):
        profile = folder/'.harness/knowledge.local.json'
        if profile.is_file():
            settings.update(load_json(profile)); break
    if root:
        settings.update(config(root)); settings['db'] = str(database(root)); settings['root'] = str(root)
    if not isinstance(settings, dict): fail('validation', 'Local profile must be an object')
    for key in ('mode','semantic_model'):
        if key in settings and not isinstance(settings[key], str): fail('validation', 'Invalid profile '+key)
    return settings


def scoped_file(root, name):
    p = Path(name)
    if not isinstance(name, str) or not name or p.is_absolute() or '..' in p.parts or str(p) != name:
        fail('validation', 'Expected relative file path')
    full = root/p
    if any(q.is_symlink() for q in (full, *full.parents) if q.is_relative_to(root)):
        fail('validation', 'Source symlinks are not scanned')
    if not full.is_file() or not full.resolve().is_relative_to(root): fail('not_found', 'Missing scoped file: '+name)
    if full.stat().st_size > 2*1024**2: fail('validation', 'Map source exceeds 2 MiB: '+name)
    return full


def declarations(data, suffix):
    if suffix != '.py': return [], 'file_only'
    try: tree = ast.parse(data)
    except (SyntaxError, UnicodeError, ValueError): return [], 'python_parse_unavailable'
    symbols=[]
    def visit(nodes, prefix=''):
        for n in nodes:
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name=prefix+n.name; symbols.append({'name':name,'line':n.lineno,'kind':'class' if isinstance(n,ast.ClassDef) else 'function'})
                if isinstance(n,ast.ClassDef): visit(n.body,name+'.')
    visit(tree.body)
    return symbols[:300], 'python_ast' if len(symbols)<=300 else 'python_ast_truncated'


def make_map(root, files, output, refresh=False):
    root=Path(root).expanduser().resolve()
    if not isinstance(files,list) or not files or len(files)>1000 or any(not isinstance(x,str) for x in files) or len(set(files))!=len(files):
        fail('validation','Select 1..1000 unique relative files explicitly')
    records=[]
    for name in sorted(files):
        path=scoped_file(root,name); data=path.read_bytes()
        symbols,method=declarations(data,path.suffix)
        records.append({'path':name,'sha256':sha(data),'bytes':len(data),'symbols':symbols,'method':method})
    result={'version':1,'created_at':now(),'project_id':config(root)['project_id'] if (root/CONFIG).is_file() else None,
            'scope':'selected_files_only','files':records,'limitations':['No call graph or inferred service dependencies','New unselected files are not detected; regenerate file list when scope changes','A source hash verifies freshness, not correctness of an architectural interpretation']}
    output = Path(output)
    if refresh and output.exists():
        old = output.read_bytes(); previous = load_json(output)
        if previous.get('version') != 1 or previous.get('scope') != 'selected_files_only':
            fail('conflict', 'Refresh only replaces a generated code map')
        fd, temp = tempfile.mkstemp(dir=output.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(result,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
            if output.read_bytes()!=old: fail('conflict','Map changed concurrently')
            os.replace(temp,output)
        finally:
            if Path(temp).exists(): Path(temp).unlink()
    else: write_new(output,result)
    return {'output':str(Path(output).resolve()),'files':len(records),'symbols':sum(len(r['symbols']) for r in records),'knowledge_entries_written':0}


def check_map(root, manifest):
    root=Path(root).expanduser().resolve(); value=load_json(manifest)
    if value.get('version')!=1 or value.get('scope')!='selected_files_only': fail('validation','Unsupported code map')
    changes=[]
    for item in value['files']:
        try:
            p=scoped_file(root,item['path'])
            if sha(p.read_bytes())!=item['sha256']: changes.append({'path':item['path'],'state':'changed'})
        except (OSError,ValueError): changes.append({'path':item['path'],'state':'missing_or_unreadable'})
    return {'status':'stale' if changes else 'current','changes':changes,'scope':'selected_files_only','checked_files':len(value['files']), 'checked_at':now()}


def navigation(root, goal, limit=6):
    """Small optional Scout hint, never a substitute for knowledge/evidence."""
    manifest=Path(root)/'.harness/code-map.json'
    if not manifest.is_file(): return {'status':'not_created','hint':'Create an explicit selected-file map if useful'}
    state=check_map(root,manifest)
    if state['status']!='current': return state | {'hint':'Do not rely on stale locations; regenerate map from current selected sources'}
    value=load_json(manifest); terms=set(re.findall(r'\w+',goal.casefold()))
    ranked=[]
    for item in value['files']:
        hay=item['path']+' '+' '.join(s['name'] for s in item['symbols'])
        score=sum(t in hay.casefold() for t in terms if len(t)>1)
        if score: ranked.append((score,item))
    ranked.sort(key=lambda x:(-x[0],x[1]['path']))
    return {'status':'current','scope':'selected_files_only','map_path':str(manifest),'matches':[{'path':i['path'],'sha256':i['sha256'],'symbols':i['symbols'][:10]} for _,i in ranked[:limit]],'hint':'Navigation observations only. Inspect sources before deriving service behavior; not an independent fact verification.'}


def register(commands):
    sub=commands.add_parser('project',help='Project-local empty DB and explicit code map').add_subparsers(dest='project_action',required=True)
    p=sub.add_parser('init');p.add_argument('--root',required=True);p.add_argument('--id',required=True);p.add_argument('--mode',choices=['lexical','semantic','hybrid'],default='lexical')
    p=sub.add_parser('status');p.add_argument('--root',required=True)
    p=sub.add_parser('map');p.add_argument('--root',required=True);p.add_argument('--files',required=True);p.add_argument('--output',required=True);p.add_argument('--refresh',action='store_true')
    p=sub.add_parser('map-check');p.add_argument('--root',required=True);p.add_argument('--input',required=True)


def dispatch(args):
    if args.project_action=='init':return initialize(args.root,args.id,args.mode)
    if args.project_action=='status':return status(args.root)
    if args.project_action=='map':return make_map(args.root,load_json(args.files),args.output,args.refresh)
    return check_map(args.root,args.input)
