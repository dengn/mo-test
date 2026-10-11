import json,time,os,signal,subprocess,fcntl
from pathlib import Path
import pymysql
p=Path('/workspace/mo-vector-fulltext');server=Path('/workspace/mo-stress');name=(p/'database.txt').read_text().strip()
# Ensure acknowledged index-bearing transactions exist and writers remain active.
start=time.monotonic()
initial_n=sum(1 for _ in open(p/'acknowledged.jsonl')) if (p/'acknowledged.jsonl').exists() else 0
while True:
    n=sum(1 for _ in open(p/'acknowledged.jsonl')) if (p/'acknowledged.jsonl').exists() else 0
    if n>=initial_n+500 and time.monotonic()-start>=25:break
    if time.monotonic()-start>50:raise RuntimeError('fault aborted: insufficient acknowledged writes')
    time.sleep(1)
client=int((p/'load.pid').read_text());assert Path(f'/proc/{client}/stat').read_text().split()[2]!='Z'
pid=int((server/'server.pid').read_text());assert Path(f'/proc/{pid}/comm').read_text().strip()=='mo-service'
cut=time.time();os.kill(pid,signal.SIGKILL)
for i in range(100):
    try:
        if Path(f'/proc/{pid}/stat').read_text().split()[2]=='Z':break
    except FileNotFoundError:break
    time.sleep(.1)
else:raise RuntimeError('server did not stop')
locks=list((server/'data').rglob('LOCK'))+list((server/'data').rglob('TAE.lock'));lock_errors=[]
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
(server/'server.log').rename(p/'server-before-crash.log')
subprocess.run([str(server/'start.sh')],check=True)
error=None
for i in range(120):
    try:
        c=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database=name,autocommit=True,connect_timeout=3,read_timeout=5)
        with c.cursor() as q:q.execute('select count(*) from ackledger');assert int(q.fetchone()[0])>=n
        c.close();r={'method':'SIGKILL during 16 cross-index transaction writers and 16 vector/fulltext readers','cut_epoch':cut,'old_pid':pid,'new_pid':int((server/'server.pid').read_text()),'acknowledged_at_cut':n,'ready_epoch':time.time(),'readiness_seconds':time.time()-cut,'lock_wait_seconds':lock_wait,'lock_errors':lock_errors,'ready':True};break
    except Exception as e:error=str(e);time.sleep(1)
else:r={'cut_epoch':cut,'ready':False,'error':error}
(p/'crash-recovery.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
if not r['ready']:raise SystemExit(2)
