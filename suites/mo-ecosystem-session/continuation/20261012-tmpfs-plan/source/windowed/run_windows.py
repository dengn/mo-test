"""Execute real native writers in archived, fully audited owned table windows."""
import driver_routes
from heavy import *
from recycle_profile import register,archive_profile
import argparse
P=argparse.ArgumentParser();P.add_argument('--route',required=True,choices=ROUTES+['pandas','sqlalchemy','pymysql','mysql_connector']);P.add_argument('--workers',type=int,default=2);a=P.parse_args()
assert DS=='mo_ecosystem_heavy_20261012';verify_ownership()
approval=Path(__file__).parents[1]/'table-reuse-approval.json';assert json.loads(approval.read_text())['approved'] is True
out=B/'core-results';out.mkdir(exist_ok=True);path=out/(a.route+'.jsonl');done={}
if path.exists():
 for line in path.read_text().splitlines():
  r=json.loads(line);assert r['id'] not in done;done[r['id']]=r
counts=collections.Counter(r['status'] for r in done.values());started=time.monotonic();audits=[];readpressure=[]
print('WINDOW_START',a.route,len(done),dict(counts),flush=True)
for pi,p in enumerate(PROFILES):
 specs=[(sc,seed,role,caseid(pi,si,seed)) for si,sc in enumerate(SCENARIOS) for seed in range(10) for role in [6001,13306] if f'{a.route}_{p["name"]}_{sc}_{seed}_{role}' not in done]
 if not specs:continue
 try:guard()
 except RuntimeError as e:
  dump(out/(a.route+'-completion.json'),{'route':a.route,'completed':len(done),'planned':5000,'counts':dict(counts),'status':'paused_capacity','reason':str(e)});raise SystemExit(75)
 for role in [6001,13306]:
  for table in tables(a.route,p):
   sql('CREATE TABLE IF NOT EXISTS '+table+'(case_id BIGINT,id BIGINT,v '+p['ddl']+',label VARCHAR(8192),rev BIGINT,PRIMARY KEY(case_id,id))',port=role)
   register(role,table,a.route,p['name'])
  evo='e_'+a.route.split('_')[0]+'_'+p['name'];sql('CREATE TABLE IF NOT EXISTS '+evo+'(case_id BIGINT,id BIGINT,v '+p['ddl']+',label VARCHAR(8192),rev BIGINT,PRIMARY KEY(case_id,id))',port=role);register(role,evo,a.route,p['name'])
 active_rows=[];phase_capacity=False
 # Submit at most a small batch; stop before any unexecuted case is counted.
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
  for start in range(0,len(specs),a.workers*2):
   try:guard()
   except RuntimeError:phase_capacity=True;break
   jobs=[pool.submit(run_case,a.route,p,sc,seed,role,cid) for sc,seed,role,cid in specs[start:start+a.workers*2]]
   for fut in concurrent.futures.as_completed(jobs):
    r=fut.result()
    if r.get('phase')=='initial' and 'test resource guard:' in r.get('error',''):phase_capacity=True;continue
    assert r['id'] not in done;r['database']=DS;r['window_profile']=p['name']
    if a.route in ['sqlalchemy','pymysql','mysql_connector'] and r['scenario']=='native_transform':r['transform_scope']='Python fixture transform then actual native driver write; not an ETL transform engine'
    with path.open('a') as f:f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
    done[r['id']]=r;active_rows.append(r);counts[r['status']]+=1
    if r['status']!='passed':print('FAIL',r['id'],r.get('error','')[:200],flush=True)
    if len(done)%50==0:print('WINDOW_PROGRESS',a.route,len(done),dict(counts),'free',shutil.disk_usage(B).free,flush=True)
   # Real concurrent-window sanity query through DBAPI (after load batch).
   table=tables(a.route,p)[0]
   q=sql("SELECT COUNT(*),COUNT(DISTINCT CONCAT(CAST(case_id AS CHAR),':',CAST(id AS CHAR))),SUM(CASE WHEN rev<0 OR id<0 THEN 1 ELSE 0 END) FROM "+table,port=6001)[0]
   assert q[0]==q[1] and not q[2];readpressure.append({'profile':p['name'],'rows':q[0],'unique_rows':q[1]})
   if phase_capacity:break
 # Fresh full-row readback uses each already-recorded immutable case oracle.
 case_audits=[]
 for r in active_rows:
  rs=sql('SELECT case_id,id,v,label,rev FROM '+tables(a.route,p)[0]+' WHERE case_id=%s ORDER BY id',(r['logical_case_id'],),port=r['port'])
  digest=sha(canon(rs,p));ok=r.get('expected_sha256')==digest and r.get('expected_rows')==len(rs)
  case_audits.append({'id':r['id'],'recorded_status':r['status'],'status':'passed' if ok else 'failed_effect_preserved' if r['status']!='passed' else 'readback_failed','rows':len(rs),'sha256':digest})
 audit={'route':a.route,'profile':p['name'],'cases':case_audits,'counts':dict(collections.Counter(x['status'] for x in case_audits))}
 dump(out/(a.route+'-'+p['name']+'-readback.json'),audit);audits.append(audit)
 assert not any(x['status']=='readback_failed' for x in case_audits),'Post-case data changed; archive but retain tables for diagnosis'
 receipt=archive_profile(a.route,p['name'],apply=True)
 # Every archived window points to the actual new case IDs, including failures.
 receipt['case_ids']=[r['id'] for r in active_rows];dump(Path(receipt['archive']).with_suffix('.receipt.json'),receipt)
 files=[]
 for f in (B/'files').glob(a.route+'_'+p['name']+'_*'):
  keep=bool(re.search(r'_0_(6001|13306)',f.name));files.append({'path':f.name,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'retained':keep})
  if not keep:f.unlink()
 with (out/'file-manifest.jsonl').open('a') as f:
  for r in files:f.write(json.dumps(r)+'\n')
 dump(out/(a.route+'-progress.json'),{'route':a.route,'completed':len(done),'planned':5000,'counts':dict(counts),'elapsed_s':time.monotonic()-started,'free_bytes':shutil.disk_usage(B).free,'archived_profile':p['name']})
 print('WINDOW_ARCHIVED',a.route,p['name'],'tables',len(receipt['tables']),'archivebytes',receipt['bytes'],'free',shutil.disk_usage(B).free,flush=True)
 if phase_capacity:
  # Preserve partial profile receipts; a future run can skip completed IDs.
  dump(out/(a.route+'-completion.json'),{'route':a.route,'completed':len(done),'planned':5000,'counts':dict(counts),'status':'paused_capacity_after_archived_partial_window'});raise SystemExit(75)
summary={'route':a.route,'completed':len(done),'planned':5000,'counts':dict(counts),'status':'complete' if len(done)==5000 else 'incomplete','elapsed_s':time.monotonic()-started,
 'scope':'Native writer API, declared type bindings, explicit effects/schema/recovery adapters; archived windows with fresh full-value oracles; not native exactly-once',
 'new_schema':DS,'old_schema_data_retained':True,'window_count':len(audits)}
dump(out/(a.route+'-completion.json'),summary);dump(out/(a.route+'-window-audit.json'),{'windows':audits,'post_batch_sanity_queries':readpressure})
print('WINDOW_FINAL',json.dumps(summary,ensure_ascii=False),flush=True)
if any(k!='passed' for k in counts):raise SystemExit(1)
