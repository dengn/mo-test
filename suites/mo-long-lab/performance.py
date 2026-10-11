"""Balanced isolated latency test of long SQL; post-compatibility only."""
import collections,concurrent.futures,json,threading,time
import numpy as np
from data import ROOT,local_oracle,tables,connect
from scenarios import sql_for
from run import equal,monitor

def main():
 oracle=local_oracle(tables());queries=[]
 for f in [0,15,30,38]:
  for i in [0,66,199]:
   sql=sql_for(f,i);queries.append((sql,oracle.execute(sql).fetchall()))
 oracle.close();c=connect()
 for sql,expected in queries:
  with c.cursor() as q:q.execute(sql);actual=q.fetchall()
  assert equal(expected,actual)
 c.close();out=ROOT/'results/performance';out.mkdir(parents=True,exist_ok=True);stop=threading.Event();h=threading.Thread(target=monitor,args=(stop,out),daemon=True);h.start();allrows=[];trials=[]
 try:
  for trial,concurrency in [(r,t) for r,order in enumerate([[1,4,2,8],[8,2,4,1],[2,1,8,4]]) for t in order]:
   gate=threading.Barrier(concurrency+1);lock=threading.Lock();rows=[]
   def worker(w):
    c=connect();local=[]
    with c.cursor() as q:q.execute(queries[w%len(queries)][0]);q.fetchall()
    gate.wait()
    for seq in range(w,48,concurrency):
     ix=seq%len(queries);sql,expected=queries[ix];t=time.perf_counter();error=None;actual=None
     try:
      with c.cursor() as q:q.execute(sql);actual=q.fetchall()
     except Exception as e:error=str(e)
     local.append({'trial':trial,'concurrency':concurrency,'sequence':seq,'query_index':ix,'ms':(time.perf_counter()-t)*1000,'error':error,'_expected':expected,'_actual':actual})
    c.close()
    with lock:rows.extend(local)
   with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
    fs=[pool.submit(worker,w) for w in range(concurrency)];gate.wait();started=time.perf_counter()
    for f in fs:f.result()
   seconds=time.perf_counter()-started;assert len(rows)==48
   for r in rows:r['status']='error' if r['error'] else 'pass' if equal(r['_expected'],r['_actual']) else 'mismatch';r.pop('_expected');r.pop('_actual')
   trials.append({'trial':trial,'concurrency':concurrency,'seconds':seconds,'qps':48/seconds});allrows.extend(rows);print(trials[-1],flush=True)
 finally:stop.set();h.join()
 groups=[]
 for c in [1,2,4,8]:
  rows=[r for r in allrows if r['concurrency']==c];seconds=sum(r['seconds'] for r in trials if r['concurrency']==c)
  groups.append({'concurrency':c,'queries':len(rows),'queries_per_second':len(rows)/seconds,'latency_ms':dict(zip(['p50','p95','p99','max'],map(float,np.quantile([r['ms'] for r in rows],[.5,.95,.99,1])))),'counts':dict(collections.Counter(r['status'] for r in rows))})
 (out/'queries.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in allrows));(ROOT/'performance.json').write_text(json.dumps({'groups':groups,'trials':trials,'measured_queries':576,'query_shapes':12,'scope':'warm local instance; long-query client-visible round trip; full query shape warmup and per-worker warmup excluded; three balanced-order trials; oracle and result assertions outside timed work'},indent=2))
if __name__=='__main__':main()
