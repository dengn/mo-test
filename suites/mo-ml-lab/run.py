"""20 x 1000 cases: MO feature SQL -> deep train -> NumPy -> transactional serving."""
import argparse,concurrent.futures,hashlib,json,os,time,traceback
import numpy as np,pandas as pd,psutil
from sqlalchemy import URL,create_engine
from data import ROOT,DB,SCHEMAS,connect,tables,native,params,query,read,compare,audit
from models import MISSIONS,prepared,fit,predict,numpy_forward,evaluate,serialize,reload
EXECUTION_FILES=['data.py','models.py','run.py']
def digest(b):return hashlib.sha256(b).hexdigest()
def table(c,w):
 with c.cursor() as q:
  q.execute(f'CREATE TABLE IF NOT EXISTS ml_models_{w}(case_id INT PRIMARY KEY,model_data LONGBLOB,model_hash VARCHAR(64),metadata TEXT)')
  q.execute(f'CREATE TABLE IF NOT EXISTS ml_predictions_{w}(case_id INT,eid INT,p0 DOUBLE,p1 DOUBLE,p2 DOUBLE,p3 DOUBLE)')
  for n in [f'ml_models_{w}',f'ml_predictions_{w}']:q.execute(f'SELECT COUNT(*) FROM {n}');assert q.fetchone()[0]==0,n
def publish(c,w,cid,blob,net,p,out,mission,i):
 keep=cid%2==0;h=digest(blob);meta=json.dumps(dict(mission=mission,i=i,mu=p['mu'].tolist(),sd=p['sd'].tolist(),median=p['median'].tolist(),ym=p['ym'].tolist(),ys=p['ys'].tolist()),separators=(',',':'))
 rows=[]
 for j in range(52,64):rows.append((cid,int(p['ids'][j]),*out[j].astype(float).tolist(),*[None]*(4-out.shape[1])))
 with c.cursor() as q:
  try:
   q.execute('BEGIN');q.execute(f'INSERT INTO ml_models_{w} VALUES(%s,%s,%s,%s)',(cid,blob,h,meta));q.executemany(f'INSERT INTO ml_predictions_{w} VALUES(%s,%s,%s,%s,%s,%s)',rows)
   q.execute(f'SELECT model_data,model_hash,metadata FROM ml_models_{w} WHERE case_id=%s',(cid,));b,storedhash,storedmeta=q.fetchone();assert b==blob and storedhash==h and storedmeta==meta
   reloaded=reload(b,mission,i);rt=predict(reloaded,p);np.testing.assert_array_equal(rt,out)
   q.execute(f'SELECT eid,p0,p1,p2,p3 FROM ml_predictions_{w} WHERE case_id=%s ORDER BY eid',(cid,));got=q.fetchall();assert len(got)==12
   np.testing.assert_allclose(np.array([r[1:1+out.shape[1]] for r in got],float),out[52:],rtol=1e-12,atol=1e-12)
   assert [r[0] for r in got]==p['ids'][52:].tolist()
   q.execute('COMMIT' if keep else 'ROLLBACK')
   # A separate connection tests externally visible committed/rolled-back serving data.
   view=connect()
   with view.cursor() as v:
    v.execute(f'SELECT COUNT(*) FROM ml_models_{w} WHERE case_id=%s',(cid,));assert v.fetchone()[0]==int(keep)
    v.execute(f'SELECT COUNT(*) FROM ml_predictions_{w} WHERE case_id=%s',(cid,));assert v.fetchone()[0]==(12 if keep else 0)
   view.close()
   q.execute(f'DELETE FROM ml_predictions_{w} WHERE case_id=%s',(cid,));q.execute(f'DELETE FROM ml_models_{w} WHERE case_id=%s',(cid,))
  except BaseException:
   q.execute('ROLLBACK');q.execute(f'DELETE FROM ml_predictions_{w} WHERE case_id=%s',(cid,));q.execute(f'DELETE FROM ml_models_{w} WHERE case_id=%s',(cid,));raise
 return dict(bytes=len(blob),sha256=h,transaction='commit' if keep else 'rollback',prediction_rows=12,reload_exact=True,external_visibility=True)
