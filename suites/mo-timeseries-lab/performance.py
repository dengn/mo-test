"""Isolated query+fetch observations; gold comparison occurs after each batch."""
import concurrent.futures,json,time
import numpy as np,pandas as pd
from sqlalchemy import text
from data import ROOT,tables,oracle,connect,engine,read,compare
from scenarios import sql_for

def main():
 pairs=[(f,i) for f in [0,4,18,35,46] for i in [28,125]];ref=oracle(tables());gold={p:ref.execute(sql_for(*p)).fetchdf() for p in pairs};ref.close();groups=[];records=[]
 for client in ['pymysql_numpy','pandas_sqlalchemy']:
  for trial,order in enumerate([[1,4,2,8],[8,2,4,1],[2,8,1,4]]):
   for concurrency in order:
    def job(pair):
     f,i=pair;eng=engine() if client.startswith('pandas') else None;c=connect() if not eng else None
     try:
      if eng:
       with eng.connect() as connection:
        t=time.perf_counter();a=pd.read_sql(text(sql_for(f,i)),connection,coerce_float=False);elapsed=(time.perf_counter()-t)*1000
      else:t=time.perf_counter();a=read(c,sql_for(f,i));elapsed=(time.perf_counter()-t)*1000
      return dict(family=f,parameter=i,client=client,trial=trial,concurrency=concurrency,ms=elapsed),a
     finally:
      if c:c.close()
      if eng:eng.dispose()
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:results=list(pool.map(job,pairs))
    seconds=time.perf_counter()-start
    for r,a in results:compare(gold[(r['family'],r['parameter'])],a);r['status']='pass';records.append(r)
    groups.append(dict(client=client,trial=trial,concurrency=concurrency,queries=len(pairs),seconds=seconds));print(client,concurrency,trial,round(seconds,3),'pass',flush=True)
 summary=[]
 for client in ['pymysql_numpy','pandas_sqlalchemy']:
  for concurrency in [1,2,4,8]:
   rows=[r for r in records if r['client']==client and r['concurrency']==concurrency];elapsed=sum(g['seconds'] for g in groups if g['client']==client and g['concurrency']==concurrency);lat=[r['ms'] for r in rows];summary.append(dict(client=client,concurrency=concurrency,queries=len(rows),queries_per_second=len(rows)/elapsed,p50_ms=float(np.quantile(lat,.5)),p95_ms=float(np.quantile(lat,.95)),p99_ms=float(np.quantile(lat,.99))))
 (ROOT/'performance.json').write_text(json.dumps(dict(expected=240,passed=len(records),failed=0,summary=summary,groups=groups,records=records,scope='SQL generation/query/fetch inside latency; connection creation outside latency but inside batch wall throughput. Gold verification after the whole timed batch. Warm local synthetic data, mixed query shapes, no other test clients, not server-only QPS.'),indent=2));assert len(records)==240
if __name__=='__main__':main()
