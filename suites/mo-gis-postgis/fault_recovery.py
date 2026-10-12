"""Kill/restart ONLY owned GIS test servers; audit acknowledged geometry commits."""
import concurrent.futures
import gzip
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from common import P,connect,query,norm,error

DOCKER=['env','-u','DOCKER_HOST','-u','DOCKER_CONTEXT','-u','DOCKER_TLS','-u','DOCKER_TLS_VERIFY','-u','DOCKER_CERT_PATH','docker','--host=unix:///var/run/docker.sock']
RESULTS=[]
for engine in ('mo','pg'):
 print('BEGIN fault',engine,flush=True)
 c=connect(engine,30);query(c,'create table crash_ledger(id bigint primary key,v int,g geometry not null)')
 query(c,'create spatial index crash_geo on crash_ledger(g)' if engine=='mo' else 'create index crash_geo on crash_ledger using gist(g)');c.close()
 ack={};ambiguous=[];lock=threading.Lock();stop=threading.Event()
 def writer(i):
  db=connect(engine,20)
  for n in range(1,10001):
   if stop.is_set():break
   ident=i*100000+n;wkt=f'POINT({i} {n})'
   try:
    query(db,'begin');query(db,'insert into crash_ledger values(%s,%s,st_geomfromtext(%s,0))',(ident,n,wkt));query(db,'commit')
    with lock:ack[ident]=(n,wkt)
   except Exception as e:
    with lock:ambiguous.append({'id':ident,'error':error(e)})
    break
  try:db.close()
  except:pass
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
  fs=[ex.submit(writer,i) for i in range(4)];deadline=time.monotonic()+20
  while len(ack)<100 and time.monotonic()<deadline:time.sleep(.05)
  assert len(ack)>=100,'did not establish acknowledged writes'
  if engine=='mo':
   pid=int((P/'server.pid').read_text());args=Path(f'/proc/{pid}/cmdline').read_bytes()
   assert b'/workspace/mo-gis-postgis/config/launch.toml' in args,'refuse to kill another server'
   before_log=(P/'server.log').read_bytes()
   with gzip.GzipFile(filename=str(P/'server-before-gis-fault.log.gz'),mode='wb',mtime=0) as z:z.write(before_log)
   os.kill(pid,signal.SIGKILL)
  else:subprocess.run(DOCKER+['kill','--signal=KILL','mo-gis-reference-postgis'],check=True,stdout=subprocess.DEVNULL)
  stop.set()
  for f in fs:f.result(timeout=25)
 print('KILLED',engine,'ack',len(ack),'ambiguous',len(ambiguous),flush=True)
 if engine=='mo':subprocess.run(['bash',str(P/'start-mo.sh')],check=True)
 else:subprocess.run(DOCKER+['start','mo-gis-reference-postgis'],check=True,stdout=subprocess.DEVNULL)
 begin=time.monotonic();last=None
 while time.monotonic()-begin<120:
  try:
   c=connect(engine,30);rows=query(c,'select id,v,st_astext(g) from crash_ledger order by id');break
  except Exception as e:last=error(e);time.sleep(1)
 else:raise RuntimeError(last)
 actual={r[0]:(r[1],r[2]) for r in rows};missing=[i for i in ack if i not in actual];corrupt=[i for i in ack if i in actual and actual[i]!=ack[i]]
 assert not missing and not corrupt,(engine,missing,corrupt)
 indexed=query(c,"select count(*) from crash_ledger where st_intersects(g,st_geomfromtext('POLYGON((-1 0,4 0,4 10000,-1 10000,-1 0))',0))")
 assert indexed[0][0]==len(actual),(engine,'recovered spatial index',indexed,len(actual))
 assert query(c,'select count(*) from places')[0][0]==4096
 rec={'engine':engine,'acknowledged':len(ack),'ambiguous':ambiguous,'recovered_rows':len(actual),
      'recovered_unacknowledged_ids':sorted(set(actual)-set(ack)),'missing_acknowledged':missing,'corrupt_acknowledged':corrupt,
      'recovery_query_seconds':time.monotonic()-begin,'spatial_index_count':norm(indexed),'status':'pass'}
 (P/f'{engine}-crash-ack-ledger.json').write_text(json.dumps({str(i):v for i,v in ack.items()},indent=2))
 RESULTS.append(rec);(P/'fault-results.json').write_text(json.dumps(RESULTS,indent=2));print(json.dumps(rec),flush=True);c.close()
