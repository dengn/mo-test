from runtime import *
import threading
out={'runtime_ref':REF,'scope':'60s per input-rate step, concurrent with 10/s Kafka and 5/s NiFi soak cohort; batches sent once per second; observation poll 250ms; not max-capacity search','stages':[]}
poll(lambda:(B/'soak-progress.json').exists() and json.loads((B/'soak-progress.json').read_text())['elapsed_s']>=240,400)
for idx,(route,rate) in enumerate([('kafka',50),('kafka',100),('kafka',200),('nifi',25),('nifi',50)]):
 count=rate*60;low=2100000+idx*20000 if route=='kafka' else 210000+(idx-3)*5000;database='cert3' if route=='kafka' else 'runtime_ecosystem';table='records' if route=='kafka' else 'nifi_source';target='records' if route=='kafka' else 'nifi_outbox_target';stamp='produced_ms' if route=='kafka' else 'updated';seen={};done=threading.Event();producer_errors=[];source_ack=[];start_t=time.monotonic();soak_start=json.loads((B/'soak-progress.json').read_text())['elapsed_s']
 def produce():
  for tick in range(60):
   time.sleep(max(0,start_t+tick-time.monotonic()));now=int(time.time()*1000)
   if route=='kafka':
    rr=[(low+tick*rate+i,2**64-1,'12345678901234567890.123456789012345678',b'\x00\xff\x80','阶梯😀','2026-10-11 12:00:00.123456','{"n":9007199254740993}',now) for i in range(rate)];stmt='INSERT INTO records VALUES('+','.join(['%s']*8)+')'
   else:
    rr=[(low+tick*rate+i,2**63-1,2**64-1,'12345678901234567890.123456789012345678',b'\x00\xff\x80','阶梯😀','2026-10-11 12:00:00.123456','{"n":9007199254740993}',now) for i in range(rate)];stmt='INSERT INTO nifi_source(id,s,u,d,payload,name,ts,doc,updated) VALUES('+','.join(['%s']*9)+')'
   try:
    t=time.monotonic()
    with db(13306,database) as d,d.cursor() as c:c.executemany(stmt,rr)
    source_ack.append((time.monotonic()-t)*1000)
   except Exception as e:producer_errors.append(str(e))
  time.sleep(max(0,start_t+60-time.monotonic()));done.set()
 thread=threading.Thread(target=produce,daemon=True);thread.start();deadline=start_t+180;at60=None;max_backlog=0
 while time.monotonic()<deadline and (not done.is_set() or len(seen)<count):
  try:
   rr=sql(6001,database,'SELECT id,'+stamp+' FROM '+target+' WHERE id>=%s AND id<%s',(low,low+count));now=time.time()*1000
   for id,ts in rr:seen.setdefault(id,now-ts)
  except Exception as e:out.setdefault('target_poll_errors',[]).append({'route':route,'error':str(e),'elapsed_s':time.monotonic()-start_t})
  produced=min(count,(int(time.monotonic()-start_t)+1)*rate);max_backlog=max(max_backlog,produced-len(seen))
  if time.monotonic()-start_t>=60 and at60 is None:at60=len(seen)
  time.sleep(.25)
 thread.join(timeout=2);elapsed=time.monotonic()-start_t;values=list(seen.values());stage={'route':route,'requested_input_rows_per_s':rate,'duration_source_s':60,'submitted':count,'target_visible':len(seen),'target_visible_at_60s':at60,'elapsed_including_drain_s':elapsed,'end_to_end_rows_per_s_including_drain':len(seen)/elapsed,'max_estimated_backlog':max_backlog,'latency_ms_p50':percentile(values,.5),'latency_ms_p95':percentile(values,.95),'latency_ms_p99':percentile(values,.99),'source_batch_commit_ms_p99':percentile(source_ack,.99),'source_errors':producer_errors,'soak_elapsed_at_start':soak_start,'soak_elapsed_at_end':json.loads((B/'soak-progress.json').read_text())['elapsed_s'],'status':'passed_delivery_at_tested_rate' if len(seen)==count and not producer_errors else 'failed'}
 out['stages'].append(stage);dump(B/'staircase-result.json',out);print('STAIRCASE',json.dumps(stage,ensure_ascii=False),flush=True)
print('STAIRCASE COMPLETE',flush=True)
