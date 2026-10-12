"""Run all 10000 actual MO cases, including required unsupported semantics as failures."""
import argparse,collections,concurrent.futures,hashlib,json,os,threading,time,traceback
from pathlib import Path
import numpy as np,pandas as pd,psutil
from sqlalchemy import text
from data import ROOT,DB,tables,connect,engine,oracle,read,compare,setup,audit,reference_sql
from scenarios import QUESTIONS,params,sql_for,daily_ctes,events_ctes,complexity
import native

NATIVE_INDICES={0,1,17,28,59,60,61,99,125,177,198,199}
FROZEN=['data.py','scenarios.py','native.py','run.py']
def plain(obj):
 if isinstance(obj,dict):return {str(k):plain(v) for k,v in obj.items()}
 if isinstance(obj,(list,tuple,np.ndarray)):return [plain(v) for v in obj]
 if isinstance(obj,np.generic):obj=obj.item()
 if isinstance(obj,float) and not np.isfinite(obj):return None if np.isnan(obj) else str(obj)
 return obj
def records(frame):return plain(frame.to_numpy(float))
def receipt(frame):return dict(rows=len(frame),columns=list(frame),sha256=hashlib.sha256(frame.to_numpy('<f8').tobytes()).hexdigest())
def monitor(stop,folder):
 pid=int(os.getenv('MO_SERVER_PID',Path('/workspace/mo-ds-lab/server.pid').read_text().strip()));proc=psutil.Process(pid);c=None
 with (folder/'health.jsonl').open('w') as f:
  while not stop.is_set():
   row=dict(time=time.time(),pid=pid)
   try:
    if c is None:c=connect()
    c.ping(reconnect=False);row.update(healthy=True,mo_rss=proc.memory_info().rss,client_rss=sum(q.memory_info().rss for q in [psutil.Process(),*psutil.Process().children(recursive=True)] if q.is_running()),memory_current=int(Path('/sys/fs/cgroup/memory.current').read_text()),memory_events=Path('/sys/fs/cgroup/memory.events').read_text().strip())
   except Exception as exc:row.update(healthy=False,error=str(exc));c=None
   f.write(json.dumps(row)+'\n');f.flush();stop.wait(5)
 if c:c.close()

