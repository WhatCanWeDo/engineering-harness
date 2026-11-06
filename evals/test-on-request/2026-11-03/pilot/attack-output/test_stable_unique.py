import argparse, importlib.util, json, pathlib, sys
parser=argparse.ArgumentParser()
parser.add_argument('--case')
a=parser.parse_args()
root=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('candidate',root/'candidate-copy/product/sequence.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
cases=json.loads((root/'cases.json').read_text())
if a.case:
    cases=[c for c in cases if c['id']==a.case]
    if not cases: parser.error('unknown case')
failed=False
for case in cases:
    original=case['items'][:]
    items=original[:]
    expected=[s for i,s in enumerate(original) if all(s != earlier for earlier in original[:i])]
    actual=module.unique_in_order(items)
    checks={'R1': isinstance(actual,list) and all(isinstance(s,str) for s in actual) and len(actual)==len(set(original)) and set(actual)==set(original), 'R2': actual==expected, 'R3': set(actual)==set(original) and (bool(original) or actual==[]), 'R4': items==original}
    failed |= not all(checks.values())
    print(json.dumps({'case':case['id'],'input':original,'expected':expected,'actual':actual,'checks':checks},ensure_ascii=False))
sys.exit(1 if failed else 0)
