"""Execute complete business workflows; stage assertions never inflate case count."""
import argparse,collections,concurrent.futures,decimal,hashlib,json,os,threading,time,traceback
from pathlib import Path
import numpy as np,pandas as pd,psutil
from sqlalchemy import text
from data import ROOT,DB,tables,local_oracle,connect,engine
from catalog import MISSIONS,queries,catalog
from facts import params
from analysis import calculate
def plain(x):
 if isinstance(x,dict):return {str(k):plain(v) for k,v in x.items()}
 if isinstance(x,(list,tuple,np.ndarray)):return [plain(v) for v in x]
 if isinstance(x,np.generic):x=x.item()
 if isinstance(x,decimal.Decimal):x=float(x)
 if isinstance(x,float) and not np.isfinite(x):return None if np.isnan(x) else str(x)
 return x
def equal(a,b):
 if isinstance(a,dict):return isinstance(b,dict) and a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
 if isinstance(a,(list,tuple,np.ndarray)):return isinstance(b,(list,tuple,np.ndarray)) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
 if a is None or b is None:return a is b
 if isinstance(a,(str,bool)):return a==b
 if isinstance(a,(int,np.integer)) and isinstance(b,(int,np.integer)):return a==b
 return bool(abs(float(a)-float(b))<=1e-7+1e-7*abs(float(a)))
def rows_equal(a,b,integers=()):
 if a.shape!=b.shape or list(a.columns)!=list(b.columns):return False
 x=a.to_numpy(dtype=float);y=b.to_numpy(dtype=float)
 if not np.array_equal(np.isnan(x),np.isnan(y)):return False
 if not np.all(np.isclose(x,y,rtol=1e-7,atol=1e-7,equal_nan=True)):return False
 for col in integers:
  xx=a[col].to_numpy(dtype=float);yy=b[col].to_numpy(dtype=float);valid=~np.isnan(xx)
  if not np.array_equal(xx[valid],yy[valid]):return False
 return True
