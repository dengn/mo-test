import json,time,os,signal,subprocess
from pathlib import Path
import pymysql
p=Path('/workspace/mo-extreme-round2');server=Path('/workspace/mo-stress');name=(p/'database.txt').read_text().strip()
pid=int((server/'server.pid').read_text());assert Path(f'/proc/{pid}/comm').read_text().strip()=='mo-service'
cut=time.time();os.kill(pid,signal.SIGKILL)
for i in range(100):
 try:
  if Path(f'/proc/{pid}/stat').read_text().split()[2]=='Z':break
 except FileNotFoundError:break
 time.sleep(.1)
else:raise RuntimeError('server did not stop')
(server/'server.log').rename(p/'server-before-active-crash.log')
subprocess.run([str(server/'start.sh')],check=True)
error=None
for i in range(120):
 try:
  c=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database=name,autocommit=True,connect_timeout=3,read_timeout=5)
  with c.cursor() as q:q.execute('SELECT COUNT(*) FROM live_money');assert int(q.fetchone()[0])==1000
  c.close();r={'type':'active_fault','method':'SIGKILL while 32 journaled transaction workers are active','cut_epoch':cut,'old_pid':pid,'new_pid':int((server/'server.pid').read_text()),'ready_epoch':time.time(),'readiness_seconds':time.time()-cut,'ready':True};break
 except Exception as e:error=str(e);time.sleep(1)
else:r={'type':'active_fault','cut_epoch':cut,'ready':False,'error':error}
(p/'active-fault.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
if not r['ready']:raise SystemExit(2)
