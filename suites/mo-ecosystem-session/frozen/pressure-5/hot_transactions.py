from runtime import *
import concurrent.futures,collections,random
CONFLICTS={20619,20628,20631,20701,20702,1213,1205};out={'runtime_ref':REF,'scope':'8-account contention, each transfer and unique ledger event in one MO transaction. Retry only explicitly recognized transaction aborts; no ambiguous commit replay. Post-run balances reconstructed from durable ledger. Client latency includes retries.','stages':[]}
sql('CREATE TABLE accounts(id INT PRIMARY KEY,balance BIGINT)');sql('CREATE TABLE transfer_ledger(event_id BIGINT PRIMARY KEY,a INT,b INT)')
def stage(workers,duration=45):
 sql('TRUNCATE TABLE accounts');sql('TRUNCATE TABLE transfer_ledger')
 with db() as d,d.cursor() as c:c.executemany('INSERT INTO accounts VALUES(%s,100000)',[(i,) for i in range(8)])
 gate=threading.Barrier(workers+1);end=[0];alllat=[];commits=[];retries=collections.Counter();errors=[];aborted=[]
 def worker(w):
  n=0;cnt=0;lat=[];rng=random.Random(w)
  try:
   with db(autocommit=False) as d,d.cursor() as c:
    gate.wait()
    while time.monotonic()<end[0]:
     a=rng.randrange(8);b=(a+1+rng.randrange(7))%8;eid=w*10000000+n;n+=1;t=time.monotonic();retry=0
     while True:
      phase='statement'
      try:
       c.execute('BEGIN');c.execute('UPDATE accounts SET balance=balance+CASE WHEN id=%s THEN -1 ELSE 1 END WHERE id IN (%s,%s)',(a,a,b));c.execute('INSERT INTO transfer_ledger VALUES(%s,%s,%s)',(eid,a,b));phase='commit';d.commit();cnt+=1;lat.append((time.monotonic()-t)*1000);break
      except Exception as e:
       code=e.args[0] if isinstance(e,pymysql.MySQLError) else None
       try:d.rollback()
       except Exception:pass
       if code in CONFLICTS:
        retries[code]+=1;retry+=1
        if retry<10 and time.monotonic()<end[0]:time.sleep(.002*min(retry,5));continue
        aborted.append({'worker':w,'event_id':eid,'retries':retry});break
       errors.append({'worker':w,'phase':phase,'error':str(e),'event_id':eid});return
  except Exception as e:errors.append({'worker':w,'error':str(e)})
  finally:commits.append(cnt);alllat.extend(lat)
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  fs=[ex.submit(worker,w) for w in range(workers)];t=time.monotonic();end[0]=t+duration;gate.wait()
  for f in fs:f.result()
 elapsed=time.monotonic()-t;expected=[100000]*8;ledgers=sql('SELECT event_id,a,b FROM transfer_ledger');actual=sql('SELECT id,balance FROM accounts ORDER BY id')
 for eid,a,b in ledgers:expected[a]-=1;expected[b]+=1
 r={'workers':workers,'requested_s':duration,'elapsed_s':elapsed,'acknowledged_commits':sum(commits),'committed_transfers_s':sum(commits)/elapsed,'logical_transaction_latency':stats(alllat),'recognized_conflict_retries':dict(retries),'explicitly_aborted_events':len(aborted),'unexpected_errors':errors,'oracle':{'ledger_rows':len(ledgers),'ack_commits':sum(commits),'actual_balances':actual,'expected_balances':expected,'sum_balance':sum(v for i,v in actual),'status':'passed' if len(ledgers)==sum(commits) and [v for i,v in actual]==expected and sum(v for i,v in actual)==800000 else 'failed'}};out['stages'].append(r);dump(B/'hot-transactions-result.json',out);print('HOT TX',workers,r['committed_transfers_s'],sum(retries.values()),len(errors),r['oracle']['status'],flush=True)
for w in [4,16,32]:stage(w)
