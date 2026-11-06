"""Immutable experiment inputs and content-bound event records (stdlib only)."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import sqlite3
import tempfile
import uuid


class ABError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ABError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    path = Path(path)
    require(path.stat().st_size <= 8 * 1024 * 1024, 'JSON exceeds 8 MiB')
    return json.loads(path.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ABError('Non-finite JSON')))


def put(path, value):
    """Atomic create, content-bound idempotency. Never overwrite an event."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical(value) + b'\n'
    if path.exists():
        require(path.read_bytes() == data, f'Immutable record conflict: {path.name}')
        return
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            require(path.read_bytes() == data, 'Concurrent record conflict')
    finally:
        os.unlink(temp)


def now():
    return datetime.now(timezone.utc).isoformat()


def number(value, name, positive=False):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, f'{name}: finite nonnegative number required')
    require(not positive or value > 0, f'{name}: must be positive')
    return value


def text(value, name):
    require(isinstance(value, str) and bool(value.strip()), f'{name}: nonempty string required')
    return value


def relative(name):
    p = Path(name)
    require(isinstance(name, str) and name and not p.is_absolute() and '..' not in p.parts and str(p) == name and name != '.', 'Unsafe relative path')
    return p


def file_at(root, name):
    p = root / relative(name)
    require(not any(q.is_symlink() for q in [p, *p.parents] if q != root.parent), 'Symlinks unsupported in snapshots')
    require(p.is_file() and p.resolve().is_relative_to(root.resolve()), f'Not a regular scoped file: {name}')
    return p


def snapshot(root, names, dest):
    root, dest = Path(root).resolve(), Path(dest)
    require(isinstance(names, list) and names and len(set(names)) == len(names), 'Explicit unique file list required')
    files = {}
    for name in sorted(names):
        src = file_at(root, name)
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        before = sha(src)
        shutil.copy2(src, target)
        require(before == sha(target) == sha(src), 'Source changed while copying')
        files[name] = {'sha256': before, 'executable': bool(src.stat().st_mode & 0o111)}
    return {'files': files, 'digest': digest(files)}


def verify_tree(root, manifest):
    root = Path(root)
    actual = sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink())
    require(actual == sorted(manifest['files']), f'Snapshot file set drift: {root.name}')
    for name, spec in manifest['files'].items():
        p = file_at(root, name)
        require(sha(p) == spec['sha256'] and bool(p.stat().st_mode & 0o111) == spec['executable'], f'Snapshot drift: {name}')
    require(digest(manifest['files']) == manifest['digest'], 'Manifest digest mismatch')


def diff(a, b, prefix=''):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(a.keys() | b.keys()):
            pointer = prefix + '/' + k.replace('~', '~0').replace('/', '~1')
            out.extend([pointer] if k not in a or k not in b else diff(a[k], b[k], pointer))
        return out
    return [] if a == b else [prefix]


def build_config(raw, dest):
    required = ('agent', 'agent_version', 'model', 'reasoning', 'environment', 'permissions', 'tools', 'instructions', 'cache_policy', 'model_control')
    require(isinstance(raw, dict), 'Config must be an object')
    for k in required:
        require(k in raw, f'Missing effective configuration: {k}')
    files = snapshot(raw['root'], raw['files'], dest)
    effective = {k: v for k, v in raw.items() if k not in ('root', 'files')}
    effective['files'] = files['files']
    return {'effective': effective, 'digest': digest(effective), 'snapshot': files}


