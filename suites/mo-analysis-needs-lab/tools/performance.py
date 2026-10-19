"""Isolated read latency after all main/framework jobs finish; full value checks outside timer."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np,pandas as pd
from sqlalchemy import text
from data import ROOT,tables,connect,engine,read,compare,plain
from native import Native
from scenarios import DOMAINS,sql_for

def reconstruct(data):
 changes=data['changes'].sort_values('seq').drop_duplicates('event_id',keep='last');inc=changes[changes.op==1]['event_id uid day v'.split()].sort_values('event_id').reset_index(drop=True);accepted={};maximum=-100000
 for cp in range(10):
  events=data['deliveries'][data['deliveries'].batch==cp].sort_values('delivery_id')
  for policy,late in enumerate([0,5,10,20,30]):
   for r in events.itertuples():
    key=(policy,r.event_id)
    if r.event_min>=maximum-late and key not in accepted:accepted[key]=(policy,r.event_id,r.uid,r.event_min,r.batch,float(r.v),r.kind)
  maximum=max(maximum,int(events.event_min.max()))
 return inc,pd.DataFrame(list(accepted.values()),columns='policy event_id uid event_min batch v kind'.split())
def main():
 out=ROOT/'results'/'performance';out.mkdir(exist_ok=False);data=tables();native=Native(data);native.set_state(9,*reconstruct(data));c=connect();e=engine();fixtures=[]
 for d in range(10):
  for j,i in [(0,9),(2,29),(5,99),(7,129),(9,999)]:fixtures.append((d,j,i,sql_for(d,j,i),native.expected(d,j,i)))
 # Gold construction and warm-up precede timed measurements.
 for d,j,i,s,g in fixtures:compare(g,read(c,s),1e-7)
 rng=np.random.default_rng(20261012);records=[]
 for repetition in range(4):
  for k in rng.permutation(len(fixtures)):
   d,j,i,s,g=fixtures[k];client='pandas_sqlalchemy' if repetition%2 else 'numpy_pymysql';start=time.perf_counter()
   if repetition%2:
    with e.connect() as con:a=pd.read_sql_query(text(s),con)
   else:a=read(c,s)
   elapsed=time.perf_counter()-start;compare(g,a,1e-7);records.append(dict(domain=DOMAINS[d],template=j,parameter=i,repetition=repetition,client=client,seconds=elapsed,rows=len(a),status='pass'))
 c.close();e.dispose();summary={}
 for d in DOMAINS:
  rows=[r for r in records if r['domain']==d];v=[r['seconds'] for r in rows];summary[d]=dict(queries=len(v),median_ms=float(np.median(v)*1000),p95_ms=float(np.quantile(v,.95)*1000),min_ms=float(min(v)*1000),max_ms=float(max(v)*1000))
 result=dict(queries=len(records),passed=len(records),scope='200 serial, warmed client read measurements after main and framework jobs stop; client fetch/DataFrame materialization included; full equality checks outside timer; 50 representative queries, not production-scale throughput',by_domain=summary)
 (out/'cases.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records));(out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':main()
