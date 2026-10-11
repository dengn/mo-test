"""Independent full-pipeline measurements; oracle work runs outside timed batches."""
import concurrent.futures,json,time
import numpy as np,pandas as pd
from data import ROOT,connect,tables,native,query,read,compare,audit
from models import prepared,fit,serialize
from run import engine,table,publish
def worker(w,jobs,client,gold):
 c=connect();eng=engine();table(c,w);d=tables();results=[]
 for seq,m,i in jobs:
  t=time.perf_counter();sql=query(i);a=pd.read_sql_query(sql,eng).astype(float) if client=='pandas' else read(c,sql);p=prepared(a,i,d['edges']);net,out,metrics=fit(p,m,i);blob=serialize(net);pub=publish(c,w,seq,blob,net,p,out,m,i);elapsed=time.perf_counter()-t
  # Full facts and reference training are verified only after each timed workflow.
  ref,expected,expected_metrics=gold[(m,i)];compare(ref,a);np.testing.assert_array_equal(out,expected);assert metrics==expected_metrics
  results.append(dict(client=client,worker=w,mission=m,i=i,seconds=elapsed,model_bytes=len(blob),status='pass'))
 c.close();eng.dispose();return results
def main():
 d=tables();audit(d,'benchmark-before');configs=[(m,i) for m,i in [(0,55),(2,333),(4,199),(6,888),(8,111),(10,777),(12,443),(14,999),(16,0),(19,555)]];gold={}
 for m,i in configs:
  ref=native(d,i);net,out,metrics=fit(prepared(ref,i,d['edges']),m,i);gold[(m,i)]=(ref,out,metrics)
 records=[];batches=[];start=time.time()
 # 2 clients x 4 concurrency levels x 30 workflows = 240 measurements.
 for client in ['numpy','pandas']:
  for n in [1,2,4,8]:
   jobs=[(rep*10+j,m,i) for rep in range(3) for j,(m,i) in enumerate(configs)];t=time.perf_counter()
   with concurrent.futures.ProcessPoolExecutor(max_workers=n) as pool:
    fs=[pool.submit(worker,w,jobs[w::n],client,gold) for w in range(n)];rows=[r for f in fs for r in f.result()]
   wall=time.perf_counter()-t;lat=np.array([r['seconds'] for r in rows]);batch=dict(client=client,concurrency=n,workflows=len(rows),elapsed_seconds=wall,throughput=len(rows)/wall,median_ms=float(np.median(lat)*1000),p95_ms=float(np.quantile(lat,.95)*1000));batches.append(batch);records.extend(rows);print(json.dumps(batch),flush=True)
 (ROOT/'performance-cases.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in records));(ROOT/'performance-summary.json').write_text(json.dumps(dict(measurements=len(records),passed=len(records),failed=0,seconds=time.time()-start,batches=batches,scope='SQL read + train-only preprocessing + one deep fit + binary model/prediction transaction + reload/visibility checks; precomputed reference comparisons outside latency, but batch throughput includes comparisons, scheduling and connection lifecycle. These are workflows/s, not pure MO QPS or large-model training throughput.'),indent=2));audit(d,'benchmark-after')
if __name__=='__main__':main()
