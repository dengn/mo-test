from runtime import *
import concurrent.futures,collections,random
out={'runtime_ref':REF,'scope':'32/128 client threads repeatedly create/authenticate/set timezone/read exact point/close sessions. 1M table immutable. Then bounded read-only DISTINCT timeout and server-session cleanup; not general distributed cancellation certification.','connection_stages':[]}
for workers in [32,128]:
 gate=threading.Barrier(workers+1);end=[0];lat=[];counts=[];errors=[];wrong=[];active=[0];peak=[0];lock=threading.Lock();t0=time.monotonic()
 def worker(w):
  n=0;local=[];rng=random.Random(w)
  try:
   gate.wait()
   while time.monotonic()<end[0]:
    i=rng.randrange(1,1000001);t=time.monotonic()
    with db() as d,d.cursor() as c:
     with lock:active[0]+=1;peak[0]=max(peak[0],active[0])
     try:c.execute("SET time_zone='+00:00'");c.execute('SELECT id,txt FROM million_rows WHERE id=%s',(i,));rows=c.fetchall()
     finally:
      with lock:active[0]-=1
     if rows!=((i,'键😀'+str(i)),):wrong.append({'i':i,'rows':rows})
    local.append((time.monotonic()-t)*1000);n+=1
  except Exception as e:errors.append({'worker':w,'error':str(e)})
  counts.append(n);lat.extend(local)
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  fs=[ex.submit(worker,w) for w in range(workers)];end[0]=time.monotonic()+30;gate.wait();t=time.monotonic()
  for f in fs:f.result()
 elapsed=time.monotonic()-t;r={'client_threads':workers,'observed_peak_live_sessions':peak[0],'elapsed_s':elapsed,'completed_sessions':sum(counts),'completed_sessions_s':sum(counts)/elapsed,'session_latency_including_connect_auth_query_close':stats(lat),'errors':errors,'wrong_rows':wrong[:5],'status':'passed' if not errors and not wrong else 'failed'};out['connection_stages'].append(r);dump(B/'connections-cancel-result.json',out);print('CONNECTION CHURN',workers,r['completed_sessions_s'],peak[0],r['status'],flush=True)
cancel=[]
def timeout_one(w):
 d=db();cid=d.thread_id();d._read_timeout=.02;t=time.monotonic();r={'worker':w,'connection_id':cid,'read_timeout_seconds':.02}
 try:
  with d.cursor() as c:c.execute('SELECT /* stress5_cancel */ COUNT(DISTINCT v) FROM million_rows');r['rows']=c.fetchall();r['client_outcome']='completed';r['correct']=r['rows']==((1000000,),)
 except pymysql.MySQLError as e:r['client_outcome']='timeout_or_connection_error';r['error']=str(e)
 finally:
  try:d.close()
  except pymysql.Error:pass
 r['client_elapsed_s']=time.monotonic()-t;cancel.append(r)
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:list(ex.map(timeout_one,range(32)))
ids={r['connection_id'] for r in cancel};t=time.monotonic();remaining=[]
while time.monotonic()-t<15:
 remaining=[r[1] for r in sql('SHOW FULL PROCESSLIST') if r[1] in ids]
 if not remaining:break
 time.sleep(.25)
out['read_timeout_cases']=cancel;out['session_cleanup']={'remaining_connection_ids':remaining,'sampled_cleanup_after_clients_finish_s':time.monotonic()-t,'status':'passed' if not remaining and all(r.get('correct',True) for r in cancel) else 'failed'};out['final_immutable_counts']=sql('SELECT COUNT(*),SUM(id) FROM million_rows');out['after']=resources();dump(B/'connections-cancel-result.json',out);print('READ TIMEOUT CLEANUP',len(cancel),out['session_cleanup'],flush=True)
