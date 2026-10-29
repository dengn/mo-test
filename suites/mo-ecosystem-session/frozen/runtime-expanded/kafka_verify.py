import json,time,os,signal,subprocess,requests,pymysql
from pathlib import Path
B=Path(__file__).parent;out={'runtime_ref':'652c643666428f1c434e03369834f2a9bead7c27','tools':{'Kafka':'3.9.1','DebeziumSource':'3.1.2.Final','DebeziumJDBCSink':'3.1.2.Final'},'semantics':'at-least-once source/sink with idempotent PK upsert; not exactly-once certification','cases':[]}
def db(port):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='runtime_ecosystem',autocommit=True)
def rows(port,table,extra=''):
 with db(port) as d,d.cursor() as c:
  c.execute('SELECT id,s,u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc,updated'+extra+' FROM '+table+' ORDER BY id')
  return [tuple(r[:7])+(json.loads(r[7]) if r[7] is not None else None,)+tuple(r[8:]) for r in c.fetchall()]
def wait(name,extra=''):
 start=time.monotonic();last=None
 while time.monotonic()-start<90:
  expected=rows(13306,'records',extra)
  try:last=rows(6001,'kc_exact_records',extra)
  except pymysql.MySQLError as e:last=str(e)
  if last==expected:
   r={'name':name,'status':'passed','source':expected,'sink':last,'elapsed_s':round(time.monotonic()-start,3)};out['cases'].append(r);print(name,'PASS',flush=True);save();return
  time.sleep(1)
 r={'name':name,'status':'failed','source':expected,'sink':last,'connector_status':{n:requests.get('http://127.0.0.1:18083/connectors/'+n+'/status').json() for n in ['mo-exact-source','mo-exact-sink']}};out['cases'].append(r);save();print(name,'FAIL',str(r)[:1200],flush=True)
def save():(B/'kafka-runtime-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
wait('snapshot-wide-types-and-microseconds')
with db(13306) as d,d.cursor() as c:
 c.execute("UPDATE records SET name='更新 😀',ts='2026-10-11 13:01:02.987654',payload=x'ff000180',updated=4 WHERE id=1")
 c.execute('DELETE FROM records WHERE id=2')
 c.execute("INSERT INTO records(id,s,u,d,payload,name,ts,doc,updated) VALUES(4,9007199254740995,18446744073709551614,'0.123456789012345678',x'00ff','新增','2026-10-11 13:00:00.000001','{}',5)")
wait('insert-update-and-physical-delete')
with db(13306) as d,d.cursor() as c:
 c.execute('ALTER TABLE records ADD COLUMN added_tag VARCHAR(100) NULL')
 c.execute("UPDATE records SET added_tag='新列 中文',updated=6 WHERE id=1")
wait('nullable-column-auto-evolution',',added_tag')
pid=int((B/'connect.pid').read_text());os.kill(pid,signal.SIGTERM)
for _ in range(30):
 try:os.kill(pid,0)
 except ProcessLookupError:break
 time.sleep(0.2)
with db(13306) as d,d.cursor() as c:
 c.execute("UPDATE records SET name='恢复之后 😀',ts='2026-10-11 14:00:00.654321',updated=7 WHERE id=1")
 c.execute('DELETE FROM records WHERE id=4')
 c.execute("INSERT INTO records(id,name,updated,added_tag) VALUES(5,'离线时新增',8,'恢复')")
f=(B/'connect-recovery.log').open('ab');p=subprocess.Popen([str(B/'kafka_2.13-3.9.1/bin/connect-distributed.sh'),str(B/'connect.properties')],stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,KAFKA_HEAP_OPTS='-Xms128m -Xmx512m'),start_new_session=True);(B/'connect.pid').write_text(str(p.pid))
wait('worker-restart-binlog-catchup-no-duplicate',',added_tag')
with db(6001) as d,d.cursor() as c:
 c.execute('SELECT COUNT(*),COUNT(DISTINCT id) FROM kc_exact_records');out['dedup_control']=c.fetchone()
save()
