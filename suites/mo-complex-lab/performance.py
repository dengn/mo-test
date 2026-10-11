"""Isolated post-compatibility mixed complex query latency benchmark."""
import collections,concurrent.futures,json,threading,time
import numpy as np
from data import ROOT,tables,connect,local_oracle
from scenarios import SQL,sql_for
from run import compare,health

def main():
 names=['net_revenue_reconciliation','daily_rolling_sales','recursive_bounded_reachability'];lookup={name:f for f,(name,_,_) in enumerate(SQL)};families=[lookup[n] for n in names]+[80]
 oracle=local_oracle(tables());queries=[]
 for i in [0,123,249,499,625,749,888,999]:
  for f in families:
   sql=sql_for(f,i);queries.append((sql,oracle.execute(sql).fetchall()))
 oracle.close()
 # Warm every query/parameter shape before the balanced repeated benchmark.
 warm=connect()
 for _ in range(2):
  for sql,expected in queries:
   with warm.cursor() as q:q.execute(sql);q.fetchall()
 warm.close()
 out=ROOT/'results/performance';out.mkdir(parents=True,exist_ok=True);stop=threading.Event();h=threading.Thread(target=health,args=(stop,out),daemon=True);h.start();allrecords=[];trials=[]
 try:
  for trial,threads in [(trial,t) for trial,order in enumerate([[1,4,2,8],[8,2,4,1],[2,1,8,4]]) for t in order]:
   gate=threading.Barrier(threads+1);records=[];errors=[];lock=threading.Lock()
   def worker(w):
    c=connect();local=[]
    for j in range(2):
     with c.cursor() as q:q.execute(queries[(w+j)%len(queries)][0]);q.fetchall()
    gate.wait()
    for seq in range(w,1024,threads):
     ix=seq%len(queries);sql,expected=queries[ix];t=time.perf_counter();error=None;actual=None
     try:
      with c.cursor() as q:q.execute(sql);actual=q.fetchall()
     except Exception as e:error=str(e)
     ms=(time.perf_counter()-t)*1000
     local.append({'trial':trial,'concurrency':threads,'sequence':seq,'query_index':ix,'query_ms':ms,'error':error,'_actual':actual,'_expected':expected})
    c.close()
    with lock:records.extend(local)
   with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
    futures=[pool.submit(worker,w) for w in range(threads)];gate.wait();start=time.perf_counter()
    for f in futures:f.result()
   sec=time.perf_counter()-start;assert len(records)==1024;ms=[r['query_ms'] for r in records]
   # Result comparison is after the timed workload to keep oracle/verification
   # CPU work out of the client-visible query concurrency measurement.
   for r in records:
    r['status']='error' if r['error'] else 'pass' if compare(r.pop('_expected'),r.pop('_actual')) else 'mismatch'
    r.pop('_expected',None);r.pop('_actual',None)
   g={'trial':trial,'concurrency':threads,'queries':1024,'warmups_excluded':2*threads,'seconds':sec,'queries_per_second':1024/sec,'latency_ms':dict(zip(['p50','p95','p99','max'],map(float,np.quantile(ms,[.5,.95,.99,1])))),'counts':dict(collections.Counter(r['status'] for r in records))};trials.append(g);allrecords.extend(records);print(g,flush=True)
 finally:stop.set();h.join()
 groups=[]
 for threads in [1,2,4,8]:
  trial=[r for r in trials if r['concurrency']==threads];r=[r for r in allrecords if r['concurrency']==threads];sec=sum(t['seconds'] for t in trial)
  groups.append({'concurrency':threads,'queries':len(r),'seconds':sec,'queries_per_second':len(r)/sec,'latency_ms':dict(zip(['p50','p95','p99','max'],map(float,np.quantile([x['query_ms'] for x in r],[.5,.95,.99,1])))),'counts':dict(collections.Counter(x['status'] for x in r)),'trial_qps':[t['queries_per_second'] for t in trial]})
 (out/'queries.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in allrecords))
 (ROOT/'performance.json').write_text(json.dumps({'groups':groups,'trials':trials,'queries_total':12288,'query_mix':names+['multi_fact_customer_features'],'source_rows':113830,'warm_query_shapes':64,'scope':'client-visible latency; post compatibility and connectors; three balanced-order trials per concurrency with 1024 queries each; every query shape prewarmed; oracle precomputed and verification outside timing; warm standalone single instance; no external database baseline'},indent=2))
if __name__=='__main__':main()
