import json,time,traceback,subprocess
from pathlib import Path
import requests,pymysql
base='http://127.0.0.1:18081'
jid=requests.get(base+'/jobs/overview',timeout=5).json()['jobs'][0]['jid']
out={'flink':'1.20.2','mysql_cdc':'3.6.0-1.20','mysql_source':'8.4.11','jdbc':'3.3.0-1.20','mysql_connector_j':'8.4.0','matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','job_id':jid,'cases':[],'delivery_semantics':'JDBC at-least-once, primary-key upsert convergence; not an end-to-end exactly-once proof'}
pg=pymysql.connect(host='127.0.0.1',port=13306,user='root',password='etl-local',database='etl_source',autocommit=False)
mo=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True)

def norm(rows):return [[str(v) if v is not None else None for v in row] for row in rows]
def rows():
 with mo.cursor() as c:c.execute('SELECT * FROM etl_mysql_cdc.accounts ORDER BY id');return norm(c.fetchall())
def checkpoint():return requests.get(base+'/jobs/'+jid+'/checkpoints',timeout=5).json()
def wait_rows(name,expected):
 deadline=time.monotonic()+60
 while True:
  actual=rows()
  if actual==expected:break
  state=requests.get(base+'/jobs/'+jid,timeout=5).json().get('state')
  if state in ['FAILED','CANCELED']:raise RuntimeError('Flink job '+state+': '+requests.get(base+'/jobs/'+jid+'/exceptions').text[:1200])
  if time.monotonic()>deadline:raise TimeoutError((name,actual,expected))
  time.sleep(1)
 out['cases'].append({'name':name,'status':'passed','expected':expected,'actual':actual});print(name,'passed',flush=True)
def wait_checkpoint(after=0):
 deadline=time.monotonic()+60
 while True:
  p=checkpoint()
  if p.get('counts',{}).get('completed',0)>after:return p
  if time.monotonic()>deadline:raise TimeoutError('No completed checkpoint after '+str(after))
  time.sleep(1)
try:
 initial=[['1','Alice','12.34','2026-10-10 10:00:00.123000'],['2','中文','56.78','2026-10-10 11:00:00.456000']]
 wait_rows('mysql-initial-snapshot-to-mo',initial)
 p=wait_checkpoint();out['initial_checkpoint']=p['latest']['completed']
 with pg.cursor() as c:
  c.execute("UPDATE accounts SET name='更新 中文',amount=99.99,updated_at='2026-10-10 12:00:00.123' WHERE id=1")
  c.execute('DELETE FROM accounts WHERE id=2')
  c.execute('INSERT INTO accounts VALUES(3,NULL,NULL,NULL)')
 pg.commit()
 expected=[['1','更新 中文','99.99','2026-10-10 12:00:00.123000'],['3',None,None,None]]
 wait_rows('mysql-committed-insert-update-delete-to-mo',expected)
 p=wait_checkpoint(p['counts']['completed']);out['before_restart_checkpoint']=p['latest']['completed']
 subprocess.run(['docker','stop','mo-etl-flink-tm'],check=True,stdout=subprocess.DEVNULL)
 try:
  with pg.cursor() as c:
   c.execute('UPDATE accounts SET amount=100.01 WHERE id=1')
   c.execute("INSERT INTO accounts VALUES(4,'恢复 😀',0.01,'2026-10-10 13:00:00.789')")
  pg.commit()
 finally:subprocess.run(['docker','start','mo-etl-flink-tm'],check=True,stdout=subprocess.DEVNULL)
 expected=[['1','更新 中文','100.01','2026-10-10 12:00:00.123000'],['3',None,None,None],['4','恢复 😀','0.01','2026-10-10 13:00:00.789000']]
 wait_rows('taskmanager-restart-and-binlog-catchup',expected)
 p=checkpoint();out['restored_checkpoint']=p.get('latest',{}).get('restored');assert p.get('counts',{}).get('restored',0)>0,p
 out['cases'].append({'name':'flink-checkpoint-restored','status':'passed','restored':out['restored_checkpoint']})
 with pg.cursor() as c:
  c.execute('DELETE FROM accounts WHERE id=3')
  c.execute("UPDATE accounts SET name='二次更新',amount=-1.23 WHERE id=4")
 pg.commit()
 expected=[expected[0],['4','二次更新','-1.23','2026-10-10 13:00:00.789000']]
 wait_rows('cdc-continues-after-recovery',expected)
 with pg.cursor() as c:c.execute("UPDATE accounts SET name='rolledback' WHERE id=1")
 pg.rollback()
 old=checkpoint().get('counts',{}).get('completed',0);out['final_checkpoints']=wait_checkpoint(old)
 wait_rows('mysql-rollback-not-published',expected)
 out['status']='passed'
except Exception as e:out.update(status='failed',error=str(e));traceback.print_exc()
finally:
 pg.close();mo.close();Path('/workspace/work/etl-expanded/mysql-cdc-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str));print(json.dumps(out,ensure_ascii=False,indent=2,default=str))
if out['status']!='passed':raise SystemExit(1)
