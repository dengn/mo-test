import json,time,requests,pymysql,os,subprocess
from pathlib import Path
B=Path(__file__).parent;ids=json.loads((B/'nifi-ids.json').read_text());API='http://127.0.0.1:10088/nifi-api';out={'profile':'MySQL transactional trigger outbox -> NiFi QueryDatabaseTableRecord(seq checkpoint) -> SplitRecord -> EvaluateJsonPath -> ReplaceText -> PutSQL -> MO; explicit adapter, not generic row-polling CDC','versions':{'NiFi':'2.4.0','JDK':'21'},'cases':[],'semantics':'PK idempotence and monotonic outbox; no exactly-once claim'}
def db(port):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='runtime_ecosystem',autocommit=True)
def rows(port,table,extra=''):
 with db(port) as d,d.cursor() as c:
  c.execute('SELECT id,s,u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc,updated'+extra+' FROM '+table+' ORDER BY id');return [tuple(r[:7])+(json.loads(r[7]) if r[7] is not None else None,)+tuple(r[8:]) for r in c.fetchall()]
def save():(B/'nifi-runtime-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
def wait(name,extra=''):
 start=time.monotonic();last=None
 while time.monotonic()-start<90:
  expected=rows(13306,'nifi_source',extra)
  try:last=rows(6001,'nifi_outbox_target',extra)
  except Exception as e:last=str(e)
  if expected==last:
   r={'name':name,'status':'passed','source':expected,'sink':last};out['cases'].append(r);save();print(name,'PASS',flush=True);return True
  time.sleep(1)
 out['cases'].append({'name':name,'status':'failed','source':expected,'sink':last});save();print(name,'FAIL',str(last)[:1000],flush=True);return False
if not wait('adapted-snapshot-all-wide-fields-and-microseconds'):raise SystemExit(1)
with db(13306) as d,d.cursor() as c:
 c.execute("UPDATE nifi_source SET name='NiFi 更新 😀',ts='2026-10-11 15:00:00.000001',payload=x'00ff80',updated=20 WHERE id=1")
 c.execute('DELETE FROM nifi_source WHERE id=3')
 c.execute("INSERT INTO nifi_source(id,s,u,d,payload,name,ts,doc,updated) VALUES(7,9007199254740997,18446744073709551615,'0.000000000000000001',x'ff00','NiFi新增','2026-10-11 15:00:00.987654','[]',21)")
wait('trigger-outbox-update-insert-physical-delete')
# Replay exact SQL events: target PK convergence, not proof of exactly-once delivery.
with db(13306) as d,d.cursor() as c:c.execute('INSERT INTO nifi_outbox(sqltext) SELECT sqltext FROM nifi_outbox WHERE seq IN (SELECT z.seq FROM (SELECT seq FROM nifi_outbox ORDER BY seq DESC LIMIT 3) z) ORDER BY seq')
wait('outbox-event-replay-idempotent-target')
id=ids['processors']['QueryDatabaseTableRecord'];out['checkpoint_before_restart']=requests.get(API+'/processors/'+id+'/state').json();save()
subprocess.run([str(B/'nifi-2.4.0/bin/nifi.sh'),'stop'],env=dict(os.environ,JAVA_HOME='/usr/lib/jvm/java-21-openjdk-amd64'),timeout=45,stdout=subprocess.DEVNULL)
with db(13306) as d,d.cursor() as c:
 c.execute("UPDATE nifi_source SET name='NiFi恢复 😀',ts='2026-10-11 16:00:00.654321',updated=22 WHERE id=1")
 c.execute('DELETE FROM nifi_source WHERE id=7')
 c.execute("INSERT INTO nifi_source(id,name,updated) VALUES(8,'NiFi停机新增',23)")
f=(B/'nifi-recovery-console.log').open('ab');p=subprocess.Popen([str(B/'nifi-2.4.0/bin/nifi.sh'),'run'],cwd=B/'nifi-2.4.0',env=dict(os.environ,JAVA_HOME='/usr/lib/jvm/java-21-openjdk-amd64'),stdout=f,stderr=subprocess.STDOUT,start_new_session=True);(B/'nifi.pid').write_text(str(p.pid))
wait('nifi-process-restart-persistent-queue-and-checkpoint-catchup')
try:out['checkpoint_after_restart']=requests.get(API+'/processors/'+id+'/state',timeout=10).json()
except Exception as e:out['checkpoint_after_restart_error']=str(e)
with db(6001) as d,d.cursor() as c:c.execute('SELECT COUNT(*),COUNT(DISTINCT id) FROM nifi_outbox_target');out['dedup_control']=c.fetchone()
save()
