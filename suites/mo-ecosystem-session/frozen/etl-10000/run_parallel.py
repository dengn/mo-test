from matrix import *
path=B/'results.jsonl';finished={}
for line in path.read_text().splitlines() if path.exists() else []:
 r=json.loads(line);assert r['id'] not in finished,'duplicate base receipt';finished[r['id']]=r
counts=collections.Counter(r['status'] for r in finished.values());start=time.monotonic()
for port in [6001,13306]:engine(port)
for ri,route in enumerate(ROUTES):
 for pi,p in enumerate(PROFILES):
  for port in [6001,13306]:create(route,p,port)
  jobs=[]
  for si,sc in enumerate(SCENARIOS):
   for seed in range(10):
    for port in [6001,13306]:
     key=f'{route}_{p["name"]}_{sc}_{seed}_{port}'
     if key not in finished:jobs.append((route,p,sc,seed,port,caseid(ri,pi,si,seed)))
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
   fs=[ex.submit(run_case,*job,cleanup=True) for job in jobs]
   for f in concurrent.futures.as_completed(fs):
    r=f.result()
    with path.open('a') as out:out.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
    finished[r['id']]=r;counts[r['status']]+=1
    if len(finished)%50==0:
     dump(B/'progress.json',{'planned':10000,'completed':len(finished),'counts':dict(counts),'last':r['id'],'parallel_case_workers':4,'resumed_elapsed_s':time.monotonic()-start,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'resources':resources()});print('PROGRESS',len(finished),dict(counts),r['id'],flush=True)
dump(B/'completion.json',{'completed':len(finished),'counts':dict(counts),'finished_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'parallel_case_workers':4,'continuation_note':'serial runner explicitly paused; pending cases remove only own case_id rows before retry; original completed receipts retained'})
