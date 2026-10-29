from runtime import *
import cdc_load as m,concurrent.futures
out={'runtime_ref':REF,'scope':'MO SIGKILL while four clients issue validated 1M-row aggregates; 25,008 PG rows change during outage; real CDC resumes. Separate native durability full-row SHA check. Kafka/JDBC final-state idempotence, not EOS.','cases':[]};stop=threading.Event();reads=[];read_errors=[];faulting=[False]
def read(w):
 while not stop.is_set():
  try:
   with db() as d,d.cursor() as c:
    t=time.monotonic();c.execute('SELECT COUNT(*),SUM(id),MAX(id) FROM million_rows');rows=c.fetchall();reads.append({'worker':w,'ms':(time.monotonic()-t)*1000,'correct':rows==((1000000,500000500000,1000000),),'fault_window':faulting[0]})
  except Exception as e:
   if len(read_errors)<50:read_errors.append({'worker':w,'error':str(e),'fault_window':faulting[0]})
   time.sleep(.1)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 fs=[ex.submit(read,w) for w in range(4)];time.sleep(5);t0=time.monotonic();faulting[0]=True;out['fault']=kill('mo','/workspace/matrixone/mo-service');psql("UPDATE stress5.wide SET rev=5,name='目标宕机积压😀' WHERE id BETWEEN 8000 AND 9562");time.sleep(5);out['sink_states_before_restart']=api('GET','/connectors/stress5-mo/status');start('mo');poll(lambda:sql('SELECT 1'),90);out['service_ready_seconds']=time.monotonic()-t0
 end=time.monotonic()+120;manual=False;samples=[];wanted=1563*16
 while time.monotonic()<end:
  status=api('GET','/connectors/stress5-mo/status');mo=sql('SELECT COUNT(*) FROM cdc_wide WHERE rev=5')[0][0];my=sql('SELECT COUNT(*) FROM cdc_wide WHERE rev=5',port=13306)[0][0];samples.append({'elapsed_s':time.monotonic()-t0,'MO_rev5':mo,'MySQL_rev5':my,'task_states':[v['state'] for v in status['tasks']]})
  if mo==my==wanted:break
  if not manual and any(v['state']=='FAILED' for v in status['tasks']):
   out['failed_task_trace']=status;api('POST','/connectors/stress5-mo/restart?includeTasks=true&onlyFailed=true');manual=True
  time.sleep(1)
 out['manual_failed_task_restart_required']=manual;out['recovery_samples']=samples;out['cases'].append({'case':'source_updates_during_MO_outage_then_resume','expected_changed_rows':wanted,'MO_rev5':mo,'MySQL_rev5':my,'inclusive_reconcile_s':time.monotonic()-t0,'status':'passed' if mo==my==wanted else 'failed'});stop.set()
 for f in fs:f.result()
out['validated_read_queries']=len(reads);out['wrong_read_queries']=sum(not r['correct'] for r in reads);out['successful_read_latency']=stats([r['ms'] for r in reads]);out['expected_fault_read_error_samples']=read_errors;dump(B/'target-crash-result.json',out)
original_dump=m.dump
def save(path,value):
 if Path(path).name=='cdc-load-result.json':path=B/'cdc-target-crash-oracle.json'
 return original_dump(path,value)
m.dump=save;m.out={'runtime_ref':REF,'tag_added':True,'scope':'full row/field oracle after target SIGKILL recovery','cases':[]};m.oracle('MO_target_SIGKILL_resume_full_fields')
# Recompute the independently generated immutable million-row hash after actual SIGKILL.
actual=hashlib.sha256();count=0
with db() as d,d.cursor(pymysql.cursors.SSCursor) as c:
 c.execute('SELECT id,g,v,d,bin,txt FROM million_rows ORDER BY id')
 for i,g,v,amount,b,txt in c:
  count+=1;actual.update(json.dumps([i,g,v,format(amount,'.18f'),b.hex() if b is not None else None,txt],ensure_ascii=False,separators=(',',':')).encode()+b'\n')
expected=json.loads((B/'million-load-result.json').read_text())['oracle']['expected_sha256'];out['cases'].append({'case':'million_rows_ACKed_before_fault_full_SHA_durability','rows':count,'actual_sha256':actual.hexdigest(),'expected_sha256':expected,'status':'passed' if count==1000000 and actual.hexdigest()==expected else 'failed'});out['after']=resources();dump(B/'target-crash-result.json',out);print('TARGET CRASH COMPLETE',[(r['case'],r['status']) for r in out['cases']],manual,flush=True)