def case(c,engine,d,ref,w,m,i,save=True):
 start=time.perf_counter();cid=m*1000+i;sql=query(i);t=time.perf_counter()
 a=pd.read_sql_query(sql,engine).astype(float) if i%2 else read(c,sql);read_s=time.perf_counter()-t;compare(ref,a)
 p=prepared(a,i,d['edges']);rp=prepared(ref,i,d['edges'])
 for k in ['x','y','adj','mu','sd','median','ym','ys','ids','sp','anchor']:np.testing.assert_array_equal(p[k],rp[k],err_msg=k)
 t=time.perf_counter();net,out,training=fit(p,m,i);training_s=time.perf_counter()-t
 rn,ro,rm=fit(rp,m,i);np.testing.assert_array_equal(out,ro);assert training==rm
 ni=numpy_forward(net,p);np.testing.assert_allclose(ni,out,rtol=3e-5,atol=3e-5)
 for k,v in net.state_dict().items():np.testing.assert_array_equal(v.numpy(),rn.state_dict()[k].numpy())
 metrics=evaluate(out,p,net.task);oraclemetrics=evaluate(ro,rp,net.task);assert metrics==oraclemetrics
 blob=serialize(net);t=time.perf_counter();write=publish(c,w,cid,blob,net,p,out,m,i);publish_s=time.perf_counter()-t
 if save:
  target=ROOT/'models'/f'{cid:05d}.pt';target.write_bytes(blob)
 return dict(case_id=cid,status='pass',mission=MISSIONS[m],config=params(i),client='pandas_sqlalchemy' if i%2 else 'pymysql_numpy',database=DB,sql_sha256=digest(sql.encode()),sql_bytes=len(sql.encode()),fact_rows=len(a),source_tables=16,
  training=training,metrics=metrics,model=write,independent_numpy_max_abs_error=float(np.max(np.abs(ni-out))),train_entities=40,validation_entities=12,test_entities=12,train_anchor=int(p['anchor'][0]),validation_anchor=int(p['anchor'][40]),test_anchor=int(p['anchor'][52]),test_entity_ids=p['ids'][52:].tolist(),test_predictions=out[52:].tolist(),prediction_sha256=digest(out.astype('<f4').tobytes()),feature_sha256=digest(p['x'].astype('<f4').tobytes()),preprocessing=dict(mu=p['mu'].tolist(),sd=p['sd'].tolist(),target_mu=p['ym'].tolist(),target_sd=p['ys'].tolist()),seconds=time.perf_counter()-start,timing=dict(read=read_s,train=training_s,publish=publish_s),checks=['full_raw_facts','native_pandas_16_table_oracle','entity_isolation','temporal_label_gap','train_only_imputation','train_only_scaling','holdout_perturbation','block_diagonal_graph','finite_gradients','nonzero_updates','training_loss_decrease','validation_only_checkpoint','deterministic_reference_training','independent_numpy_inference','full_state_roundtrip','reload_exact_inference','full_prediction_roundtrip','external_commit_rollback_visibility'])
def engine():
 return create_engine(URL.create('mysql+pymysql',username=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),database=DB),connect_args={'connect_timeout':10,'read_timeout':90},pool_size=1,max_overflow=0)
def worker(w,indices,missions,tag):
 d=tables();c=connect();table(c,w);eng=engine();passed=failed=0;t=time.time()
 with (ROOT/f'{tag}-worker-{w}.jsonl').open('w') as log:
  for i in indices:
   ref=native(d,i)
   for m in missions:
    try:r=case(c,eng,d,ref,w,m,i,save=tag=='main');passed+=1
    except Exception as e:r=dict(case_id=m*1000+i,status='error',mission=MISSIONS[m],config=params(i),error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc());failed+=1
    log.write(json.dumps(r,separators=(',',':'))+'\n');log.flush()
   if (passed+failed)%100==0:print(json.dumps(dict(worker=w,pass_count=passed,fail_count=failed,elapsed=time.time()-t,last_i=i)),flush=True)
 c.close();eng.dispose();return dict(worker=w,passed=passed,failed=failed,seconds=time.time()-t)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pilot',action='store_true');ap.add_argument('--workers',type=int,default=4);args=ap.parse_args();tag='pilot' if args.pilot else 'main';indices=[0,5,27,199,443,777,999] if args.pilot else list(range(1000));n=args.workers
 (ROOT/'models').mkdir(exist_ok=True);start=time.time();frozen={f:digest((ROOT/f).read_bytes()) for f in EXECUTION_FILES};(ROOT/f'{tag}-start.json').write_text(json.dumps(dict(start_utc_epoch=start,code=frozen,database=DB,expected=len(indices)*20,workers=n,server_pid=1384),indent=2))
 if not args.pilot:audit(tables(),'main-before')
 with concurrent.futures.ProcessPoolExecutor(max_workers=n) as pool:
  fs=[pool.submit(worker,w,[v for k,v in enumerate(indices) if (k//4)%n==w],range(20),tag) for w in range(n)]
  while not all(f.done() for f in fs):
   mo=psutil.Process(1384);healthy=False;err=None
   try:
    c=connect();
    with c.cursor() as q:q.execute('SELECT 1');healthy=q.fetchone()[0]==1
    c.close()
   except Exception as e:err=str(e)
   client=psutil.Process();tree=[client]+client.children(recursive=True);client_rss=sum(p.memory_info().rss for p in tree if p.is_running())
   with (ROOT/f'{tag}-health.jsonl').open('a') as h:h.write(json.dumps(dict(time=time.time(),server_pid=mo.pid,rss=mo.memory_info().rss,client_tree_rss=client_rss,cgroup_memory_current=int(open('/sys/fs/cgroup/memory.current').read()),memory_events=open('/sys/fs/cgroup/memory.events').read().strip(),healthy=healthy,error=err))+'\n')
   time.sleep(5)
  results=[f.result() for f in fs]
 assert frozen=={f:digest((ROOT/f).read_bytes()) for f in EXECUTION_FILES},'execution code changed'
 meta=dict(expected=len(indices)*20,passed=sum(r['passed'] for r in results),failed=sum(r['failed'] for r in results),seconds=time.time()-start,workers=results,code=frozen)
 (ROOT/f'{tag}-summary.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta),flush=True)
 if not args.pilot:audit(tables(),'main-after')
 if meta['failed']:raise SystemExit(1)
if __name__=='__main__':main()
