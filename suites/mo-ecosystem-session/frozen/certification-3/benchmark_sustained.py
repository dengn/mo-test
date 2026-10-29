from runtime import *
import concurrent.futures,threading,hashlib
out={'runtime_ref':REF,'scope':'single collocated 4 CPU quota; Python text protocol closed-loop throughput, two 60s direct-load stages concurrent with 30min CDC soak; not server maximum','direct':[],'pipelines':[]}
def save():dump(B/'throughput-sustained-result.json',out)
for workers,batch in [(4,1),(4,100)]:
 gate=threading.Barrier(workers+1);lat=[];counts=[];errors=[]
 def worker(w):
  l=[];n=0
  try:
   with db() as d,d.cursor() as c:
    gate.wait();deadline=time.monotonic()+60
    while time.monotonic()<deadline:
     rows=[(w*1000+i,n+i,b'x'*64) for i in range(batch)]
     t=time.monotonic();c.executemany('INSERT INTO direct_bench VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v),payload=VALUES(payload)',rows);l.append((time.monotonic()-t)*1000);n+=batch
  except Exception as e:errors.append(str(e))
  lat.extend(l);counts.append(n)
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  futures=[ex.submit(worker,w) for w in range(workers)];gate.wait();begin=time.monotonic()
  for f in futures:f.result()
 elapsed=time.monotonic()-begin;r={'workers':workers,'batch_rows':batch,'duration_s':elapsed,'acknowledged_row_operations':sum(counts),'ack_row_ops_per_s':sum(counts)/elapsed,'transaction_count':len(lat),'transaction_ms_p50':percentile(lat,.5),'transaction_ms_p95':percentile(lat,.95),'transaction_ms_p99':percentile(lat,.99),'errors':errors};out['direct'].append(r);save();print('DIRECT',json.dumps(r),flush=True)

print("SUSTAINED DIRECT COMPLETE",flush=True)
