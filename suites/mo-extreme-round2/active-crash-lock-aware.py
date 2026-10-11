import json,time,os,signal,subprocess,fcntl
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
locks=list((server/'data').rglob('LOCK'))+list((server/'data').rglob('TAE.lock'))
lock_errors=[]
for attempt in range(300):
 handles=[]
 try:
  for path in locks:
   fd=os.open(path,os.O_RDWR);handles.append(fd);fcntl.lockf(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  break
 except OSError as e:lock_errors.append({'errno':e.errno,'error':str(e)});time.sleep(.1)
 finally:
  for fd in handles:os.close(fd)
else:raise RuntimeError('lock release timeout')
lock_wait=time.time()-cut
(server/'server.log').rename(p/'server-before-second-active-crash.log')
subprocess.run([str(server/'start.sh')],check=True)
error=None
for i in range(120):
 try:
  c=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database=name,autocommit=True,connect_timeout=3,read_timeout=5)
  with c.cursor() as q:q.execute('SELECT COUNT(*) FROM live_money');assert int(q.fetchone()[0])==1000
  c.close();r={'type':'active_fault','method':'SIGKILL while 32 journaled transaction workers are active','cut_epoch':cut,'old_pid':pid,'new_pid':int((server/'server.pid').read_text()),'ready_epoch':time.time(),'readiness_seconds':time.time()-cut,'lock_release_wait_seconds':lock_wait,'lock_retry_errors':lock_errors,'ready':True};break
 except Exception as e:error=str(e);time.sleep(1)
else:r={'type':'active_fault','cut_epoch':cut,'ready':False,'error':error}
(p/'active-fault-lock-aware.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
if not r['ready']:raise SystemExit(2)
