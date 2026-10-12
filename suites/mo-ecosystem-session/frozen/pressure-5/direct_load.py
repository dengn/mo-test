from runtime import *
import concurrent.futures
N=1000000
sql('CREATE TABLE IF NOT EXISTS million_rows(id BIGINT PRIMARY KEY,g INT,v BIGINT,d DECIMAL(38,18),bin VARBINARY(4),txt VARCHAR(48))')
assert sql('SELECT COUNT(*) FROM million_rows')[0][0]==0, 'fresh isolated fixture required'
def row(i):return (i,i%128,(-1 if i%2 else 1)*(9007199254740993+i),f'{i%1000}.{i:018d}',None if i%11==0 else (b'' if i%7==0 else bytes([0,255,i%256])),'键😀'+str(i))
q='INSERT INTO million_rows VALUES(%s,%s,%s,%s,%s,%s)';out={'runtime_ref':REF,'scope':'collocated Python/PyMySQL text protocol bulk insertion into a fresh table; includes client generation and serialization, not server maximum','target_rows':N,'stages':[]};done=0
def stage(workers,total):
 global done
 base=done;gate=threading.Barrier(workers+1);ack=[];lat=[];errors=[];start_resource=resources()
 def worker(w):
  local=[];cnt=0
  try:
   with db() as d,d.cursor() as c:
    gate.wait();lo=base+(total*w)//workers+1;hi=base+(total*(w+1))//workers+1
    for first in range(lo,hi,1000):
     guard();rows=[row(i) for i in range(first,min(first+1000,hi))];t=time.monotonic();c.executemany(q,rows);local.append((time.monotonic()-t)*1000);cnt+=len(rows)
  except Exception as e:errors.append({'worker':w,'error':str(e),'ack':cnt})
  ack.append(cnt);lat.extend(local)
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  fs=[ex.submit(worker,w) for w in range(workers)];gate.wait();t=time.monotonic()
  for f in fs:f.result()
 elapsed=time.monotonic()-t;r={'workers':workers,'attempted_rows':total,'acknowledged_rows':sum(ack),'batch_rows':1000,'elapsed_s':elapsed,'ack_rows_s':sum(ack)/elapsed,'transaction_latency':stats(lat),'errors':errors,'before':start_resource,'after':resources()};out['stages'].append(r);done+=total;dump(B/'million-load-result.json',out);print('MILLION STAGE',workers,sum(ack),elapsed,r['ack_rows_s'],flush=True);assert not errors,errors
for w,n in [(1,100000),(4,300000),(8,600000)]:stage(w,n)
expected=hashlib.sha256();actual=hashlib.sha256();bad=0;first_bad=[];count=0;t=time.monotonic()
with db() as d,d.cursor(pymysql.cursors.SSCursor) as c:
 c.execute('SELECT id,g,v,d,bin,txt FROM million_rows ORDER BY id')
 for rr in c:
  count+=1;i=rr[0];exp=row(count);normalized=(rr[0],rr[1],rr[2],format(rr[3],'.18f'),rr[4],rr[5])
  if normalized!=exp:
   bad+=1
   if len(first_bad)<10:first_bad.append({'position':count,'expected':exp,'actual':normalized})
  def canonical(r):return json.dumps([r[0],r[1],r[2],r[3],r[4].hex() if r[4] is not None else None,r[5]],ensure_ascii=False,separators=(',',':')).encode()+b'\n'
  expected.update(canonical(exp));actual.update(canonical(normalized))
out['oracle']={'read_rows':count,'expected_rows':N,'mismatched_rows':bad,'first_mismatches':first_bad,'expected_sha256':expected.hexdigest(),'actual_sha256':actual.hexdigest(),'verification_seconds':time.monotonic()-t,'status':'passed' if count==N and bad==0 and expected.digest()==actual.digest() else 'failed'}
out['final_pk_counts']=sql('SELECT COUNT(*),COUNT(DISTINCT id) FROM million_rows');dump(B/'million-load-result.json',out);print('MILLION ORACLE',json.dumps(out['oracle']),flush=True)
