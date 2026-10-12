"""Real-MO leakage invariance: change future-only knowledge without changing past results."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data import ROOT,connect,read,compare,values,plain
from scenarios import params,sql_for

def main():
 out=ROOT/'results/counterfactual';out.mkdir(exist_ok=False);c=connect();records=[];started=time.time();copies={'observations':'cf_observations','attrs':'cf_attrs','labels':'cf_labels'}
 try:
  for i in [0,17,60,125,999]:
   cut=params(0,0,i)['cut'];mutations={}
   with c.cursor() as q:
    for original,copy in copies.items():q.execute(f'DROP TABLE IF EXISTS {copy}');q.execute(f'CREATE TABLE {copy} AS SELECT * FROM {original}')
    q.execute(f'UPDATE cf_observations SET v=1000000000000,revision=revision+100,valid=0 WHERE received_day>{cut}');mutations['observations']=q.rowcount
    q.execute(f'UPDATE cf_attrs SET scale=1000000000000,revision=revision+100 WHERE recorded_day>{cut}');mutations['attrs']=q.rowcount
    q.execute(f'UPDATE cf_labels SET y=1000000000000 WHERE ready_day>{cut}');mutations['labels']=q.rowcount
   assert sum(mutations.values())>0  # Latest cutoff can have no future dimension versions.
   for j in range(10):
    sql=sql_for(0,j,i);altered=sql
    for original,copy in copies.items():altered=altered.replace('JOIN '+original+' ','JOIN '+copy+' ')
    g=read(c,sql);a=read(c,altered);r=dict(template=j,parameter=i,cut=cut,mutations=mutations,baseline_sql=sql,counterfactual_sql=altered,status='pass',columns=list(g),expected=values(g),actual=values(a))
    try:compare(g,a,1e-7)
    except Exception as e:r.update(status='fail',error=str(e))
    records.append(r)
 finally:
  with c.cursor() as q:
   for copy in copies.values():q.execute(f'DROP TABLE IF EXISTS {copy}')
  c.close()
 (out/'cases.jsonl').write_text(''.join(json.dumps(plain(r),separators=(',',':'))+'\n' for r in records));result=dict(cases=len(records),passed=sum(r['status']=='pass' for r in records),failed=sum(r['status']!='pass' for r in records),elapsed_seconds=time.time()-started,scope='50 supplemental full-result invariance controls, two MO queries each; future-only observations, dimensions and labels perturbed in private copies; original source tables unchanged')
 (out/'summary.json').write_text(json.dumps(result,indent=2));print(result,flush=True)
if __name__=='__main__':main()
