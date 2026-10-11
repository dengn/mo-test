import argparse,collections,concurrent.futures,decimal,json,os,threading,time,traceback
from pathlib import Path
import numpy as np,pandas as pd,psutil
from sqlalchemy import text
from data import ROOT,tables,setup,connect,engine,local_oracle,params
from scenarios import SQL,SCIENCE,sql_for,label
from science import compute

def plain(v):
 if isinstance(v,np.ndarray):return [plain(x) for x in v]
 if isinstance(v,(tuple,list)):return [plain(x) for x in v]
 if isinstance(v,dict):return {str(k):plain(x) for k,x in v.items()}
 if isinstance(v,(decimal.Decimal,np.generic)):v=float(v) if isinstance(v,decimal.Decimal) else v.item()
 if isinstance(v,float) and not np.isfinite(v):return None if np.isnan(v) else str(v)
 return v

def compare(a,b):
 a,b=plain(a),plain(b)
 if isinstance(a,list):return isinstance(b,list) and len(a)==len(b) and all(compare(x,y) for x,y in zip(a,b))
 if a is None or b is None:return a is None and b is None
 if isinstance(a,(float,int)) and isinstance(b,(float,int)):
  if isinstance(a,int) and isinstance(b,int):return a==b
  return bool(np.isclose(a,b,rtol=1e-7,atol=1e-7))
 return a==b

def health(stop,out):
 pid=int(Path('/workspace/mo-ds-lab/server.pid').read_text().strip());proc=psutil.Process(pid);proc.cpu_percent();c=None
 with (out/'health.jsonl').open('w') as f:
  while not stop.is_set():
   row={'time':time.time(),'pid':pid}
   try:
    if c is None:c=connect()
    c.ping(reconnect=False);row.update(rss_mib=proc.memory_info().rss/2**20,cpu_percent=proc.cpu_percent(),threads=proc.num_threads(),status='ok')
   except Exception as e:row.update(status='error',error=str(e));c=None
   f.write(json.dumps(row)+'\n');f.flush();stop.wait(5)
 if c:c.close()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pilot',type=int,default=0);ap.add_argument('--workers',type=int,default=8);ap.add_argument('--setup',action='store_true');args=ap.parse_args()
 data=tables()
 if args.setup: print('loaded',setup(data),flush=True)
 # Deterministic round-robin scenario coverage followed by seeded permutation.
 indices=[f*1000+i for i in (range(1000) if not args.pilot else np.linspace(0,999,args.pilot,dtype=int)) for f in range(100)]
 np.random.default_rng(20261011).shuffle(indices)
 out=ROOT/'results'/('pilot' if args.pilot else 'canonical');out.mkdir(parents=True,exist_ok=True)
 # Preflight every SQL oracle. Fail harness setup before executing any canonical cases.
 oracle=local_oracle(data)
 for f in range(100):
  try:oracle.execute(sql_for(f,0)).fetchall()
  except Exception as e:raise RuntimeError(f'Oracle SQL {label(f)[0]}: {e}') from e
 oracle.close()
 counts=collections.Counter();lock=threading.Lock();stop=threading.Event();h=threading.Thread(target=health,args=(stop,out),daemon=True);h.start()
 begin=time.time();logsize=Path('/workspace/mo-ds-lab/server.log').stat().st_size
 def worker(w,ids):
  oracle=local_oracle(data);c=connect();eng=engine();local=[]
  with (out/f'cases-{w}.jsonl').open('w') as file:
   for case in ids:
    family,i=divmod(int(case),1000);name,category=label(family);sql=sql_for(family,i)
    r={'case_id':int(case),'family':name,'category':category,'parameter':i,'client':'pandas' if case%2 else 'numpy','params':params(i)};t=time.perf_counter()
    try:
     expected=oracle.execute(sql).fetchall();r['oracle_ms']=(time.perf_counter()-t)*1000;tq=time.perf_counter()
     try:
      if case%2:
       with eng.connect() as con:df=pd.read_sql(text(sql),con,coerce_float=False)
       actual=list(df.itertuples(index=False,name=None))
      else:
       with c.cursor() as q:q.execute(sql);actual=q.fetchall()
      r['query_ms']=(time.perf_counter()-tq)*1000
     except Exception as e:
      r.update(status='sql_error',error=str(e)[:2500],query_ms=(time.perf_counter()-tq)*1000)
      try:c.ping(reconnect=True)
      except Exception:pass
      actual=None
     if actual is not None:
      r['source_rows']=len(actual); tc=time.perf_counter()
      r['feature_equal']=compare(expected,actual)
      if family>=80:
       expected=compute(name,expected,i);actual=compute(name,actual,i)
      r['compute_ms']=(time.perf_counter()-tc)*1000
      r['status']='pass' if r['feature_equal'] and compare(expected,actual) else 'mismatch'
      r['expected']=plain(expected);r['actual']=plain(actual)
     if r['status']!='pass':r['sql']=sql
    except Exception as e:r.update(status='harness_error',error=str(e),traceback=traceback.format_exc())
    r['total_ms']=(time.perf_counter()-t)*1000
    file.write(json.dumps(r,allow_nan=False)+'\n')
    with lock:
     counts[r['status']]+=1;n=sum(counts.values())
     if n%1000==0:print(json.dumps({'completed':n,'target':len(indices),'seconds':round(time.time()-begin,2),'counts':dict(counts)}),flush=True);file.flush()
  c.close();eng.dispose();oracle.close()
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
   list(pool.map(lambda x:worker(*x),[(w,indices[w::args.workers]) for w in range(args.workers)]))
 finally:stop.set();h.join()
 meta={'count':len(indices),'unique_cases':len(set(indices)),'counts':dict(counts),'seconds':time.time()-begin,'workers':args.workers,'sql_families':80,'science_families':20,'log_start_offset':logsize,'log_end_offset':Path('/workspace/mo-ds-lab/server.log').stat().st_size,'scope':'80 complex SQL families + 20 MO-derived client numerical/ML pipelines; each 1000 unique parameter tuples; DuckDB independent SQL oracle; scientific compute on client','tolerance':{'rtol':1e-7,'atol':1e-7},'seed':2026101102}
 (out/'meta.json').write_text(json.dumps(meta,indent=2));print(meta,flush=True)
 if sum(counts.values())!=len(indices):raise RuntimeError('incomplete run')
if __name__=='__main__':main()
