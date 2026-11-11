"""Automatic project organization. Affiliations are ranking hints, never ACLs."""
from collections import defaultdict
import json
import os
from pathlib import Path
import re
import subprocess

from .knowledge import encode, fail, ident, sha, string_list

SCHEMA = """
CREATE TABLE IF NOT EXISTS subproject_catalog(project_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS task_organization(task_id TEXT PRIMARY KEY REFERENCES tasks(task_id), payload TEXT NOT NULL);
"""
MARKERS = {'pyproject.toml', 'package.json', 'Cargo.toml', 'go.mod', 'SKILL.md', '__init__.py'}
CONTAINERS = {'apps', 'packages', 'services', 'components', 'skills', 'experiments', 'workflows', 'src', 'lib'}
UTILITY = {'tests', 'test', 'docs', 'doc', 'scripts', 'assets', 'fixtures', 'shared', 'common', 'utils', 'examples', 'evals'}
IGNORED = {'.git', '.harness', '.venv', 'venv', 'node_modules', '__pycache__', 'build', 'dist', 'target', 'vendor', '.next', '.cache', '.agents', '.claude'}
GENERIC_TAGS = {'python', 'javascript', 'typescript', 'test', 'tests', 'testing', 'code-map', 'observation', 'procedure', 'documentation', 'bug', 'fix', 'project', 'general', 'тесты', 'код', 'проект'}


def workspace_root(cwd=None):
    start = Path(cwd or Path.cwd()).resolve()
    for p in (start, *start.parents):
        if p == Path.home().resolve() or p.parent == p: return None
        if (p/'.git').exists() or any((p/m).is_file() for m in ('pyproject.toml','package.json','Cargo.toml','go.mod')):
            return p
    # Do not scan HOME or arbitrary ancestors when there is no identifiable repository.
    return None


def inventory(root):
    if root is None: return [], {'method':'unavailable','complete':False}
    root=Path(root).resolve(); names=[]; method='bounded_walk'; complete=True
    try:
        top=subprocess.run(['git','-C',str(root),'rev-parse','--show-toplevel'],capture_output=True,text=True,timeout=5)
        if top.returncode==0 and Path(top.stdout.strip()).resolve()==root:
            result=subprocess.run(['git','-C',str(root),'ls-files','--cached','--others','--exclude-standard','-z'],capture_output=True,timeout=10)
            if result.returncode==0 and len(result.stdout)<=8*1024**2:
                names=result.stdout.decode('utf-8').split('\0'); method='git_file_names'
            else: complete=False
    except (OSError,subprocess.TimeoutExpired,UnicodeError):
        complete=False
    if method!='git_file_names':
        names=[]
        for current, dirs, files in os.walk(root,followlinks=False):
            here=Path(current); rel=here.relative_to(root)
            dirs[:]=sorted(d for d in dirs if d not in IGNORED and not d.startswith('.') and not (here/d).is_symlink())
            if len(rel.parts)>=6:
                if dirs: complete=False
                dirs[:]=[]
            for name in sorted(files):
                names.append((rel/name).as_posix())
                if len(names)>=20000: complete=False;break
            if len(names)>=20000:break
    accepted=[]
    for name in sorted(set(names)):
        if not name: continue
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or any(part in IGNORED or part.startswith('.') for part in p.parts):continue
        if len(p.parts)>7: complete=False;continue
        full=root/p
        if not full.is_file() or any(q.is_symlink() for q in (full,*full.parents) if q.is_relative_to(root)):continue
        accepted.append(p.as_posix())
        if len(accepted)>=20000: complete=False;break
    return accepted, {'method':method,'complete':complete,'files':len(accepted)}


def group_id(project, kind, key):
    return 'S-'+sha(encode([project,kind,key]))[:24]


def file_groups(project, files):
    directories=defaultdict(list)
    for name in files:
        for parent in Path(name).parents:
            if parent==Path('.'):break
            directories[parent.as_posix()].append(name)
    proposed={}
    for path, members in directories.items():
        parts=Path(path).parts
        if parts[0] in UTILITY:continue
        markers=[name for name in members if Path(name).parent.as_posix()==path and Path(name).name in MARKERS]
        conventional=(len(parts)==2 and parts[0] in CONTAINERS)
        domain=(len(parts)==1 and parts[0] not in CONTAINERS|UTILITY)
        if not markers and not ((conventional or domain) and len(members)>=2):continue
        proposed[path]={'id':group_id(project,'component',path),'name':parts[-1],'kind':'component','paths':[path],
                        'state':'active','basis':'package_marker' if markers else 'directory_cluster','support':markers[:3] or members[:3]}
    # A generic src/lib container with __init__ is not a useful sibling domain.
    for p in list(proposed):
        if p in CONTAINERS:proposed.pop(p)
    groups=sorted(proposed.values(),key=lambda g:g['paths'][0])
    for g in groups:
        path=g['paths'][0];parents=[x for x in groups if path.startswith(x['paths'][0]+'/')]
        g['parent_id']=max(parents,key=lambda x:len(x['paths'][0]))['id'] if parents else None
    return groups