def plan(spec, destination):
    destination = Path(destination).expanduser().resolve()
    require(not destination.exists(), 'Experiment destination must be new')
    require(spec.get('version') == 1, 'Plan input version must be 1')
    text(spec.get('hypothesis'), 'hypothesis')
    require(spec.get('dataset') in ('development', 'fresh_validation'), 'dataset required')
    text(spec.get('dataset_provenance'), 'dataset_provenance')
    reps = spec.get('replicates')
    require(type(reps) is int and 1 <= reps <= 100, 'replicates 1..100')
    require(type(spec.get('seed')) is int, 'Explicit integer schedule seed required')
    tasks = spec.get('tasks')
    require(isinstance(tasks, list) and 0 < len(tasks) <= 100, 'tasks 1..100 required')
    ids = [text(t.get('id'), 'task id') for t in tasks]
    require(len(set(ids)) == len(ids), 'Duplicate task IDs')
    limits = spec.get('limits', {})
    for field in ('wall_seconds_per_run', 'calls_per_run', 'human_seconds_per_review'):
        number(limits.get(field), field, True)
    require(type(limits.get('max_runs')) is int and len(tasks) * reps * 2 <= limits['max_runs'], 'max_runs insufficient')
    require(spec.get('retry_policy') == 'none', 'MVP retries require a new linked experiment; retry_policy must be none')
    analysis = spec.get('analysis', {})
    require(analysis.get('primary') in ('human_seconds', 'cost'), 'primary must be human_seconds or cost')
    number(analysis.get('min_improvement'), 'min_improvement', True)
    require(analysis.get('max_correctness_regressions') == 0, 'MVP requires zero observed correctness regressions')
    review = spec.get('review', {})
    require(review.get('protocol') in ('personal_crossover', 'independent_reviewers'), 'Explicit review protocol required')
    review_reps = review.get('replicates')
    require(isinstance(review_reps, list) and len(set(review_reps)) == len(review_reps) and all(type(r) is int and 1 <= r <= reps for r in review_reps), 'Invalid review replicate subset')
    require(analysis['primary'] != 'human_seconds' or bool(review_reps), 'Human primary needs precommitted review subset')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.ab-plan-', dir=destination.parent))
    try:
        configs = {arm: build_config(spec[key], stage / 'inputs' / arm) for arm, key in [('A', 'baseline'), ('B', 'candidate')]}
        changes = diff(configs['A']['effective'], configs['B']['effective'])
        allowed = spec.get('allowed_changes', [])
        require(changes and isinstance(allowed, list) and changes == sorted(set(allowed)), f'Exact allowed_changes must equal actual JSON pointers: {changes}')
        for key in ('agent', 'agent_version', 'model', 'reasoning'):
            require(configs['A']['effective'][key] == configs['B']['effective'][key], f'MVP one stratum: {key} differs')
        task_records = []
        for i, task in enumerate(tasks):
            text(task.get('goal'), 'task goal')
            text(task.get('clarification_policy'), 'clarification policy')
            requirements = task.get('requirements')
            require(isinstance(requirements, list) and requirements and len(set(requirements)) == len(requirements) and all(isinstance(x, str) and x for x in requirements), 'Unique requirement IDs required')
            key = f't{i + 1:03}'
            snap = snapshot(task['root'], task['files'], stage / 'inputs' / key)
            for arm in configs:
                require(not (set(snap['files']) & set(configs[arm]['snapshot']['files'])), 'Config/task file collision')
            evaluator = task['evaluator']
            require(evaluator.get('kind') in ('command', 'external'), 'Evaluator kind command or external')
            text(evaluator.get('identity'), 'independent evaluator identity')
            require(evaluator.get('independent') is True, 'Evaluator must be independently authored')
            if evaluator['kind'] == 'command':
                argv = evaluator.get('argv')
                require(isinstance(argv, list) and argv and all(isinstance(x, str) for x in argv) and any('{evaluator}' in x for x in argv), 'argv must reference {evaluator}')
                number(evaluator.get('timeout_seconds'), 'evaluator timeout', True)
                source = Path(evaluator['path']).resolve()
                # Evaluator lives outside the agent starting tree.
                target = stage / 'evaluators' / key / 'evaluator'
                target.parent.mkdir(parents=True)
                shutil.copy2(source, target)
                ev = {k: v for k, v in evaluator.items() if k != 'path'}
                ev['sha256'] = sha(target)
            else:
                ev = dict(evaluator)
                require(ev.get('protected') is False, 'Protected backend unavailable in local MVP')
            task_records.append({k: task[k] for k in ('id', 'goal', 'requirements', 'clarification_policy')} | {'key': key, 'snapshot': snap, 'evaluator': ev})
        knowledge = spec.get('knowledge_db')
        knowledge_hash = None
        if knowledge:
            source = Path(knowledge).expanduser().resolve()
            require(source.is_file(), 'knowledge_db must already exist')
            with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(stage / 'knowledge.sqlite3') as dst:
                src.backup(dst)
            knowledge_hash = sha(stage / 'knowledge.sqlite3')
        rng = random.Random(spec['seed'])
        pairs = [(t['key'], r) for t in task_records for r in range(1, reps + 1)]
        rng.shuffle(pairs)
        orders = ['AB', 'BA'] * (len(pairs) // 2) + (['AB' if rng.randrange(2) == 0 else 'BA'] if len(pairs) % 2 else [])
        rng.shuffle(orders)
        schedule = []
        for pair, order in zip(pairs, orders):
            for arm in order:
                schedule.append({'run_id': uuid.uuid4().hex, 'task_key': pair[0], 'replicate': pair[1], 'arm': arm, 'order_in_pair': order.index(arm) + 1})
        value = {'version': 1, 'synthetic': spec.get('synthetic') is True, 'analysis_version': 'paired-descriptive-v1', 'experiment_id': uuid.uuid4().hex, 'created_at': now(), 'hypothesis': spec['hypothesis'], 'dataset': spec['dataset'], 'dataset_provenance': spec['dataset_provenance'], 'limits': limits, 'analysis': analysis, 'review': review, 'retry_policy': 'none', 'seed': spec['seed'], 'configs': configs, 'tasks': task_records, 'changes': changes, 'knowledge_sha256': knowledge_hash, 'schedule': schedule, 'trust_profile': 'local_cooperative', 'limit_enforcement': 'advisory_native_execution'}
        put(stage / 'plan.json', value)
        put(stage / 'seal.json', {'sha256': digest(value)})
        stage.rename(destination)
        return {'experiment': str(destination), 'plan_sha256': digest(value), 'planned_runs': len(schedule), 'status': 'planned', 'execution': 'not_started'}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


class Experiment:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.plan = read(self.path / 'plan.json')
        require(digest(self.plan) == read(self.path / 'seal.json')['sha256'], 'Plan drift')

    @contextmanager
    def lock(self):
        with (self.path / '.lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def task(self, run):
        return next(t for t in self.plan['tasks'] if t['key'] == run['task_key'])

    def run(self, run_id):
        found = [r for r in self.plan['schedule'] if r['run_id'] == run_id]
        require(len(found) == 1, 'Unknown run ID')
        return found[0]

    def records(self, kind, run_id=None):
        folder = self.path / 'records' / kind
        values = [read(p) for p in sorted(folder.glob('*.json'))]
        for v in values:
            require(v['experiment_sha256'] == digest(self.plan), 'Record bound to another experiment')
            require(v.get('record_sha256') == digest({k: x for k, x in v.items() if k != 'record_sha256'}), 'Stored receipt drift')
        return [v for v in values if run_id is None or v.get('run_id') == run_id]

    def save(self, kind, key, record):
        record = dict(record, experiment_sha256=digest(self.plan))
        record['record_sha256'] = digest({k: v for k, v in record.items() if k != 'record_sha256'})
        put(self.path / 'records' / kind / (digest(key) + '.json'), record)
        return {'status': 'recorded', 'kind': kind, 'record_sha256': digest(record)}

    def verify_inputs(self):
        for arm, config in self.plan['configs'].items():
            verify_tree(self.path / 'inputs' / arm, config['snapshot'])
        for task in self.plan['tasks']:
            verify_tree(self.path / 'inputs' / task['key'], task['snapshot'])
            if task['evaluator']['kind'] == 'command':
                require(sha(self.path / 'evaluators' / task['key'] / 'evaluator') == task['evaluator']['sha256'], 'Evaluator drift')
        if self.plan['knowledge_sha256']:
            require(sha(self.path / 'knowledge.sqlite3') == self.plan['knowledge_sha256'], 'Knowledge snapshot drift')

    def prepare(self):
        self.verify_inputs()
        for run in self.plan['schedule']:
            base = self.path / 'runs' / run['run_id']
            assignment = base / 'assignment.json'
            if assignment.exists():
                prepared = self.records('prepared', run['run_id'])
                require(prepared and prepared[0]['assignment_sha256'] == digest(read(assignment)), 'Prepared assignment drift/incomplete prepare')
                continue
            require(not base.exists(), 'Partial prepare exists; inspect/remove only this undispatched run before retry')
            work = base / 'workspace'
            work.mkdir(parents=True)
            for source in (run['task_key'], run['arm']):
                shutil.copytree(self.path / 'inputs' / source, work, dirs_exist_ok=True)
            state = base / 'state'; state.mkdir()
            if self.plan['knowledge_sha256']:
                shutil.copy2(self.path / 'knowledge.sqlite3', state / 'knowledge.sqlite3')
            else:
                from ..knowledge import KnowledgeStore
                with KnowledgeStore(state / 'knowledge.sqlite3'):
                    pass
            cfg = self.plan['configs'][run['arm']]
            task = self.task(run)
            data = {'version': 1, 'experiment_sha256': digest(self.plan), 'run_id': run['run_id'], 'task': {k: task[k] for k in ('id', 'goal', 'requirements', 'clarification_policy')}, 'workspace': str(work), 'state': str(state), 'knowledge_db': str(state / 'knowledge.sqlite3'), 'effective_config': cfg['effective'], 'config_sha256': cfg['digest'], 'starting_sha256': digest({'task': task['snapshot']['digest'], 'config': cfg['snapshot']['digest']}), 'limits': self.plan['limits'], 'instructions': ['Start a fresh native session. Apply and inspect effective config.', 'Use only this workspace and run-local knowledge DB; do not publish memory.', 'Do not read sibling runs, evaluator materials or experiment mapping.', 'Record global skill/memory/hook isolation capabilities honestly; folders are not a security boundary.', 'Stop at first completed autonomous output F0; repair feedback belongs to F1.', 'All attributable calls and sidecars must be recorded. No implicit retry.']}
            put(assignment, data)
            self.save('prepared', [run['run_id']], {'run_id': run['run_id'], 'assignment_sha256': digest(data)})
        return {'status': 'prepared', 'runs': len(self.plan['schedule']), 'isolation': 'requires_native_adapter_attestation'}

    def receipt(self, rid):
        run = self.run(rid)
        assignment = read(self.path / 'runs' / rid / 'assignment.json')
        base = self.path / 'outputs' / rid / 'F0'
        output_hash = self.output(rid)[1]['digest'] if base.exists() else None
        return {'run_id': rid, 'config_sha256': assignment['config_sha256'], 'output_sha256': output_hash,
                'status': 'completed', 'duration_seconds': None, 'session_id': '', 'fresh_session': True,
                'isolation': 'unavailable', 'isolation_evidence': '', 'skill_loading_evidence': '',
                'accounting_complete': False, 'request_keys': []}

    def dispatch(self):
        self.verify_inputs()
        for run in self.plan['schedule']:
            rid = run['run_id']
            if self.records('execution', rid):
                continue
            assignment = self.path / 'runs' / rid / 'assignment.json'
            require(assignment.exists(), 'Run prepare first')
            existing = self.records('dispatch', rid)
            data = read(assignment)
            require(self.records('prepared', rid)[0]['assignment_sha256'] == digest(data), 'Prepared assignment drift')
            if not existing:
                names = dict(self.task(run)['snapshot']['files'])
                names.update(self.plan['configs'][run['arm']]['snapshot']['files'])
                verify_tree(Path(data['workspace']), {'files': names, 'digest': digest(names)})
                self.save('dispatch', [rid], {'run_id': rid, 'assignment_sha256': digest(data)})
            else:
                require(existing[0]['assignment_sha256'] == digest(data), 'Assignment drift')
            return {'status': 'assignment_ready', 'run_id': rid, 'assignment': str(assignment), 'execution': 'manual_native_session', 'reused': bool(existing)}
        return {'status': 'all_runs_received'}

    def freeze(self, rid, source, files, revision='F0'):
        self.run(rid)
        require(revision in ('F0', 'F1'), 'MVP supports F0 and F1 only')
        require(self.records('dispatch', rid), 'Dispatch run before freeze')
        if revision == 'F1':
            require(self.records('execution', rid), 'Freeze F0 and ingest execution before F1')
        base = self.path / 'outputs' / rid / revision
        require(not base.exists(), 'Output revision already frozen')
        base.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(dir=base.parent, prefix='.freeze-'))
        try:
            manifest = snapshot(source, files, stage / 'tree')
            put(stage / 'manifest.json', manifest)
            stage.rename(base)
        finally:
            if stage.exists(): shutil.rmtree(stage)
        return {'run_id': rid, 'revision': revision, 'output_sha256': manifest['digest'], 'tree': str(base / 'tree')}

    def output(self, rid, revision='F0'):
        self.run(rid)
        base = self.path / 'outputs' / rid / revision
        manifest = read(base / 'manifest.json')
        verify_tree(base / 'tree', manifest)
        return base / 'tree', manifest

    def ingest(self, kind, value):
        require(isinstance(value, dict), 'Record must be an object')
        rid = value.get('run_id')
        run = self.run(rid) if rid else None
        if kind == 'execution':
            require(run and self.records('dispatch', rid), 'Dispatched run required')
            assignment = read(self.path / 'runs' / rid / 'assignment.json')
            require(digest(assignment) == self.records('dispatch', rid)[0]['assignment_sha256'], 'Assignment drift')
            require(value.get('config_sha256') == assignment['config_sha256'], 'Effective config hash mismatch')
            require(value.get('status') in ('completed', 'timeout', 'budget_exhausted', 'infra_error', 'aborted'), 'Invalid execution status')
            number(value.get('duration_seconds'), 'duration_seconds')
            text(value.get('session_id'), 'session_id')
            require(value.get('fresh_session') is True, 'Fresh session attestation required')
            for other in self.records('execution'):
                require(other['run_id'] == rid or other['session_id'] != value['session_id'], 'Reused native session')
            require(value.get('isolation') in ('attested', 'unavailable', 'violated'), 'isolation attestation required')
            text(value.get('isolation_evidence'), 'isolation_evidence')
            text(value.get('skill_loading_evidence'), 'skill_loading_evidence')
            require(type(value.get('accounting_complete')) is bool, 'accounting_complete required')
            reqs = value.get('request_keys')
            require(isinstance(reqs, list) and all(isinstance(k, list) and len(k) == 2 and all(isinstance(x, str) and x for x in k) for k in reqs) and len({digest(k) for k in reqs}) == len(reqs), 'Unique [provider,request_id] request_keys required')
            if value['status'] == 'completed' or value.get('output_sha256'):
                _, manifest = self.output(rid)
                require(value.get('output_sha256') == manifest['digest'], 'Output hash mismatch')
            else:
                require(value.get('output_sha256') is None, 'Failure without output must use null')
            return self.save(kind, [rid], value)
        if kind == 'usage':
            text(value.get('provider'), 'provider'); text(value.get('request_id'), 'request_id')
            require(value.get('phase') in ('f0', 'repair', 'overhead'), 'Invalid usage phase')
            require((run is None) == (value['phase'] == 'overhead'), 'Overhead has no run; production requires run')
            require(value.get('category') in ('main', 'sidecar', 'compute', 'evaluation', 'setup', 'report'), 'Usage category required')
            require(value.get('basis') in ('reported', 'estimated', 'unknown'), 'Billing basis required')
            money = value.get('money')
            if money is not None:
                number(money, 'money'); text(value.get('currency'), 'currency')
                require(value['basis'] != 'unknown', 'Unknown billing cannot have money')
                text(value.get('pricing_provenance'), 'pricing_provenance')
            else:
                require(value['basis'] == 'unknown', 'Missing money must be unknown')
            raw = value.get('units', {})
            require(isinstance(raw, dict), 'units object required')
            for k, v in raw.items():
                if v is not None: number(v, k)
            return self.save(kind, [value['provider'], value['request_id']], value)
        if kind == 'evaluation':
            require(run, 'run_id required')
            revision = value.get('revision')
            require(revision in ('F0', 'F1'), 'Evaluation revision required')
            _, manifest = self.output(rid, revision)
            require(value.get('output_sha256') == manifest['digest'], 'Evaluation output hash mismatch')
            ev = self.task(run)['evaluator']
            require(value.get('evaluator_sha256') == digest(ev), 'Evaluator identity mismatch')
            require(value.get('provenance') in ('independent_command', 'independent_external'), 'Independent provenance required')
            require(value.get('protected') is False, 'Protected evaluation unavailable')
            checks = value.get('checks')
            require(isinstance(checks, list), 'checks list required')
            require(sorted(c.get('requirement_id', '') for c in checks) == sorted(self.task(run)['requirements']), 'Exactly one check per requirement required')
            for c in checks:
                require(c.get('verdict') in ('pass', 'fail', 'error', 'unavailable'), 'Invalid check verdict')
                require(c.get('severity') in ('none', 'minor', 'major', 'critical'), 'Check severity required')
                text(c.get('evidence'), 'check evidence')
            return self.save(kind, [rid, revision], value)
        if kind == 'review':
            from .review import validate_review
            require(run and run['replicate'] in self.plan['review']['replicates'], 'Review outside planned subset')
            _, manifest = self.output(rid)
            require(value.get('output_sha256') == manifest['digest'], 'Review output hash mismatch')
            validate_review(value, self.plan['limits']['human_seconds_per_review'])
            return self.save(kind, [rid], value)
        raise ABError('Unsupported record kind')
