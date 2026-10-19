"""Replay one logical case with the documented NULL-safe evaluator and original source truth."""
import sys,json,hashlib
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'repaired'))
import run
from data import tables,compare,audit,plain
from scenarios import DOMAINS,params
from stages import Stages
ident=int(sys.argv[1]);assert 0<=ident<100000;d=ident//10000;j=ident%10000//1000;i=ident%1000;out=ROOT/'results'/f'replay-{ident}';out.mkdir(exist_ok=False);stored=None
for path in [ROOT/f'results/main-001/{DOMAINS[d]}.jsonl',ROOT/'results/retest/cases.jsonl']:
 if path.exists():
  for line in path.open():
   r=json.loads(line)
   if r['case_id']==ident:stored=r;break
assert stored is not None;run.DATA=tables();audit(run.DATA,f'replay-{ident}-before');stage=None
try:
 if d in [1,2]:
  stage=Stages(run.DATA,out)
  for cp in range(params(d,j,i)['checkpoint']+1):run.STATES[cp]=stage.advance(cp)
 r=run.execute((d,j,i));assert r['status']=='pass',r.get('error')
 if stored['status']=='pass':compare(pd.DataFrame(stored['output']['expected'],columns=stored['output']['columns']),pd.DataFrame(r['output']['actual'],columns=r['output']['columns']),1e-6)
 r['historical_outcome_compared']=stored['status']=='pass';r['code_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'repaired').glob('*.py')};(out/'case.json').write_text(json.dumps(plain(r),ensure_ascii=False,indent=2));print(dict(case_id=ident,status=r['status'],historical_outcome_compared=r['historical_outcome_compared'],output_rows=len(r['output']['actual'])))
finally:
 if stage:stage.close()
 for n,o,c,e in run.WORKERS:o.close();c.close();e.dispose()