def frame_receipt(f):
 a=f.to_numpy(dtype=float);return {'rows':len(f),'columns':list(f.columns),'float64_sha256':hashlib.sha256(a.astype('<f8').tobytes()).hexdigest(),'sample':plain(f.head(2).replace({np.nan:None}).values.tolist()+f.tail(2).replace({np.nan:None}).values.tolist())}
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
def publish(c,oracle,w,case,model,expected_model):
 table=f'decisions_{w}';records=[(case,*r) for r in model['decisions']];expected_records=[(case,*r) for r in expected_model['decisions']];steps=[]
 def execute(sql):
  t=time.perf_counter()
  with c.cursor() as q:q.execute(sql);rows=q.fetchall()
  steps.append({'sql':sql,'ms':(time.perf_counter()-t)*1000});return rows
 execute('BEGIN')
 if records:
  t=time.perf_counter()
  with c.cursor() as q:q.executemany(f'INSERT INTO {table} VALUES(%s,%s,%s,%s)',records)
  steps.append({'sql':f'INSERT INTO {table} VALUES(bound decision rows)','rows':len(records),'ms':(time.perf_counter()-t)*1000})
 oracle.execute(f'DELETE FROM {table}')
 if expected_records:oracle.executemany(f'INSERT INTO {table} VALUES(?,?,?,?)',expected_records)
 read=f'SELECT entity,allocation,benefit FROM {table} WHERE case_id={case} ORDER BY entity'
 expected=oracle.execute(read).fetchall();actual=execute(read)
 if not equal(plain(expected),plain(actual)):raise AssertionError('decision_roundtrip_mismatch')
 aggregate=f'SELECT COUNT(*),COALESCE(SUM(allocation),0),COALESCE(SUM(benefit),0),COALESCE(MAX(benefit),0) FROM {table} WHERE case_id={case}'
 expected_agg=oracle.execute(aggregate).fetchall();actual_agg=execute(aggregate)
 if not equal(plain(expected_agg),plain(actual_agg)):raise AssertionError('decision_audit_mismatch')
 # Even cases persist their report before cleanup; odd cases simulate a cancelled report.
 commit=case%2==0;execute('COMMIT' if commit else 'ROLLBACK');visible=execute(read)
 if not equal(plain(expected if commit else []),plain(visible)):raise AssertionError('decision_publication_visibility_mismatch')
 execute(f'DELETE FROM {table} WHERE case_id={case}');return steps

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=6);ap.add_argument('--pilot',type=int,default=0);ap.add_argument('--resume-from',type=Path);args=ap.parse_args();data=tables();out=ROOT/'results'/('pilot' if args.pilot else 'canonical');out.mkdir(parents=True,exist_ok=True)
 indices=np.linspace(0,249,args.pilot,dtype=int) if args.pilot else range(250);ids=[f*250+int(i) for f in range(40) for i in indices];np.random.default_rng(2026101106).shuffle(ids)
 retained=[];checkpoint=None
 if args.resume_from:
  assert not args.pilot
  checkpoint=json.loads((args.resume_from/'checkpoint-meta.json').read_text())
  for name,digest in checkpoint['unchanged_code_hashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,('changed analytical code',name)
  assert hashlib.sha256((ROOT/'dataset-manifest.json').read_bytes()).hexdigest()==checkpoint['dataset_manifest_sha256'],'source fixture changed'
  for file in sorted(args.resume_from.glob('cases-*.jsonl')):
   for line in file.open():
    try:r=json.loads(line)
    except ValueError:continue
    f,i=divmod(r['case_id'],250)
    if r['status']=='pass' and [s['sql'] for s in r['stages']]==queries(f,i) and r['parameters']==params(i):r['retained_verified_segment']=str(args.resume_from.name);retained.append(r)
  accepted={r['case_id'] for r in retained};assert len(accepted)==len(retained);ids=[case for case in ids if case not in accepted]
  (out/'cases-reused.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in retained));(out/'health-previous.jsonl').write_bytes((args.resume_from/'health.jsonl').read_bytes());print('retained',len(retained),'identical already verified workflows; executing',len(ids),flush=True)
 (ROOT/'requirements-catalog.json').write_text(json.dumps(catalog(),ensure_ascii=False,indent=2));c=connect()
 for w in range(args.workers):
  with c.cursor() as q:q.execute(f'CREATE TABLE IF NOT EXISTS decisions_{w}(case_id INT,entity INT,allocation DOUBLE,benefit DOUBLE)');q.execute(f'SELECT COUNT(*) FROM decisions_{w}');assert q.fetchone()[0]==0
 c.close();started=time.time();log=Path('/workspace/mo-ds-lab/server.log');offset=log.stat().st_size;stop=threading.Event();health=threading.Thread(target=monitor,args=(stop,out),daemon=True);health.start();counts=collections.Counter(r['status'] for r in retained);lock=threading.Lock();target=len(ids)+len(retained)
 def worker(w,cases):
  oracle=local_oracle(data);oracle.execute(f'CREATE TABLE decisions_{w}(case_id INT,entity INT,allocation DOUBLE,benefit DOUBLE)');c=connect();eng=engine()
  with (out/f'cases-{w}.jsonl').open('w') as file:
   for case in cases:
    f,i=divmod(int(case),250);m=MISSIONS[f];r={'case_id':int(case),'requirement':m['key'],'question':m['question'],'parameter':i,'parameters':params(i),'client':'pandas_sqlalchemy' if case%2 else 'pymysql_numpy','stages':[]};t=time.perf_counter();expected_frames=[];actual_frames=[];state='reference'
    try:
     for index,sql in enumerate(queries(f,i)):
      tq=time.perf_counter();cur=oracle.execute(sql);columns=[d[0] for d in cur.description];integer_cols=[d[0] for d in cur.description if str(d[1]) in ['INTEGER','BIGINT','SMALLINT','TINYINT','HUGEINT','UBIGINT']];expected=pd.DataFrame(cur.fetchall(),columns=columns);oracle_ms=(time.perf_counter()-tq)*1000;state='extract';tq=time.perf_counter()
      if case%2:
       with eng.connect() as con:actual=pd.read_sql(text(sql),con,coerce_float=False)
      else:
       with c.cursor() as q:q.execute(sql);actual=pd.DataFrame(q.fetchall(),columns=[d[0] for d in q.description])
      stage={'index':index,'sql':sql,'query_ms':(time.perf_counter()-tq)*1000,'oracle_ms':oracle_ms,'integral_columns':integer_cols,'expected':frame_receipt(expected),'actual':frame_receipt(actual),'status':'pass' if rows_equal(expected,actual,integer_cols) else 'mismatch'};r['stages'].append(stage)
      if stage['status']!='pass':r['failed_extract_expected']=plain(expected.replace({np.nan:None}).values.tolist());r['failed_extract_actual']=plain(actual.replace({np.nan:None}).values.tolist());raise AssertionError('extract_mismatch')
      expected_frames.append(expected);actual_frames.append(actual)
     state='analysis';ta=time.perf_counter();expected_model=plain(calculate(m['key'],expected_frames,i));actual_model=plain(calculate(m['key'],actual_frames,i));r.update(expected_analysis=expected_model,actual_analysis=actual_model,analysis_ms=(time.perf_counter()-ta)*1000)
     if not equal(expected_model,actual_model):raise AssertionError('analysis_mismatch')
     if not all(expected_model['checks'].values()):raise AssertionError('reference_business_constraint_failure')
     if not all(actual_model['checks'].values()):raise AssertionError('business_constraint_failure')
     state='publication';r['publication']=publish(c,oracle,w,int(case),actual_model,expected_model);r['status']='pass'
    except Exception as e:
     r.update(status='harness_error' if state=='reference' or 'reference_business_constraint' in str(e) else 'sql_error' if state=='extract' and 'mismatch' not in str(e) else 'extract_mismatch' if state=='extract' else 'analysis_mismatch' if state=='analysis' else 'publication_error',error=str(e)[:5000],phase=state,traceback=traceback.format_exc())
     try:
      c.rollback()
      with c.cursor() as q:q.execute(f'DELETE FROM decisions_{w} WHERE case_id=%s',(int(case),))
     except Exception:pass
    r['total_ms']=(time.perf_counter()-t)*1000;file.write(json.dumps(r,allow_nan=False)+'\n');file.flush()
    with lock:
     counts[r['status']]+=1;n=sum(counts.values())
     if n%100==0:print(json.dumps({'completed':n,'target':target,'seconds':round(time.time()-started,2),'counts':dict(counts)}),flush=True)
  c.close();eng.dispose();oracle.close()
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:list(pool.map(lambda pair:worker(*pair),[(w,ids[w::args.workers]) for w in range(args.workers)]))
 finally:stop.set();health.join()
 meta={'cases':target,'counts':dict(counts),'seconds':time.time()-started,'workers':args.workers,'requirements':40,'parameters_each':250,'started_at':started,'ended_at':time.time(),'log_start_offset':offset,'log_end_offset':log.stat().st_size,'database':DB,'retained_identical_verified_cases':len(retained),'executed_this_segment':len(ids),'checkpoint':checkpoint};(out/'meta.json').write_text(json.dumps(meta,indent=2));print(meta,flush=True);assert sum(counts.values())==target
if __name__=='__main__':main()
