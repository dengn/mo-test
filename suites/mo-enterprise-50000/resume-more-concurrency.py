import json,os,signal,time,re
from pathlib import Path
import pymysql
P=Path('/workspace/mo-enterprise-50000');pid=None
for d in Path('/proc').iterdir():
 if not d.name.isdigit():continue
 try:a=d.joinpath('cmdline').read_bytes().split(b'\0')
 except OSError:continue
 if len(a)>1 and a[1]==b'/workspace/mo-enterprise-50000/runner.py':pid=int(d.name);break
if pid is None:raise RuntimeError('No exact test runner process found')
mo_pid=Path('/workspace/mo-stress/server.pid').read_text().strip();os.kill(pid,signal.SIGTERM)
for _ in range(50):
 try:state=Path(f'/proc/{pid}/stat').read_text().split()[2]
 except FileNotFoundError:break
 if state=='Z':break
 time.sleep(.1)
else:raise RuntimeError('Runner did not terminate')
time.sleep(10)
done={r['id'] for r in map(json.loads,(P/'results.jsonl').open())}
c=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='enterprise50',autocommit=True,ssl_disabled=True,read_timeout=30);removed=[]
with c.cursor() as q:
 q.execute("select relname from mo_catalog.mo_tables where reldatabase='enterprise50'");tables=[str(r[0]) for r in q.fetchall()]
targets=[]
for t in tables:
 m=re.fullmatch(r'(gb|gs)([0-9]+)',t)
 if m and f'M{40001+int(m[2]):06d}' not in done:targets.append(t)
for t in sorted(targets,key=lambda n:(0 if n.startswith('gs') else 1,n)):
 for attempt in range(5):
  try:
   with c.cursor() as q:q.execute('drop table if exists '+t)
   removed.append(t);break
  except Exception:
   if attempt==4:raise
   time.sleep(.5)
c.close()
report={'planned_runner_restart':True,'old_runner_pid':pid,'completed_ids_preserved':len(done),'incomplete_case_tables_removed':removed,'old_ddl_workers':4,'new_ddl_workers':12,'mo_pid_before':mo_pid,'mo_pid_after':Path('/workspace/mo-stress/server.pid').read_text().strip(),'original_cases_and_expectations_changed':False}
(P/'concurrency-transition.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
