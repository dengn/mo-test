import pathlib,json,zipfile,hashlib,datetime,os,signal,subprocess,time
B=pathlib.Path(__file__).resolve().parent;first=B.parent/'etl-10000';zip_path=B/'evidence-20000.zip';inventory=[]
with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for root in [first,B]:
  for p in sorted(root.rglob('*')):
   if not p.is_file() or any(c in p.parts for c in ['venv','fivetran-venv','dbt-venv','sdk-cache','apache-dolphinscheduler-3.4.2-bin','airflow-home','files']):continue
   if p.suffix not in ['.json','.jsonl','.py','.txt','.yml','.sql','.log']:continue
   if p.name in ['dolphin-sql-runtime-ids.json','dolphin-sql-api-receipts.json','publication-metadata.json'] or p.name.endswith('.tmp') or 'archive' in p.name:continue
   if p.name in ['mo.log']:continue
   archive_name=str(p.relative_to(B.parent));z.write(p,archive_name);inventory.append({'path':archive_name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 z.writestr('archive-inventory.json',json.dumps(inventory,indent=2))
(B/'archive-receipt.json').write_text(json.dumps({'path':str(zip_path),'bytes':zip_path.stat().st_size,'sha256':hashlib.sha256(zip_path.read_bytes()).hexdigest(),'entries':len(inventory),'scope':'Original fixture plans,complete case receipts,source/adapters,compiled dbtSQL/configs,official connector protocols and relevant logs. Runtime images/venvs/tester/data files remain in workspace. Synthetic local passwords only; active session-token files excluded.'},indent=2))
receipts=[]
for name,pfile,marker in [('airflow',B/'airflow.pid',b'airflow\x00standalone'),('dolphin',B/'dolphin.pid',b'standalone-server/bin/start.sh'),('mo',first/'mo.pid',b'/workspace/matrixone/mo-service')]:
 pid=int(pfile.read_text());proc=pathlib.Path('/proc',str(pid));cmd=(proc/'cmdline').read_bytes();assert marker in cmd,(name,pid,cmd[:150]);pgid=os.getpgid(pid);r={'service':name,'pid':pid,'signal':'SIGTERM','UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 if name in ['airflow','dolphin']:assert pgid==pid;os.killpg(pid,signal.SIGTERM)
 else:os.kill(pid,signal.SIGTERM)
 receipts.append(r)
end=time.monotonic()+30
while time.monotonic()<end:
 alive=[]
 for r in receipts:
  p=pathlib.Path('/proc',str(r['pid']))
  if p.exists():
   try:state=(p/'stat').read_text().split()[2]
   except FileNotFoundError:continue
   if state!='Z':alive.append(r['service'])
 if not alive:break
 time.sleep(.5)
for r in receipts:
 p=pathlib.Path('/proc',str(r['pid']))
 try:r['final_state']=(p/'stat').read_text().split()[2]
 except FileNotFoundError:r['final_state']='gone'
(B/'shutdown-receipt.json').write_text(json.dumps({'services':receipts,'left_running':alive,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2));print('ARCHIVE',zip_path.stat().st_size,'SHUTDOWN',receipts,flush=True)
if alive:raise RuntimeError('owned services still running:'+str(alive))
D=['env','-u','DOCKER_HOST','-u','DOCKER_CONTEXT','-u','DOCKER_TLS','-u','DOCKER_TLS_VERIFY','-u','DOCKER_CERT_PATH','docker','--host=unix:///var/run/docker.sock']
r=subprocess.run(D+['stop','--time','10','mo-minio-local','mo-types-mysql'],capture_output=True,text=True,timeout=40);(B/'docker-shutdown-receipt.json').write_text(json.dumps({'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'containers':['mo-minio-local','mo-types-mysql'],'scope':'These two originally exited and were started for this synthetic test; data volumes retained'},indent=2));print('DOCKER STOP',r.returncode,r.stdout,flush=True)