def topic_groups(store, project):
    support=defaultdict(set)
    for record in store._records():
        if record['scope']!='project' or record['project_id']!=project or record['state']!='active' or not store._fresh(record):continue
        for tag in record.get('tags',[]):
            key=' '.join(tag.casefold().split())
            if not 3<=len(key)<=60 or key in GENERIC_TAGS or '/' in key or '\\' in key:continue
            support[key].add(record['origin_task'])
    return [{'id':group_id(project,'topic',tag),'name':tag,'kind':'topic','paths':[],'parent_id':None,
             'state':'active','basis':'recurring_tag','support_tasks':len(tasks)}
            for tag,tasks in sorted(support.items()) if len(tasks)>=2]


def catalog(store, project):
    ident(project,'project ID')
    row=store.db.execute('SELECT payload FROM subproject_catalog WHERE project_id=?',(project,)).fetchone()
    return json.loads(row[0]) if row else {'project_id':project,'version':1,'revision':None,'groups':[],'inventory':{'method':'not_discovered','complete':False}}


def refresh(store, project, root=None):
    ident(project,'project ID')
    old=catalog(store,project);files,info=inventory(root)
    groups=file_groups(project,files)
    component_names={g['name'].casefold() for g in groups}
    groups += [g for g in topic_groups(store,project) if g['name'] not in component_names]
    if len(groups)>100:info['complete']=False;info['groups_truncated']=True;groups=groups[:100]
    current={g['id'] for g in groups}
    # Incomplete discovery must not declare disappeared components retired.
    for previous in old['groups']:
        if previous['id'] not in current:
            state='retired' if info['complete'] or previous['kind']=='topic' else previous['state']
            groups.append(dict(previous,state=state))
    value={'version':1,'project_id':project,'groups':sorted(groups,key=lambda g:g['id']),
           'inventory':info,'inventory_sha256':sha(encode(files)),'algorithm':'components-and-recurring-tags-v1'}
    value['revision']=sha(encode(value))
    if old.get('revision')==value['revision']:return old
    with store._write():
        store.db.execute('INSERT OR REPLACE INTO subproject_catalog VALUES(?,?)',(project,encode(value)))
        store._event('subproject_catalog',{'project_id':project,'revision':value['revision']})
    return value


def normalize_paths(paths):
    string_list(paths,'paths')
    result=[]
    for name in paths:
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or str(p)!=name or name=='.':fail('validation','Task paths must be relative repository paths')
        if name not in result:result.append(name)
    return sorted(result)


def path_memberships(paths, groups):
    found=set()
    for name in paths:
        matches=[g for g in groups if any(name==p or name.startswith(p+'/') for p in g['paths'])]
        if matches:
            depth=max(max(len(p) for p in g['paths']) for g in matches)
            found.update(g['id'] for g in matches if max(len(p) for p in g['paths'])==depth)
    return sorted(found)


def route(task, cat, paths, cwd_path=None):
    groups=[g for g in cat['groups'] if g['state']=='active']
    ids=path_memberships(paths,groups);basis='task_paths'
    if not ids and not paths and cwd_path:
        ids=path_memberships([cwd_path],groups);basis='working_directory'
    if not ids:
        # Only substantial names; never route on generic fragments like "api"/"src".
        tokens=set(re.findall(r'[\w-]+',task['goal'].casefold()))
        matches=[]
        for g in groups:
            labels={x for x in re.findall(r'[\w-]+',g['name'].casefold()) if len(x)>=(3 if g['kind']=='topic' else 4) and x not in GENERIC_TAGS}
            if labels and labels<=tokens:matches.append(g['id'])
        names=[g['name'].casefold() for g in groups if g['id'] in matches]
        if len(matches)<=3 and len(set(names))==len(names):ids=sorted(matches)
        basis='goal_terms' if ids else 'project_fallback'
    ids=ids[:8]
    return {'version':1,'project_id':task['project_id'],'subproject_ids':ids,'basis':basis,
            'classification':'crosscutting' if len(ids)>1 else 'subproject' if ids else 'project',
            'input_paths':paths,'catalog_revision':cat['revision'],'catalog':groups,
            'catalog_inventory':cat['inventory'],'sealed':False,'shared_knowledge':True}


