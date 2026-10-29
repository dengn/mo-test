"""Bounded native-component continuation; capacity stops do not count as cases."""
import driver_routes
from heavy import *
import argparse

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--route',required=True,choices=ROUTES+['pandas','sqlalchemy','pymysql','mysql_connector'])
 parser.add_argument('--workers',type=int,default=2)
 args=parser.parse_args();route=args.route
 if not 1<=args.workers<=8:parser.error('workers must be1..8')
 out=B/'core-results';out.mkdir(exist_ok=True)
 path=out/(route+'.jsonl');done={}
 if path.exists():
  for line in path.read_text().splitlines():
   row=json.loads(line);assert row['id'] not in done;done[row['id']]=row
 counts=collections.Counter(r['status'] for r in done.values())
 print('RESUME',route,len(done),dict(counts),flush=True)
 start=time.monotonic();capacity=None;active=[];stop=threading.Event();readstats={'queries':0,'errors':[],'latencies_ms':[]}
 def reader():
  while not stop.is_set():
   if active:
    t0=time.monotonic();table=active[-1]
    try:
     row=sql("SELECT COUNT(*),COUNT(DISTINCT CONCAT(CAST(case_id AS CHAR),':',CAST(id AS CHAR))),SUM(CASE WHEN rev<0 OR id<0 THEN 1 ELSE 0 END) FROM "+table,port=6001)[0]
     assert row[0]==row[1] and not row[2],row
     readstats['queries']+=1;readstats['latencies_ms'].append((time.monotonic()-t0)*1000)
    except Exception as e:readstats['errors'].append({'table':table,'error':repr(e)})
   stop.wait(.5)
 thread=threading.Thread(target=reader,daemon=True);thread.start()
 try:
  engine(6001);engine(13306)
  with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
   for pi,p in enumerate(PROFILES):
    specs=[(sc,seed,port,caseid(pi,si,seed)) for si,sc in enumerate(SCENARIOS) for seed in range(10) for port in [6001,13306]
           if f'{route}_{p["name"]}_{sc}_{seed}_{port}' not in done]
    if not specs:continue
    try:guard()
    except RuntimeError as e:capacity=str(e);break
    for port in [6001,13306]:create(route,p,port)
    active.append(tables(route,p)[0]);iterator=iter(specs);futures={};exhausted=False
    while futures or not exhausted:
     while not exhausted and capacity is None and len(futures)<args.workers*2:
      try:guard()
      except RuntimeError as e:capacity=str(e);exhausted=True;break
      try:sc,seed,port,cid=next(iterator)
      except StopIteration:exhausted=True;break
      fut=pool.submit(run_case,route,p,sc,seed,port,cid);futures[fut]=(sc,seed,port,cid)
     if not futures:break
     ready,_=concurrent.futures.wait(futures,return_when=concurrent.futures.FIRST_COMPLETED)
     for fut in ready:
      spec=futures.pop(fut);row=fut.result()
      if row.get('phase')=='initial' and 'test resource guard:' in row.get('error',''):
       capacity=row['error'];exhausted=True;continue
      assert row['id'] not in done
      with path.open('a') as f:f.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')
      done[row['id']]=row;counts[row['status']]+=1
      if row['status']!='passed':print('FAIL',row['id'],row.get('error','')[:160],flush=True)
      if len(done)%50==0:
       state={'route':route,'completed':len(done),'planned':5000,'counts':dict(counts),'elapsed_s':time.monotonic()-start,'resources':resources(),'reader_queries':readstats['queries'],'reader_errors':len(readstats['errors'])}
       dump(out/(route+'-progress.json'),state);print('PROGRESS',route,len(done),dict(counts),'disk',state['resources']['disk_free'],flush=True)
    if capacity is not None:break
    # Files of other rounds/routes are never removed. Preserve representative
    # seed0 files and record hashes before removing this run's generated extras.
    receipts=[]
    for f in (B/'files').glob(route+'_'+p['name']+'_*'):
     record={'name':f.name,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'retained':bool(re.search(r'_0_(6001|13306)',f.name))}
     receipts.append(record)
     if not record['retained']:f.unlink()
    with (out/'file-manifest.jsonl').open('a') as f:
     for record in receipts:f.write(json.dumps(record)+'\n')
 finally:
  stop.set();thread.join(timeout=10)
  dump(out/(route+'-resume-read-pressure.json'),dict(readstats,latency=stats(readstats['latencies_ms']),scope='Concurrent uniqueness/nonnegative revision aggregate sanity; not arbitrary snapshot certification'))
 summary={'route':route,'completed':len(done),'planned':5000,'counts':dict(counts),'status':'paused_capacity' if capacity else 'complete' if len(done)==5000 else 'incomplete',
          'capacity_reason':capacity,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'case_scope':'Real native component loads plus explicitly labelled effects/schema adapters; not native connector EOS',
          'ownership_scope':'Existing current heavy5000 route tables; only unfinished own case IDs reset; completed effect rows and prior-round databases retained'}
 dump(out/(route+'-completion.json'),summary)
 print('FINAL',json.dumps(summary,ensure_ascii=False),flush=True)
 if capacity:raise SystemExit(75)
 if counts.get('execution_failed') or counts.get('fidelity_failed'):raise SystemExit(1)
if __name__=='__main__':main()
