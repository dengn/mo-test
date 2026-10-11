import json,os,signal,time,subprocess,pymysql,hashlib
from pathlib import Path
p=Path('/workspace/mo-stress')
def connect():return pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='mo_stress',autocommit=True,connect_timeout=3,read_timeout=120)
def snapshot():
 c=connect();r={}
 with c.cursor() as q:
  for name,query in [('items','SELECT COUNT(*),SUM(id),SUM(value),SUM(length(payload)) FROM items'),('accounts','SELECT COUNT(*),SUM(balance) FROM accounts'),('events','SELECT COUNT(*),COUNT(DISTINCT id),COALESCE(MAX(id),0) FROM events')]:
   q.execute(query);r[name]=list(map(int,q.fetchone()))
  q.execute("SELECT COUNT(*) FROM items WHERE payload<>repeat(md5(cast(id AS varchar)),32)");r['bad_payload_rows']=int(q.fetchone()[0])
  q.execute('SELECT COUNT(*) FROM items WHERE value<>id%100000 OR grp<>id%1000');r['bad_value_rows']=int(q.fetchone()[0])
  for table,query in [('accounts','SELECT id,balance FROM accounts ORDER BY id'),('events','SELECT id,grp,payload FROM events ORDER BY id')]:
   q.execute(query);h=hashlib.sha256()
   for row in q:h.update((json.dumps(row,separators=(',',':'))+'\n').encode())
   r[table+'_sha256']=h.hexdigest()
 c.close();return r
before=snapshot();(p/'pre-crash.json').write_text(json.dumps(before,indent=2))
pid=int((p/'server.pid').read_text());cmd=Path(f'/proc/{pid}/comm').read_text().strip();assert cmd=='mo-service',cmd
start=time.time();os.kill(pid,signal.SIGKILL)
for i in range(100):
 try:
  if Path(f'/proc/{pid}/stat').read_text().split()[2]=='Z':break
 except FileNotFoundError:break
 time.sleep(.1)
else:raise RuntimeError('target process did not stop')
(p/'server.log').rename(p/'server-load.log')
subprocess.run([str(p/'start.sh')],check=True)
last=None
for i in range(120):
 try:
  c=connect()
  with c.cursor() as q:q.execute('SELECT 1');assert q.fetchone()==(1,)
  c.close();ready=time.time()-start;break
 except Exception as e:last=str(e);time.sleep(1)
else:raise RuntimeError(f'recovery readiness timeout: {last}')
after=snapshot();good=before==after and after['bad_payload_rows']==0 and after['bad_value_rows']==0 and after['items']==[2000000,2000001000000,99999000000,2048000000] and after['accounts']==[10000,1000000000]
r={'method':'SIGKILL of own isolated mo-service, restart with same data directory','readiness_seconds':ready,'verification_total_seconds':time.time()-start,'before':before,'after':after,'pass':good}
(p/'crash-recovery.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
if not good:raise SystemExit(2)
