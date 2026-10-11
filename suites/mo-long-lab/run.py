import argparse,collections,concurrent.futures,decimal,json,os,threading,time,traceback
from pathlib import Path
import numpy as np,pandas as pd,psutil
from sqlalchemy import text
from data import ROOT,tables,setup,connect,engine,local_oracle
from scenarios import sql_for,label,parameters,complexity

def plain(x):
 if isinstance(x,(list,tuple,np.ndarray)):return [plain(v) for v in x]
 if isinstance(x,dict):return {str(k):plain(v) for k,v in x.items()}
 if isinstance(x,np.generic):x=x.item()
 if isinstance(x,decimal.Decimal):return float(x)
 if isinstance(x,float) and not np.isfinite(x):return None if np.isnan(x) else str(x)
 return x

def equal(a,b):
 if len(a)!=len(b):return False
 for ra,rb in zip(a,b):
  if len(ra)!=len(rb):return False
  for x,y in zip(ra,rb):
   if pd.isna(x) or pd.isna(y):
    if not (pd.isna(x) and pd.isna(y)):return False
   elif isinstance(x,(int,np.integer)) and isinstance(y,(int,np.integer)):
    if x!=y:return False
   else:
    fx,fy=float(x),float(y)
    if not abs(fx-fy)<=1e-7+1e-7*abs(fx):return False
 return True

def monitor(stop,out):
 pid=int(Path('/workspace/mo-ds-lab/server.pid').read_text());proc=psutil.Process(pid);proc.cpu_percent();c=None
 with (out/'health.jsonl').open('w') as file:
  while not stop.is_set():
   r={'time':time.time(),'pid':pid}
   try:
    if c is None:c=connect()
    c.ping(reconnect=False);r.update(status='ok',rss_mib=proc.memory_info().rss/2**20,cpu_percent=proc.cpu_percent())
   except Exception as e:r.update(status='error',error=str(e));c=None
   file.write(json.dumps(r)+'\n');file.flush();stop.wait(5)
 if c:c.close()

def stage_schema():return 'case_id INT,cid INT,tier INT,region INT,score DOUBLE,feature_sum DOUBLE,weighted DOUBLE'

def stage_rows_sql(table,case):return f'SELECT cid,tier,region,score,feature_sum,weighted FROM {table} WHERE case_id={case} ORDER BY cid'

def stage_transform(table,case):
 return f'''SELECT cid,tier,region,score-AVG(score) OVER(PARTITION BY tier)+CAST(0.5 AS DOUBLE) score,
 feature_sum+COALESCE(LAG(feature_sum) OVER(PARTITION BY tier ORDER BY cid),0) feature_sum,
 SUM(weighted) OVER(PARTITION BY tier ORDER BY cid ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) weighted
 FROM {table} WHERE case_id={case}'''

def multi_stage(c,oracle,case,f,actual,expected,w):
 # Private worker tables; original inputs are never written.
 a=f'stage_input_{w}';b=f'stage_output_{w}';steps=[]
 def execute(sql,parameters=None):
  t=time.perf_counter()
  with c.cursor() as q:q.execute(sql,parameters);rows=q.fetchall()
  steps.append({'sql':sql,'ms':(time.perf_counter()-t)*1000});return rows
 def check(sql,expected,stage):
  actual=execute(sql);ok=equal(expected,actual)
  steps[-1].update(check=stage,status='pass' if ok else 'mismatch',rows=len(actual))
  if not ok:raise ValueError(json.dumps({'stage':stage,'expected':plain(expected),'actual':plain(actual)}))
 execute('BEGIN')
 rows=[(case,*r) for r in actual];expected_rows=[(case,*r) for r in expected]
 t=time.perf_counter()
 with c.cursor() as q:q.executemany(f'INSERT INTO {a} VALUES(%s,%s,%s,%s,%s,%s,%s)',rows)
 steps.append({'sql':f'INSERT INTO {a} VALUES (bound rows)','rows':len(rows),'ms':(time.perf_counter()-t)*1000})
 oracle.execute(f'DELETE FROM {a}');oracle.execute(f'DELETE FROM {b}')
 oracle.executemany(f'INSERT INTO {a} VALUES(?,?,?,?,?,?,?)',expected_rows)
 check(stage_rows_sql(a,case),expected,'input_roundtrip')
 transform=stage_transform(a,case)
 execute(f'INSERT INTO {b} SELECT {case},z.* FROM ({transform}) z')
 oracle.execute(f'INSERT INTO {b} SELECT {case},z.* FROM ({transform}) z')
 result=oracle.execute(stage_rows_sql(b,case)).fetchall();check(stage_rows_sql(b,case),result,'server_window_transformation')
 agg=f'SELECT tier,COUNT(*),SUM(score),SUM(feature_sum),SUM(weighted),VAR_POP(weighted) FROM {b} WHERE case_id={case} GROUP BY tier ORDER BY tier'
 check(agg,oracle.execute(agg).fetchall(),'post_materialization_aggregation')
 # Both persistent commit and all-row rollback are exercised in separate families.
 commit=f%2==0;execute('COMMIT' if commit else 'ROLLBACK')
 check(stage_rows_sql(a,case),expected if commit else [],'after_commit_or_rollback')
 check(stage_rows_sql(b,case),result if commit else [],'output_after_commit_or_rollback')
 execute('BEGIN');execute(f'UPDATE {a} SET score=score+5 WHERE case_id={case} AND MOD(cid,3)=0')
 if commit:
  modified=[(cid,tier,region,score+(5 if cid%3==0 else 0),features,weighted) for cid,tier,region,score,features,weighted in expected]
  check(stage_rows_sql(a,case),modified,'read_own_update')
 execute('ROLLBACK');check(stage_rows_sql(a,case),expected if commit else [],'update_rollback')
 execute(f'DELETE FROM {a} WHERE case_id={case}');execute(f'DELETE FROM {b} WHERE case_id={case}')
 return steps

