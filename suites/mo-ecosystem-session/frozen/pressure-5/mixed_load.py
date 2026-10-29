from runtime import *
import concurrent.futures,random
N=1000000
if __name__=='__main__':
 sql('CREATE TABLE writer_state(id BIGINT PRIMARY KEY,seq BIGINT,payload VARBINARY(160))');sql('CREATE TABLE dim(g INT PRIMARY KEY,category INT)')
 with db() as d,d.cursor() as c:c.executemany('INSERT INTO dim VALUES(%s,%s)',[(g,g//32) for g in range(128)])
def group_expected():
 out=[]
 for g in range(128):
  first=g if g else 128;cnt=(N-first)//128+1;out.append((g,cnt,cnt*(2*first+(cnt-1)*128)//2))
 return out
queries=[('point','SELECT id,g,v,d,bin,txt FROM million_rows WHERE id=%s'),('group','SELECT g,COUNT(*),SUM(id) FROM million_rows GROUP BY g ORDER BY g'),('join','SELECT category,COUNT(*),SUM(m.id) FROM million_rows m JOIN dim d ON m.g=d.g GROUP BY category ORDER BY category'),('sort','SELECT id FROM million_rows ORDER BY v DESC LIMIT 100'),('distinct','SELECT COUNT(DISTINCT v) FROM million_rows')]
expected_group=group_expected();expected_join=[(k,sum(c for g,c,s in expected_group if g//32==k),sum(s for g,c,s in expected_group if g//32==k)) for k in range(4)]
out={'runtime_ref':REF,'scope':'closed-loop collocated Python workload, 1M immutable fact table. Every read verifies result; every acknowledged writer state is verified after each stage. Latencies measured at client, includes queue/service/network and serialization.','stages':[]}
def run_stage(writers,readers,duration=60,batch=100):
 gate=threading.Barrier(writers+readers+1);end=[0];lat_w=[];lat_q={k:[] for k,q in queries};errors=[];wrong=[];oracle={};counts=[];r0=resources()
 def writer(w):
  state={};n=0;lat=[]
  try:
   with db() as d,d.cursor() as c:
    gate.wait()
    while time.monotonic()<end[0]:
     guard();rows=[(w*1000+(n+i)%1000,n+i,bytes([w%256])*128+(n+i).to_bytes(8,'big')) for i in range(batch)]
     t=time.monotonic();c.executemany('INSERT INTO writer_state VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE seq=VALUES(seq),payload=VALUES(payload)',rows);lat.append((time.monotonic()-t)*1000)
     for i,s,p in rows:state[i]=(s,p)
     n+=batch
  except Exception as e:errors.append({'role':'writer','worker':w,'error':str(e)})
  oracle.update(state);lat_w.extend(lat);counts.append(n)
 def reader(w):
  rng=random.Random(w+100);n=0
  try:
   with db() as d,d.cursor() as c:
    gate.wait()
    while time.monotonic()<end[0]:
     kind,q=queries[n%len(queries)];i=rng.randrange(1,N+1);t=time.monotonic();c.execute(q,(i,) if kind=='point' else None);rows=c.fetchall();lat_q[kind].append((time.monotonic()-t)*1000)
     if kind=='point':
      exp=(i,i%128,(-1 if i%2 else 1)*(9007199254740993+i),decimal.Decimal(f'{i%1000}.{i:018d}'),None if i%11==0 else (b'' if i%7==0 else bytes([0,255,i%256])),'键😀'+str(i));ok=rows==(exp,)
     elif kind=='group':ok=list(rows)==expected_group
     elif kind=='join':ok=list(rows)==expected_join
     elif kind=='sort':ok=[r[0] for r in rows]==list(range(N,N-200,-2))
     else:ok=rows==((N,),)
     if not ok:
      if len(wrong)<10:wrong.append({'role':'reader','kind':kind,'rows':rows[:5]})
     n+=1
  except Exception as e:errors.append({'role':'reader','worker':w,'kind':kind if n else None,'error':str(e)})
 with concurrent.futures.ThreadPoolExecutor(max_workers=writers+readers) as ex:
  fs=[ex.submit(writer,w) for w in range(writers)]+[ex.submit(reader,w) for w in range(readers)];t=time.monotonic();end[0]=t+duration;gate.wait()
  for f in fs:f.result()
 elapsed=time.monotonic()-t;bad=[]
 for i,s,p in sql('SELECT id,seq,payload FROM writer_state'):
  if i in oracle and (s,p)!=oracle[i]:bad.append(i)
 actual_count=sql('SELECT COUNT(*) FROM writer_state')[0][0];expected_count=len(oracle)
 r={'writers':writers,'readers':readers,'batch_rows':batch,'requested_duration_s':duration,'inclusive_elapsed_s':elapsed,'acknowledged_row_ops':sum(counts),'ack_row_ops_s':sum(counts)/elapsed,'writer_transaction_latency':stats(lat_w),'read_latency':{k:stats(v) for k,v in lat_q.items()},'read_queries':sum(len(v) for v in lat_q.values()),'errors':errors,'incorrect_read_samples':wrong,'writer_state_oracle':{'mismatch_ids':bad[:10],'expected_latest_keys':expected_count,'actual_keys':actual_count,'passed':not bad and expected_count==actual_count},'before':r0,'after':resources()};out['stages'].append(r);dump(B/'mixed-load-result.json',out);print('MIXED',writers,readers,elapsed,r['ack_row_ops_s'],r['read_queries'],len(errors),len(wrong),flush=True)
if __name__=='__main__':
 for w,r in [(4,0),(4,2),(8,4),(16,8)]:
  sql('TRUNCATE TABLE writer_state');run_stage(w,r)