def stage(c,ref,case,actual,expected,w):
 name=f'ts_stage_{w}';steps=[];snapshot=connect()
 def execute(sql,args=None):
  t=time.perf_counter()
  with c.cursor() as q:q.execute(sql,args);values=q.fetchall();cols=[d[0] for d in q.description] if q.description else []
  steps.append(dict(sql=sql,ms=(time.perf_counter()-t)*1000,rows=len(values)));return pd.DataFrame(values,columns=cols)
 def fetch(connection):return read(connection,f'SELECT eid,day,score,y,budget FROM {name} WHERE case_id={case} ORDER BY eid,day')
 fields=['eid','day','score','y','budget'];df=actual[fields];gold=expected[fields]
 ref.execute(f'DELETE FROM {name}');ref.executemany(f'INSERT INTO {name} VALUES(?,?,?,?,?,?)',[(case,*r) for r in gold.itertuples(index=False,name=None)])
 try:
  execute('BEGIN');t=time.perf_counter()
  with c.cursor() as q:q.executemany(f'INSERT INTO {name} VALUES(%s,%s,%s,%s,%s,%s)',[(case,*r) for r in df.itertuples(index=False,name=None)])
  steps.append(dict(sql=f'INSERT INTO {name} (bound actual values)',ms=(time.perf_counter()-t)*1000,rows=len(df)));compare(gold,fetch(c));assert len(fetch(snapshot))==0,'uncommitted externally visible'
  sql=f'''SELECT eid,day,score,score-AVG(score) OVER(PARTITION BY eid ORDER BY day ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) centered,LAG(score,2,0) OVER(PARTITION BY eid ORDER BY day) previous,SUM(y) OVER(PARTITION BY eid ORDER BY day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) revenue FROM {name} WHERE case_id={case} ORDER BY eid,day'''
  g=ref.execute(sql).fetchdf();a=execute(sql);compare(g,a);steps[-1]['verified']=True
  commit=case%2==0;execute('COMMIT' if commit else 'ROLLBACK');after=fetch(snapshot)
  if commit:compare(gold,after)
  else:assert len(after)==0
  execute(f'DELETE FROM {name} WHERE case_id={case}');assert len(fetch(snapshot))==0
  return dict(steps=steps,commit=commit,external_visibility=True,persisted_rows=len(df),server_window_rows=len(a),cleanup=True)
 finally:
  snapshot.close()
  try:c.rollback()
  except Exception:pass
  with c.cursor() as q:q.execute(f'DELETE FROM {name} WHERE case_id=%s',(case,))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--setup',action='store_true');ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,default=4);args=ap.parse_args();data=tables()
 if args.setup:print(setup(data),flush=True);audit(data,'before')
 folder=ROOT/'results'/('pilot' if args.pilot else 'canonical');folder.mkdir(parents=True,exist_ok=True);assert not (folder/'meta.json').exists(),'Use a new attempt folder; completed results are immutable.'
 indices=[0,60,125,199] if args.pilot else list(range(200));ref=oracle(data)
 for f in range(50):ref.execute(sql_for(f,indices[0])).fetchdf()
 ref.close();print('All 50 original-data SQL preflights passed',flush=True)
 schema='case_id INT,eid INT,day INT,score DOUBLE,y DOUBLE,budget DOUBLE';c=connect()
 for w in range(args.workers):
  with c.cursor() as q:q.execute(f'CREATE TABLE IF NOT EXISTS ts_stage_{w}({schema})');q.execute(f'SELECT COUNT(*) FROM ts_stage_{w}');assert q.fetchone()[0]==0
 c.close();started=time.time();log=Path(os.getenv('MO_SERVER_LOG','/workspace/mo-ds-lab/server.log'));offset=log.stat().st_size;stop=threading.Event();thread=threading.Thread(target=monitor,args=(stop,folder),daemon=True);thread.start();counts=collections.Counter();lock=threading.Lock();base_records=[];native_records=[]
 code={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in FROZEN};(folder/'start.json').write_text(json.dumps(dict(started_at=started,code=code,log_offset=offset,database=DB),indent=2))
 def worker(w,items):
  ref=oracle(data);c=connect();eng=engine();ref.execute(f'CREATE TABLE ts_stage_{w}({schema})')
  try:
   with (folder/f'cases-{w}.jsonl').open('w') as file:
    for i in items:
     nd=native.daily(data,i);base_cols=[col for col in nd if col not in ['net','valid_from','valid_to']];base_cols=[col for col in base_cols if col in ['eid','region','sector','scale','day','week','weekday','utc_min','offset_min','sensor','observations','raw_count','original_sensor','y','demand','shipped','late_qty','stock','capacity','temp','price','rate','target','severity','budget','effect','event_count','late_count','phase0','phase1','neighbor','x']]
     sql='WITH '+daily_ctes(i)+' SELECT '+','.join(base_cols)+' FROM daily ORDER BY eid,day';gold=ref.execute(sql).fetchdf();compare(nd[base_cols],gold,1e-10);actual=read(c,sql);compare(nd[base_cols],actual,1e-10)
     ne=native.events(data,i);cols=['event_id','eid','day','minute','received_min','kind','magnitude','region','sector','weekday','offset_min','civil_min','x','rn','prev_min','prev_kind'];esql='WITH '+events_ctes(i)+' SELECT '+','.join(cols)+' FROM ev ORDER BY eid,minute,event_id';eg=ref.execute(esql).fetchdf();compare(ne[cols],eg,1e-12);ea=read(c,esql);compare(ne[cols],ea,1e-12)
     with lock:base_records.append(dict(parameter=i,daily_rows=len(gold),event_rows=len(eg),native_daily=True,native_events=True,mo_full_facts=True))
     families=list(np.random.default_rng(SEED_LOCAL+i).permutation(50))
     for ff in families:
      f=int(ff);case=f*200+i;sql=sql_for(f,i);r=dict(case_id=case,family=f,name=QUESTIONS[f][0],question=QUESTIONS[f][2],parameter=i,parameters=params(i),client='pandas_sqlalchemy' if case%2 else 'pymysql_numpy',complexity=complexity(sql),sql=sql);start=time.perf_counter()
      if reference_sql(sql)!=sql:r['oracle_optimizer_hint']='DuckDB layer CTEs AS MATERIALIZED; identical arithmetic/frames; independently checked using native NumPy.'
      try:
       t=time.perf_counter();expected=ref.execute(sql).fetchdf();r['oracle_ms']=(time.perf_counter()-t)*1000;r.update(columns=list(expected),expected=records(expected),expected_receipt=receipt(expected))
       if i in NATIVE_INDICES:
        checks=native.independently_check(data,f,i,expected)
        with lock:native_records.append(dict(case_id=case,**checks))
       t=time.perf_counter()
       try:
        if case%2:
         with eng.connect() as connection:actual=pd.read_sql(text(sql),connection,coerce_float=False)
        else:actual=read(c,sql)
        r.update(query_ms=(time.perf_counter()-t)*1000,actual=records(actual),actual_receipt=receipt(actual));compare(expected,actual)
        if f==49:r['publication']=stage(c,ref,case,actual,expected,w)
        r['status']='pass'
       except Exception as exc:r.update(status='mismatch' if isinstance(exc,AssertionError) else 'sql_or_stage_error',error=str(exc)[:10000],query_ms=(time.perf_counter()-t)*1000)
      except Exception as exc:r.update(status='reference_or_harness_error',error=str(exc),traceback=traceback.format_exc())
      r['total_ms']=(time.perf_counter()-start)*1000;file.write(json.dumps(plain(r),allow_nan=False)+'\n');file.flush()
      with lock:
       counts[r['status']]+=1;n=sum(counts.values())
       if n%100==0:print(json.dumps(dict(completed=n,target=len(indices)*50,seconds=round(time.time()-started,2),counts=dict(counts))),flush=True)
  finally:c.close();eng.dispose();ref.close()
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(lambda x:worker(*x),[(w,indices[w::args.workers]) for w in range(args.workers)]))
 finally:stop.set();thread.join();(folder/'base-checks.json').write_text(json.dumps(sorted(base_records,key=lambda r:r['parameter']),indent=2));(folder/'native-checks.json').write_text(json.dumps(sorted(native_records,key=lambda r:r['case_id']),indent=2))
 meta=dict(expected=len(indices)*50,completed=sum(counts.values()),counts=dict(counts),seconds=time.time()-started,workers=args.workers,started_at=started,ended_at=time.time(),log_start_offset=offset,log_end_offset=log.stat().st_size,code=code,base_configs_verified=len(base_records),native_checks=len(native_records));(folder/'meta.json').write_text(json.dumps(meta,indent=2));print(meta,flush=True);assert sum(counts.values())==len(indices)*50
SEED_LOCAL=2026101123
if __name__=='__main__':main()
