import sys,json,importlib.util,argparse
from pathlib import Path
P=Path('/workspace');ap=argparse.ArgumentParser();ap.add_argument('case_id');a=ap.parse_args();ident=a.case_id
packs={'C':'mo-cases-50000','H':'mo-chaos-50000','X':'mo-crossdb-100000','E':'mo-etl-100000','G':'mo-gap-200000'};name=packs[ident[0]];directory=P/name
case=next(c for c in map(json.loads,(directory/'cases.jsonl').open()) if c['id']==ident)
sys.path.insert(0,str(P/'mo-cases-50000'));import runner as base
if ident[0] in 'CX':fn=base.runone
else:
 spec=importlib.util.spec_from_file_location('case_runner',directory/'runner.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);fn=mod.normal if ident[0]=='H' else mod.runone
print(json.dumps({'case':case,'result':fn(case)},ensure_ascii=False,default=str,indent=2))
