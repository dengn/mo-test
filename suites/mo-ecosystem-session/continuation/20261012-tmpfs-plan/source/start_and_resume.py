"""Approval-gated new native runtime, then one pending core writer at a time."""
from pathlib import Path
import os,sys,json,time,subprocess,signal,socket,pwd
B=Path(__file__).resolve().parent
approval_path=B/'execution-approval.json'
approval=json.loads(approval_path.read_text()) if approval_path.exists() else {'approved':False}
if approval.get('approved') is not True:raise SystemExit('NOT STARTED: scope-change approval absent;64GiB expansion condition still applies')
plan=json.loads((B/'review-plan.json').read_text());R=B/'runtime';assert not R.exists(),'Refuses to overwrite any existing runtime'
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(B),LD_LIBRARY_PATH=str(B/'lib'),MO_TEST_DATABASE=plan['database'],MO_CASE_OUTPUT=str(B/'results'),MO_CASE_MIN_FREE_MIB='2048',MO_CASE_RUNTIME_ID=plan['runtime_id'],MO_PORT='16001',MYSQL_PORT='23306',MO_PASSWORD='<SET_MO_PASSWORD>',MYSQL_PASSWORD='<SET_MYSQL_PASSWORD>')
os.environ.update({k:v for k,v in env.items() if k.startswith(('MO_','MYSQL_'))})
sys.path.insert(0,str(B/'windowed'));import runtime as rt
rt.guard()
ports=[16001,23306,9002,9003,17001,18000,19000,32000,32001]
for port in ports:
 with socket.socket() as sock:sock.bind(('127.0.0.1',port))
R.mkdir();(R/'mysql').mkdir();(R/'minio').mkdir();(R/'certs').mkdir();records=[]
def launch(name,args,extra=None):
 e=dict(env);e.update(extra or {});log=(R/(name+'.log')).open('ab')
 p=subprocess.Popen(args,cwd=R,env=e,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
 records.append({'name':name,'pid':p.pid,'argv':args,'log':str(R/(name+'.log'))});(R/'owned-processes.json').write_text(json.dumps(records,indent=2)+'\n');return p
def waitfn(fn,secs=120):
 until=time.monotonic()+secs;last=None
 while time.monotonic()<until:
  try:
   x=fn()
   if x:return x
  except Exception as e:last=repr(e)
  time.sleep(.5)
 raise RuntimeError('Startup timeout '+str(last))
def connect_mysql(socket_path=False,password=''):
 import pymysql
 kw={'unix_socket':str(R/'mysql.sock')} if socket_path else {'host':'127.0.0.1','port':23306}
 return pymysql.connect(**kw,user='root',password=password,autocommit=True,connect_timeout=3)
owned=[]
try:
 minio=launch('minio',[str(B/'bin/minio'),'server','--address','127.0.0.1:9002','--console-address','127.0.0.1:9003','--certs-dir',str(R/'certs'),str(R/'minio')],{'MINIO_ROOT_USER':'minio','MINIO_ROOT_PASSWORD':'<SET_MINIO_PASSWORD>','GOMEMLIMIT':'256MiB','GOMAXPROCS':'2'});owned.append(minio)
 sys.path.append('/workspace/toolchains/python/lib/python3.12/site-packages');import boto3
 s=boto3.client('s3',endpoint_url='http://127.0.0.1:9002',aws_access_key_id='minio',aws_secret_access_key='<SET_MINIO_PASSWORD>',region_name='us-east-1')
 waitfn(lambda:s.list_buckets());s.create_bucket(Bucket=plan['runtime_id'])
 mysql_common=[str(B/'bin/mysqld'),'--no-defaults','--basedir='+str(B),'--datadir='+str(R/'mysql'),'--lc-messages-dir='+str(B/'share'),'--character-sets-dir='+str(B/'share/charsets'),'--innodb-buffer-pool-size=134217728','--innodb-redo-log-capacity=67108864','--user='+pwd.getpwuid(os.getuid()).pw_name]
 with (R/'mysql-initialize.log').open('ab') as log:subprocess.run(mysql_common+['--initialize-insecure'],cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
 mysql=launch('mysql',mysql_common+['--bind-address=127.0.0.1','--port=23306','--socket='+str(R/'mysql.sock'),'--pid-file='+str(R/'mysql.pid'),'--log-error='+str(R/'mysql-server.log'),'--tmpdir='+str(R),'--mysqlx=OFF','--skip-log-bin','--max-connections=32']);owned.append(mysql)
 def bootstrap_mysql():
  with connect_mysql(True) as d,d.cursor() as c:
   c.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s",('<SET_MYSQL_PASSWORD>',));return True
 waitfn(bootstrap_mysql)
 mo=launch('mo',['/workspace/matrixone/mo-service','-launch',str(B/'config/launch.toml')],{'GOMEMLIMIT':'1536MiB','GOMAXPROCS':'2'});owned.append(mo)
 waitfn(lambda:rt.sql('SELECT 1',database='mo_catalog'),150)
 rt.initialize();rt.guard()
 print('NEW_RUNTIME_READY',plan['runtime_id'],'old data untouched',flush=True)
 for route in [plan['first_route']]+plan['next_core_routes']:
  rt.guard()
  log=R/(route+'-cases.log')
  with log.open('ab') as f:
   command=[sys.executable,str(B/'windowed/run_windows_micro.py'),'--route',route,'--workers','2']
   if route==plan['first_route']:
    pilot=subprocess.run(command+['--max-windows','1'],env=env,cwd=R,stdout=f,stderr=subprocess.STDOUT)
    print('PILOT_EXIT',route,pilot.returncode,flush=True)
    if pilot.returncode!=0:raise SystemExit(pilot.returncode)
    receipt=json.loads((B/'results/core-results'/f'{route}-pilot.json').read_text());assert receipt['new_cases']==20 and receipt['status']=='pilot_window_archived'
    print('PILOT_VERIFIED',json.dumps(receipt),flush=True)
   r=subprocess.run(command,env=env,cwd=R,stdout=f,stderr=subprocess.STDOUT)
  print('ROUTE_EXIT',route,r.returncode,flush=True)
  if r.returncode!=0:raise SystemExit(r.returncode)
finally:
 # Stop only the exact processes created in this launch, with graceful SIGTERM.
 # Persisted temporary runtime files/buckets are retained for inspection.
 for p in reversed(owned):
  if p.poll() is None:p.send_signal(signal.SIGTERM)
 for p in reversed(owned):
  try:p.wait(timeout=30)
  except subprocess.TimeoutExpired:print('PROCESS_STILL_RUNNING',p.pid,'retained for inspection',flush=True)
 (R/'exit-process-states.json').write_text(json.dumps([{'pid':p.pid,'exit_code':p.poll()} for p in owned],indent=2)+'\n')
