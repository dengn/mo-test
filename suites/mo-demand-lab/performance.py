"""Independent end-to-end business analysis latency, after compatibility clients."""
import collections,concurrent.futures,json,threading,time
import numpy as np,pandas as pd
from data import ROOT,tables,local_oracle,connect
from catalog import MISSIONS,queries
from analysis import calculate
from run import equal,plain,monitor

def main():
 shapes=[(f,i) for f in [0,8,28,29,39] for i in [0,123]];oracle=local_oracle(tables());reference=[]
 for f,i in shapes:reference.append(plain(calculate(MISSIONS[f]['key'],[oracle.execute(q).fetchdf() for q in queries(f,i)],i)))
 oracle.close();out=ROOT/'results/performance';out.mkdir(parents=True,exist_ok=True);stop=threading.Event();health=threading.Thread(target=monitor,args=(stop,out),daemon=True);health.start();records=[];trials=[]
 def workflow(c,f,i):
  frames=[];sql_ms=0.
  for sql in queries(f,i):
   t=time.perf_counter()
   with c.cursor() as q:q.execute(sql);rows=q.fetchall();columns=[d[0] for d in q.description]
   sql_ms+=(time.perf_counter()-t)*1000;frames.append(pd.DataFrame(rows,columns=columns))
  return plain(calculate(MISSIONS[f]['key'],frames,i)),sql_ms
 try:
  for trial,concurrency in [(r,t) for r,order in enumerate([[1,4,2,8],[8,2,4,1],[2,1,8,4]]) for t in order]:
   timer={};gate=threading.Barrier(concurrency+1,action=lambda:timer.update(start=time.perf_counter()));lock=threading.Lock();rows=[]
   def worker(w):
    c=connect();workflow(c,*shapes[w%len(shapes)]);gate.wait();local=[]
    for sequence in range(w,40,concurrency):
     shape=sequence%len(shapes);f,i=shapes[shape];started=time.perf_counter();error=None;model=None;sql_ms=None
     try:model,sql_ms=workflow(c,f,i)
     except Exception as e:error=str(e)
     local.append({'trial':trial,'concurrency':concurrency,'sequence':sequence,'requirement':MISSIONS[f]['key'],'parameter':i,'shape':shape,'ms':(time.perf_counter()-started)*1000,'sql_ms':sql_ms,'error':error,'_model':model})
    c.close()
    with lock:rows.extend(local)
   with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
    fs=[pool.submit(worker,w) for w in range(concurrency)];gate.wait()
    for future in fs:future.result()
   seconds=time.perf_counter()-timer['start'];assert len(rows)==40
   for r in rows:r['status']='error' if r['error'] else 'pass' if equal(r.pop('_model'),reference[r['shape']]) else 'mismatch';r.pop('_model',None)
   records.extend(rows);trials.append({'trial':trial,'concurrency':concurrency,'seconds':seconds,'workflows_per_second':40/seconds});print(trials[-1],flush=True)
 finally:stop.set();health.join()
 groups=[]
 for concurrency in [1,2,4,8]:
  rows=[r for r in records if r['concurrency']==concurrency];seconds=sum(t['seconds'] for t in trials if t['concurrency']==concurrency)
  groups.append({'concurrency':concurrency,'workflows':len(rows),'workflows_per_second':len(rows)/seconds,'latency_ms':dict(zip(['p50','p95','p99','max'],map(float,np.quantile([r['ms'] for r in rows],[.5,.95,.99,1])))),'counts':dict(collections.Counter(r['status'] for r in rows))})
 (out/'workflows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records));(ROOT/'performance.json').write_text(json.dumps({'groups':groups,'trials':trials,'measured_workflows':480,'business_shapes':10,'scope':'Local warm end-to-end reads plus Pandas/NumPy/SciPy decisions. No publication writes in this timed benchmark. Independent reference models precomputed; assertions after timed work. Measures the full local analysis stack, not pure MO server QPS.'},indent=2))
if __name__=='__main__':main()
