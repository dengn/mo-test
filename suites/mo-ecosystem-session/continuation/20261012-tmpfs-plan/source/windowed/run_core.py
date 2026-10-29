import driver_routes
from heavy import *
import argparse
P=argparse.ArgumentParser();P.add_argument('--preflight',action='store_true');P.add_argument('--workers',type=int,default=4);P.add_argument('--route',choices=ROUTES+['pandas','sqlalchemy','pymysql','mysql_connector']);P.add_argument('--limit',type=int,default=5000);args=P.parse_args();routes=[args.route] if args.route else ROUTES
if not 1<=args.limit<=5000 or not 1<=args.workers<=32:P.error('limit 1..5000; workers 1..32')
verify_ownership()
outdir=B/'core-results';outdir.mkdir(exist_ok=True);startall=time.monotonic();stop=threading.Event();readstats={'queries':0,'errors':[],'latencies_ms':[]};active=[];lock=threading.Lock()
def reader():
 while not stop.is_set():
  with lock:items=list(active)
  if not items:stop.wait(.2);continue
  for table in items[-2:]:
   if stop.is_set():break
   start=time.monotonic()
   try:
    rs=sql("SELECT COUNT(*),COUNT(DISTINCT CONCAT(CAST(case_id AS CHAR),':',CAST(id AS CHAR))),SUM(CASE WHEN rev<0 OR id<0 THEN 1 ELSE 0 END) FROM "+table,port=6001)[0];assert rs[0]==rs[1] and not rs[2],rs;readstats['queries']+=1;readstats['latencies_ms'].append((time.monotonic()-start)*1000)
   except Exception as e:readstats['errors'].append({'table':table,'error':repr(e)})
  stop.wait(.25)
thread=threading.Thread(target=reader,daemon=True);thread.start()
try:
 for route in routes:
  path=outdir/(route+('-preflight' if args.preflight else '')+'.jsonl');finished={}
  if path.exists():
   for line in path.read_text().splitlines():r=json.loads(line);assert r['id'] not in finished;finished[r['id']]=r
  counts=collections.Counter(r['status'] for r in finished.values());print('START',route,'resumed',len(finished),flush=True)
  engine(6001);engine(13306)
  with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
   for pi,p in enumerate(PROFILES):
    if len(finished)>=args.limit:break
    for port in [6001,13306]:create(route,p,port)
    with lock:active.append(tables(route,p)[0])
    jobs=[]
    scenarios=['append','schema_add','duplicate_rollback_retry','staging_merge'] if args.preflight else SCENARIOS
    for sc in scenarios:
     si=SCENARIOS.index(sc)
     for seed in ([0] if args.preflight else range(10)):
      for port in [6001,13306]:
       key=f'{route}_{p["name"]}_{sc}_{seed}_{port}'
       if len(finished)+len(jobs)<args.limit and key not in finished:jobs.append(pool.submit(run_case,route,p,sc,seed,port,caseid(pi,si,seed)+(100000 if args.preflight else 0)))
    for fut in concurrent.futures.as_completed(jobs):
     r=fut.result()
     with path.open('a') as f:f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
     finished[r['id']]=r;counts[r['status']]+=1
     if r['status']!='passed':print('FAIL',r['id'],r.get('error','')[:150],flush=True)
     if len(finished)%50==0:
      progress={'route':route,'completed':len(finished),'planned':200 if args.preflight else 5000,'counts':dict(counts),'elapsed_s':time.monotonic()-startall,'resources':resources(),'reader_queries':readstats['queries'],'reader_errors':len(readstats['errors'])};dump(outdir/(route+'-progress.json'),progress);print('PROGRESS',route,len(finished),dict(counts),flush=True)
    # Each profile uses bounded files; preserve one representative per scenario and hashes of every generated file.
    folder=B/'files'
    if folder.exists():
     file_receipts=[]
     for f in folder.glob(route+'_'+p['name']+'_*'):
      file_receipts.append({'name':f.name,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'retained':bool(re.search(r'_0_(6001|13306)',f.name))})
      if not file_receipts[-1]['retained']:f.unlink()
     with (outdir/'file-manifest.jsonl').open('a') as f:
      for r in file_receipts:f.write(json.dumps(r)+'\n')
  dump(outdir/(route+'-completion.json'),{'completed':len(finished),'counts':dict(counts),'preflight':args.preflight,'configured_profile':'Explicit bindings/envelopes,aliasSQLeffect adapters; no nativeCDC/EOS automaticclaim','finished_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()})
finally:
 stop.set();thread.join(timeout=10);dump(outdir/'read-pressure.json',{'queries':readstats['queries'],'errors':readstats['errors'],'latency':stats(readstats['latencies_ms']),'scope':'Concurrent whole-table uniqueness/rev sanity,notarbitraryconcurrentfullsnapshotoracle'});print('READPRESSURE',readstats['queries'],'errors',len(readstats['errors']),flush=True)

if any(r['status']!='passed' for r in finished.values()):raise SystemExit(1)
