#!/usr/bin/env python3
"""Synthetic local walkthrough of the CLI, no models and no human measurements.

This is a runnable usage example, not an independently authored correctness suite.
All simulated receipts remain under the chosen new directory; no knowledge writes.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    a = parser.parse_args(); root = a.output.resolve(); root.mkdir(parents=True, exist_ok=False)
    log = []
    def call(*args):
        command = [sys.executable, '-m', 'harness', 'ab', *map(str, args)]
        p = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        value = json.loads(p.stdout); log.append({'argv': command, 'result': value})
        write(root / 'walkthrough.json', {'synthetic': True, 'steps': log})
        return value
    for name in ['baseline', 'candidate', 'task']:
        (root / name).mkdir()
    (root / 'baseline/SKILL.md').write_text('Synthetic baseline configuration\n')
    (root / 'candidate/SKILL.md').write_text('Synthetic candidate configuration\n')
    (root / 'task/input.txt').write_text('Synthetic starting artifact\n')
    # Fixed result fixture exercises evaluator transport, not product correctness.
    evaluator = root / 'fixture_evaluator.py'
    evaluator.write_text('import json,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps({"checks":[{"requirement_id":"example","verdict":"pass","severity":"none","evidence":"Synthetic transport fixture; no correctness claim"}]}))\n')
    common = {'files':['SKILL.md'], 'agent':'synthetic-no-agent', 'agent_version':'none', 'model':'none', 'reasoning':'none', 'environment':{'python':sys.version.split()[0]}, 'permissions':['local-fixture-only'], 'tools':[], 'instructions':'synthetic', 'cache_policy':'none', 'model_control':'not_applicable'}
    spec = {'version':1,'synthetic':True,'hypothesis':'СИНТЕТИЧЕСКИЙ ПРИМЕР — проверка механики, не эффект skill','dataset':'development','dataset_provenance':'Fabricated local CLI walkthrough; no model or human runs','baseline':dict(common,root=str(root/'baseline')),'candidate':dict(common,root=str(root/'candidate')),'allowed_changes':['/files/SKILL.md/sha256'],'replicates':2,'seed':17,'retry_policy':'none','analysis':{'primary':'human_seconds','min_improvement':10,'max_correctness_regressions':0},'review':{'protocol':'personal_crossover','replicates':[1,2]},'limits':{'wall_seconds_per_run':300,'calls_per_run':5,'human_seconds_per_review':600,'max_runs':4},'tasks':[{'id':'example:task','goal':'Read the synthetic artifact','clarification_policy':'No clarifications in this fixture','requirements':['example'],'root':str(root/'task'),'files':['input.txt'],'evaluator':{'kind':'command','identity':'synthetic-fixture-v1','independent':True,'path':str(evaluator),'argv':[sys.executable,'{evaluator}','{result}'],'timeout_seconds':10}}]}
    spec_path=write(root/'plan-input.json',spec); exp=root/'experiment'
    call('plan','--input',spec_path,'--output',exp)
    call('prepare','--experiment',exp)
    call('report','--experiment',exp,'--output',root/'before-report')
    schedule=json.loads((exp/'plan.json').read_text())['schedule']
    for index, run in enumerate(schedule):
        assignment=call('dispatch','--experiment',exp)
        rid=assignment['run_id']; tree=exp/'runs'/rid/'workspace'
        (tree/'result.txt').write_text('Synthetic output '+str(index))
        files=write(root/'files.json',['result.txt'])
        frozen=call('freeze','--experiment',exp,'--run',rid,'--source',tree,'--files',files)
        receipt=call('receipt','--experiment',exp,'--run',rid)
        receipt.update(duration_seconds=20,session_id='synthetic-'+rid,isolation='unavailable',isolation_evidence='No real native agent used',skill_loading_evidence='Synthetic fixture only',accounting_complete=True,request_keys=[['synthetic',rid]])
        path=write(root/'execution.json',receipt)
        call('ingest','--experiment',exp,'--kind','execution','--input',path)
        usage={'run_id':rid,'provider':'synthetic','request_id':rid,'phase':'f0','category':'main','basis':'estimated','money':0.2 if run['arm']=='A' else 0.3,'currency':'USD','pricing_provenance':'Fabricated fixture, not provider pricing','units':{'input_tokens':100}}
        call('ingest','--experiment',exp,'--kind','usage','--input',write(root/'usage.json',usage))
        call('evaluate','--experiment',exp,'--run',rid)
        call('review','--experiment',exp,'--run',rid,'--output',root/f'review-{index}.html')
        seconds=120 if run['arm']=='A' else 90
        review={'run_id':rid,'output_sha256':frozen['output_sha256'],'reviewer':'synthetic-fixture','prior_exposure':index%2==1,'unblinded':False,'review_order':run['order_in_pair'],'verdict':'accept','stop_reason':'completed','issues':[],'events':[{'action':'start','at_ms':0,'mode':'review'},{'action':'pause','at_ms':seconds*500,'mode':'review'},{'action':'resume','at_ms':seconds*500+10000,'mode':'review'},{'action':'stop','at_ms':seconds*1000+10000,'mode':'review'}]}
        call('ingest','--experiment',exp,'--kind','review','--input',write(root/'review.json',review))
    report=call('report','--experiment',exp,'--output',root/'report')
    call('report','--experiment',exp,'--output',root/'report-replay')
    print(json.dumps({'synthetic':True,'steps':len(log),'report':report,'walkthrough':str(root/'walkthrough.json'),'replay_identical':(root/'report/comparison.json').read_bytes()==(root/'report-replay/comparison.json').read_bytes()}))

if __name__=='__main__':main()
