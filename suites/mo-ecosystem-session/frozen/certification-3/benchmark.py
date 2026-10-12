from runtime import *
import concurrent.futures,threading,hashlib
out={'runtime_ref':REF,'scope':'single collocated 4 CPU quota; Python text protocol closed-loop throughput, not server maximum; end-to-end CDC poll resolution 250ms','direct':[],'pipelines':[]}
def save():dump(B/'throughput-result.json',out)
for workers,batch in [(1,1),(4,1),(8,1),(1,100),(4,100)]:
 gate=threading.Barrier(workers+1);lat=[];counts=[];errors=[]
 def worker(w):
  l=[];n=0
  try:
   with db() as d,d.cursor() as c:
    gate.wait();deadline=time.monotonic()+8
    while time.monotonic()<deadline:
     rows=[(w*1000+i,n+i,b'x'*64) for i in range(batch)]
     t=time.monotonic();c.executemany('INSERT INTO direct_bench VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v),payload=VALUES(payload)',rows);l.append((time.monotonic()-t)*1000);n+=batch
  except Exception as e:errors.append(str(e))
  lat.extend(l);counts.append(n)
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  futures=[ex.submit(worker,w) for w in range(workers)];gate.wait();begin=time.monotonic()
  for f in futures:f.result()
 elapsed=time.monotonic()-begin;r={'workers':workers,'batch_rows':batch,'duration_s':elapsed,'acknowledged_row_operations':sum(counts),'ack_row_ops_per_s':sum(counts)/elapsed,'transaction_count':len(lat),'transaction_ms_p50':percentile(lat,.5),'transaction_ms_p95':percentile(lat,.95),'transaction_ms_p99':percentile(lat,.99),'errors':errors};out['direct'].append(r);save();print('DIRECT',json.dumps(r),flush=True)
# Independent bounded full-pipeline bursts. Latency includes source commit and observation polling.
for route,count in [('kafka',1000),('nifi',500)]:
 source_table='records' if route=='kafka' else 'nifi_source';source_db='cert3' if route=='kafka' else 'runtime_ecosystem';target='records' if route=='kafka' else 'nifi_outbox_target';low=1000000 if route=='kafka' else 100000
 start_ms=int(time.time()*1000);begin=time.monotonic();lat=[];seen=set()
 if route=='kafka':
  values=[(low+i,2**64-1,'12345678901234567890.123456789012345678',b'\x00\xff\x80','吞吐😀','2026-10-11 12:00:00.123456','{"n":9007199254740993}',start_ms) for i in range(count)]
  stmt='INSERT INTO records VALUES('+','.join(['%s']*8)+')'
 else:
  values=[(low+i,2**63-1,2**64-1,'12345678901234567890.123456789012345678',b'\x00\xff\x80','吞吐😀','2026-10-11 12:00:00.123456','{"n":9007199254740993}',start_ms) for i in range(count)]
  stmt='INSERT INTO nifi_source(id,s,u,d,payload,name,ts,doc,updated) VALUES('+','.join(['%s']*9)+')'
 with db(13306,source_db) as d,d.cursor() as c:c.executemany(stmt,values)
 source_ack=time.monotonic()-begin
 deadline=time.monotonic()+180
 while time.monotonic()<deadline and len(seen)<count:
  rows=sql(6001,source_db,'SELECT id FROM '+target+' WHERE id>=%s AND id<%s',(low,low+count));now=(time.monotonic()-begin)*1000
  for (id,) in rows:
   if id not in seen:seen.add(id);lat.append(now)
  time.sleep(.25)
 elapsed=time.monotonic()-begin;r={'route':route,'submitted':count,'source_ack_s':source_ack,'target_visible':len(seen),'total_s':elapsed,'end_to_end_rows_per_s':len(seen)/elapsed,'visibility_ms_p50':percentile(lat,.5),'visibility_ms_p95':percentile(lat,.95),'visibility_ms_p99':percentile(lat,.99),'status':'passed' if len(seen)==count else 'failed','payload_profile':'unsigned64/decimal38,18/binary/Unicode/JSON/DATETIME6'};out['pipelines'].append(r);save();print('PIPELINE',json.dumps(r),flush=True)
print('BENCHMARK COMPLETE',flush=True)