def get_route(store, task_id):
    row=store.db.execute('SELECT payload FROM task_organization WHERE task_id=?',(task_id,)).fetchone()
    return json.loads(row[0]) if row else None


def attach(store, task_id, cat, paths=None, cwd_path=None):
    previous=get_route(store,task_id)
    if previous:
        if paths is not None and normalize_paths(paths)!=previous['input_paths']:
            fail('conflict','Existing task has different paths; use a new task ID')
        return previous
    task=store.get_task(task_id);value=route(task,cat,normalize_paths(paths or []),cwd_path)
    with store._write():
        store.db.execute('INSERT INTO task_organization VALUES(?,?)',(task_id,encode(value)))
    return value


def summarize(value):
    if not value:return None
    return {k:v for k,v in value.items() if k not in ('catalog','input_paths')}


def refine(store, task_id, role, selection):
    value=get_route(store,task_id)
    if value is None:
        if selection is not None:fail('unavailable','Task has no frozen subproject catalog')
        return None
    task=store.get_task(task_id);store._role(task,role)
    ids=value['subproject_ids'] if selection is None else sorted(set(string_list(selection,'subproject_ids')))
    if len(ids)>8 or not set(ids)<={g['id'] for g in value['catalog']}:fail('validation','Scout must select IDs from the task catalog, maximum eight')
    with store._write():
        current=get_route(store,task_id)
        has_packets=store.db.execute('SELECT 1 FROM packets WHERE task_id=? LIMIT 1',(task_id,)).fetchone()
        if current['sealed'] or has_packets:
            if ids!=current['subproject_ids']:fail('conflict','Subproject routing already frozen for this task')
            return current
        value=dict(current,subproject_ids=ids,sealed=True,
                   classification='crosscutting' if len(ids)>1 else 'subproject' if ids else 'project')
        if selection is not None:value['basis']='native_scout'
        store.db.execute('UPDATE task_organization SET payload=? WHERE task_id=?',(encode(value),task_id))
    return value


def record_groups(record, groups):
    ids=set(record.get('subproject_ids',[]))
    paths=[s for s in record.get('symbols',[]) if '/' in s or '.' in s]
    ids.update(path_memberships(paths,groups))
    tags={' '.join(t.casefold().split()) for t in record.get('tags',[])}
    ids.update(g['id'] for g in groups if g['name'].casefold() in tags)
    return ids


def affiliations(store, task, proposal):
    value=get_route(store,task['task_id'])
    if 'subproject_ids' in proposal:
        ids=sorted(set(string_list(proposal['subproject_ids'],'subproject_ids')))
        allowed={g['id'] for g in (value or {}).get('catalog',[])}
        if len(ids)>8 or not set(ids)<=allowed:fail('validation','Unknown subproject affiliation for task snapshot')
        return ids
    if proposal.get('entry_id'):return store._current(proposal['entry_id']).get('subproject_ids',[])
    if not value:return []
    inferred=record_groups(proposal,value['catalog'])
    return sorted(inferred or value['subproject_ids'])[:8]


def rank(store, task, ordered, records, exact=()):
    value=get_route(store,task['task_id'])
    if not value or not value['subproject_ids']:return ordered
    own=set(value['subproject_ids']);fixed=[k for k in ordered if k in exact];rest=[k for k in ordered if k not in exact]
    positions={k:i for i,k in enumerate(rest)}
    scores={k:i-(2 if own & record_groups(records[k],value['catalog']) else 0) for i,k in enumerate(rest)}
    return fixed+sorted(rest,key=lambda k:(scores[k],positions[k]))


def brief(store, task):
    value=get_route(store,task['task_id'])
    if not value:return None
    own=set(value['subproject_ids'])
    groups=sorted(value['catalog'],key=lambda g:(g['id'] not in own,g['name'],g['id']))[:12]
    return {'routing':summarize(value),'candidates':[{k:g[k] for k in ('id','name','kind','paths','basis')} for g in groups],
            'omitted_groups':max(0,len(value['catalog'])-len(groups)),
            'instruction':'Optional subproject_ids: select up to eight listed IDs (or [] for project-wide) by task meaning. No new groups here. Affiliation never grants access or excludes sibling knowledge. Shared final routing is frozen before the first packet.'}
