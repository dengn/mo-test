from runtime import *
import concurrent.futures,random
base=9007199254740993
for port in [6001,13306]:
 sql('CREATE TABLE pooling_point(id BIGINT PRIMARY KEY,txt VARCHAR(48))',port=port)
 with db(port=port) as d,d.cursor() as c:c.executemany('INSERT INTO pooling_point VALUES(%s,%s)',[(base+i,'pool😀'+str(i)) for i in range(2000)])
out={'runtime_ref':REF,'scope':'same 2000-row table, 32 threads, both execute SET timezone + exact point read every operation; vary connection reuse only. Four CPU shared with idle Kafka/Connect; no active CDC or native stress producer. Not maximum server QPS or auth-only profiler.','cases':[]}
for port,reuse in [(6001,False),(6001,True),(13306,False),(13306,True)]:
 gate=threading.Barrier(33);end=[0];lat=[];counts=[];errors=[];wrong=[]
 def worker(w):
  d=None;n=0;ll=[];rng=random.Random(w)
  try:
   gate.wait()
   while time.monotonic()<end[0]:
    i=rng.randrange(2000);t=time.monotonic()
    if d is None:d=db(port=port)
    with d.cursor() as c:c.execute("SET time_zone='+00:00'");c.execute('SELECT id,txt FROM pooling_point WHERE id=%s',(base+i,));r=c.fetchall()
    if r!=((base+i,'pool😀'+str(i)),):wrong.append({'worker':w,'i':i,'rows':r})
    if not reuse:d.close();d=None
    n+=1;ll.append((time.monotonic()-t)*1000)
  except Exception as e:errors.append({'worker':w,'error':str(e)})
  finally:
   if d is not None:d.close()
   lat.extend(ll);counts.append(n)
 with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
  fs=[ex.submit(worker,w) for w in range(32)];end[0]=time.monotonic()+20;gate.wait();t=time.monotonic()
  for f in fs:f.result()
 elapsed=time.monotonic()-t;r={'port':port,'reuse':reuse,'workers':32,'elapsed_s':elapsed,'completed_ops':sum(counts),'ops_s':sum(counts)/elapsed,'latency':stats(lat),'errors':errors,'incorrect_samples':wrong[:5],'status':'passed' if not errors and not wrong else 'failed'};out['cases'].append(r);dump(B/'pooling-control-result.json',out);print('POOL CONTROL',port,reuse,r['ops_s'],r['latency']['p99_ms'],r['status'],flush=True)
