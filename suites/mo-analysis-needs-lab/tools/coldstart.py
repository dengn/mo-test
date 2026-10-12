"""Positive coverage control for cold-start fallback; never substitutes primary records."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data import ROOT,tables,connect,read,compare,plain,values
from native import Native
from analytics import analyze
from scenarios import sql_for,params

def main():
 out=ROOT/'results/coldstart';out.mkdir(exist_ok=False);data=tables();native=Native(data);c=connect();start=time.time();counts=dict(cases=0,passed=0,failed=0)
 with (out/'cases.jsonl').open('w') as f:
  for i in range(1000):
   p=params(5,8,i);base=sql_for(5,8,i);sql=f"WITH cold_source AS (SELECT * FROM daily WHERE day>{p['cut']} OR day>={p['cut']}-MOD(uid,4)) "+base.replace('FROM daily d ','FROM cold_source d ');r=dict(case_id=i,domain='hierarchical_forecast',template=8,parameters=p,sql=sql,status='pass')
   try:
    g=native.expected(5,8,i);g=g[(g.day>p['cut'])|(g.day>=p['cut']-g.uid%4)].reset_index(drop=True);a=read(c,sql);compare(g,a,1e-7);n=g[g.train_flag==1].groupby('uid').size().to_dict();assert all(1<=v<=4 and v<p['lb'] for v in n.values());e=analyze(5,8,i,g,True,data);actual=analyze(5,8,i,a,False,data);compare(e,actual,1e-6);r.update(training_rows_per_unit=n,columns=list(e),expected=values(e),actual=values(actual),fallback_branch_exercised=True)
   except Exception as ex:r.update(status='fail',error=str(ex))
   counts['cases']+=1;counts['passed']+=r['status']=='pass';counts['failed']+=r['status']!='pass';f.write(json.dumps(plain(r),separators=(',',':'))+'\n')
 c.close();counts.update(elapsed_seconds=time.time()-start,scope='1000 supplemental cold-start controls, historical source restricted to 1–4 observations per unit in MO; explicitly exercises fallback branch. Dense main template 8 has enough history and does not activate this branch; original main records preserved.')
 (out/'summary.json').write_text(json.dumps(counts,indent=2));print(counts,flush=True)
if __name__=='__main__':main()
