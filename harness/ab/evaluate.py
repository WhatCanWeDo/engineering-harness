"""Run a predeclared existing evaluator against a disposable frozen-output copy."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
from .core import digest, read, require, sha, put


def evaluate(exp, rid, revision='F0'):
    run = exp.run(rid); ev = exp.task(run)['evaluator']
    require(ev['kind'] == 'command', 'External evaluator: import its content-bound receipt with ingest')
    previous = [v for v in exp.records('evaluation', rid) if v['revision'] == revision]
    if previous: return {'status': 'already_recorded', 'record_sha256': digest(previous[0])}
    exp.verify_inputs()
    tree, manifest = exp.output(rid, revision)
    source = exp.path / 'evaluators' / run['task_key'] / 'evaluator'
    log = exp.path / 'evaluation-attempts' / rid / revision
    require(not log.exists(), 'Evaluator attempt already exists. Inspect errors; no hidden reruns in this experiment.')
    log.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='harness-evaluate-') as temp:
        temp = Path(temp); output = temp / 'output'; shutil.copytree(tree, output)
        evaluator = temp / 'evaluator'; shutil.copy2(source, evaluator)
        result_path = temp / 'result.json'
        argv = [s.replace('{evaluator}', str(evaluator)).replace('{output}', str(output)).replace('{result}', str(result_path)) for s in ev['argv']]
        env = dict(os.environ, HARNESS_OUTPUT=str(output), HARNESS_RESULT=str(result_path))
        with (log / 'stdout.log').open('wb') as stdout, (log / 'stderr.log').open('wb') as stderr:
            process = subprocess.Popen(argv, cwd=temp, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            timed_out = False
            try: code = process.wait(timeout=ev['timeout_seconds'])
            except subprocess.TimeoutExpired:
                timed_out = True; os.killpg(process.pid, signal.SIGKILL); code = process.wait()
        put(log / 'process.json', {'returncode': code, 'timeout': timed_out, 'argv': argv, 'trust': 'local_cooperative_not_sandboxed'})
        exp.verify_inputs(); exp.output(rid, revision)
        if code != 0 or not result_path.exists():
            checks = [{'requirement_id': r, 'verdict': 'error', 'severity': 'none', 'evidence': 'Evaluator timeout/nonzero/missing result; see evaluation-attempts logs'} for r in exp.task(run)['requirements']]
        else:
            data = read(result_path); checks = data['checks']
        value = {'run_id': rid, 'revision': revision, 'output_sha256': manifest['digest'], 'evaluator_sha256': digest(ev), 'provenance': 'independent_command', 'protected': False, 'checks': checks}
        return exp.ingest('evaluation', value)