def main():
 p=argparse.ArgumentParser();p.add_argument('--setup',action='store_true');p.add_argument('--pilot',type=int,default=0);p.add_argument('--workers',type=int,default=4);args=p.parse_args();data=tables()
 if args.setup:print('dataset',setup(data),flush=True)
 out=ROOT/'results'/('pilot' if args.pilot else 'canonical');out.mkdir(parents=True,exist_ok=True)
 oracle=local_oracle(data)
 for f in range(50):
  try:oracle.execute(sql_for(f,0,rows=f>=40)).fetchall()
  except Exception as e:raise RuntimeError(f'Oracle preflight {f}: {e}') from e
 oracle.close();print('oracle preflight passed',flush=True)
 ids=[f*200+i for i in (np.linspace(0,199,args.pilot,dtype=int) if args.pilot else range(200)) for f in range(50)];np.random.default_rng(2026101103).shuffle(ids)
 c=connect()
 for w in range(args.workers):
  for table in [f'stage_input_{w}',f'stage_output_{w}']:
   with c.cursor() as q:q.execute(f'CREATE TABLE IF NOT EXISTS {table}({stage_schema()})');q.execute(f'SELECT COUNT(*) FROM {table}');assert q.fetchone()[0]==0,'non-empty previous stage table'
 c.close();stop=threading.Event();health=threading.Thread(target=monitor,args=(stop,out),daemon=True);health.start();lock=threading.Lock();counts=collections.Counter();started=time.time();log=Path('/workspace/mo-ds-lab/server.log');offset=log.stat().st_size
 def worker(w,indices):
  oracle=local_oracle(data);c=connect();eng=engine()
  for table in [f'stage_input_{w}',f'stage_output_{w}']:oracle.execute(f'CREATE TABLE {table}({stage_schema()})')
  with (out/f'cases-{w}.jsonl').open('w') as file:
   for case in indices:
    case=int(case);f,i=divmod(case,200);sql=sql_for(f,i,rows=f>=40);r={'case_id':case,'family':label(f)[0],'category':label(f)[1],'parameter':i,'params':parameters(i),'client':'pandas' if case%2 else 'numpy','complexity':complexity(f,i),'sql':sql};t=time.perf_counter()
    try:
     expected=oracle.execute(sql).fetchall();r['oracle_ms']=(time.perf_counter()-t)*1000;tq=time.perf_counter()
     try:
      if case%2:
       with eng.connect() as con:frame=pd.read_sql(text(sql),con,coerce_float=False)
       actual=list(frame.itertuples(index=False,name=None))
      else:
       with c.cursor() as q:q.execute(sql);actual=q.fetchall()
      r.update(query_ms=(time.perf_counter()-tq)*1000,actual=plain(actual),expected=plain(expected),row_count=len(actual));r['status']='pass' if equal(expected,actual) else 'mismatch'
      if f>=40 and r['status']=='pass':r['steps']=multi_stage(c,oracle,case,f,actual,expected,w)
     except Exception as e:
      r.update(status='sql_error' if 'stage' not in str(e) else 'stage_mismatch',error=str(e)[:5000],query_ms=(time.perf_counter()-tq)*1000)
      try:c.rollback()
      except Exception:pass
      try:
       with c.cursor() as q:
        for table in [f'stage_input_{w}',f'stage_output_{w}']:q.execute(f'DELETE FROM {table} WHERE case_id=%s',(case,))
      except Exception:pass
    except Exception as e:r.update(status='harness_error',error=str(e),traceback=traceback.format_exc())
    r['total_ms']=(time.perf_counter()-t)*1000;file.write(json.dumps(r,allow_nan=False)+'\n');file.flush()
    with lock:
     counts[r['status']]+=1;n=sum(counts.values())
     if n%100==0:print(json.dumps({'completed':n,'target':len(ids),'seconds':round(time.time()-started,2),'counts':dict(counts)}),flush=True)
  c.close();eng.dispose();oracle.close()
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(lambda t:worker(*t),[(w,ids[w::args.workers]) for w in range(args.workers)]))
 finally:stop.set();health.join()
 meta={'cases':len(ids),'unique_cases':len(set(ids)),'counts':dict(counts),'seconds':time.time()-started,'workers':args.workers,'families':50,'parameters_per_family':200,'log_start_offset':offset,'log_end_offset':log.stat().st_size,'started_at':started,'ended_at':time.time(),'sql_cases':8000 if not args.pilot else 40*args.pilot,'multi_stage_cases':2000 if not args.pilot else 10*args.pilot}
 (out/'meta.json').write_text(json.dumps(meta,indent=2));print(meta,flush=True)
 assert sum(counts.values())==len(ids)
if __name__=='__main__':main()
