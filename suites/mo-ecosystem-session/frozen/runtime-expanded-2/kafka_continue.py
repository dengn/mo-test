from common import *
N='rt2_kafka';out=json.loads((B/'kafka-expanded-result.json').read_text());names=['wide','composite','ren','drp','widen','nullability','defaultcol']
def save():dump(B/'kafka-expanded-result.json',out)
def rows(port,table):
 if table=='wide':
  r=sql(port,N,'SELECT id,s,u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc,updated FROM wide ORDER BY id')
  return [tuple(x[:7])+(json.loads(x[7]) if x[7] is not None else None,)+tuple(x[8:]) for x in r]
 return sql(port,N,'SELECT * FROM '+table+' ORDER BY 1,2')
def wait(label,table='wide',timeout=80):
 t=time.monotonic();expected=rows(13306,table);last=None
 while time.monotonic()-t<timeout:
  try:last=rows(6001,table)
  except Exception as e:last=str(e)
  if expected==last:break
  time.sleep(1)
 c={'name':label,'status':'passed' if expected==last else 'failed','source':expected,'sink':last,'elapsed_s':round(time.monotonic()-t,2),'connector_status':api('GET','/connectors/rt2-'+table+'/status')};out['cases'].append(c);save();print(label,c['status'],flush=True);return expected==last
# Preserve 100-second failure; wait for framework's default scheduled rebalance delay.
out['broker_rebalance_configuration']={'scheduled.rebalance.max.delay.ms':300000,'observed_log':'got assignment: connectorIds=[], taskIds=[], delay=300000','note':'framework recovery latency; not a MatrixOne data-loss claim'}
for c in out['cases']:
 if c['name']=='nullability-backfill':c['excluded_from_schema_conclusions']='executed while Connect still UNASSIGNED after broker restart'
save();print('WAITING DEFAULT REBALANCE',flush=True)
def assigned():
 s=api('GET','/connectors/rt2-source/status');return s['connector']['state']=='RUNNING' and all(t['state']=='RUNNING' for t in s['tasks'])
poll(assigned,360);assert wait('broker-SIGKILL-eventual-default-delay-recovery')
assert wait('nullability-backfill-after-worker-assignment','nullability')
# Native target availability fault, same persisted MO store and MinIO, no object loss.
out['pre_mo_crash_rows']=rows(6001,'wide');out['faults'].append(kill_owned('mo','/workspace/matrixone/mo-service'));save()
sql(13306,N,"UPDATE wide SET name='MO SIGKILL恢复😀',ts='2026-10-11 19:00:00.654321',updated=500 WHERE id=3")
sql(13306,N,'DELETE FROM wide WHERE id=6');sql(13306,N,"INSERT INTO wide(id,u,name,updated) VALUES(103,9223372036854775808,'MO停机写入',501)")
time.sleep(6);out['sink_while_mo_down']=api('GET','/connectors/rt2-wide/status');save();start('mo');poll(lambda:sql(6001,None,'SELECT 1'),180)
recovered=wait('MO-SIGKILL-connector-auto-retry-catchup',timeout=65)
if not recovered:
 api('POST','/connectors/rt2-wide/restart?includeTasks=true&onlyFailed=true');wait('MO-restart-after-explicit-failed-task-restart')
changes={'ren':(None,None),'drp':('ALTER TABLE drp DROP COLUMN dropped',"UPDATE drp SET v='dropped' WHERE id=1"),'widen':('ALTER TABLE widen MODIFY COLUMN n BIGINT','UPDATE widen SET n=2147483648 WHERE id=1'),'nullability':("ALTER TABLE nullability MODIFY COLUMN nullable VARCHAR(10) NOT NULL DEFAULT 'fill'","INSERT INTO nullability(id,v,n) VALUES(2,'new',2)"),'defaultcol':("ALTER TABLE defaultcol ALTER COLUMN v SET DEFAULT 'def'",'INSERT INTO defaultcol(id,n) VALUES(2,2)')}
for n,(change,update) in changes.items():
 if change:sql(13306,N,change)
 if update:sql(13306,N,update)
 time.sleep(6)
 c={'name':'schema-'+n,'source_schema':sql(13306,N,'SHOW COLUMNS FROM '+n),'sink_schema':sql(6001,N,'SHOW COLUMNS FROM '+n),'source_rows':rows(13306,n),'sink_rows':rows(6001,n),'connector_status':api('GET','/connectors/rt2-'+n+'/status')}
 c['rows_equal']=c['source_rows']==c['sink_rows'];c['schemas_equal']=c['source_schema']==c['sink_schema'];out['cases'].append(c);save();print('DDL',n,'rows',c['rows_equal'],'state',c['connector_status']['tasks'][0]['state'],flush=True)
 api('PUT','/connectors/rt2-'+n+'/pause')
# Explicit schema migration for each profile, then restart the sink and compare again.
adapt={'ren':'ALTER TABLE ren RENAME COLUMN v TO renamed_v','drp':'ALTER TABLE drp DROP COLUMN dropped','widen':'ALTER TABLE widen MODIFY COLUMN n BIGINT','nullability':"ALTER TABLE nullability MODIFY COLUMN nullable VARCHAR(10) NOT NULL DEFAULT 'fill'",'defaultcol':"ALTER TABLE defaultcol ALTER COLUMN v SET DEFAULT 'def'"}
for n,stmt in adapt.items():
 try:
  sql(6001,N,stmt);api('POST','/connectors/rt2-'+n+'/restart?includeTasks=true');api('PUT','/connectors/rt2-'+n+'/resume');wait('explicit-target-schema-adaptation-'+n,n,60)
 except Exception as e:
  out['cases'].append({'name':'explicit-target-schema-adaptation-'+n,'status':'failed','error':str(e),'sql':stmt});save();print('adaptation',n,'FAIL',str(e),flush=True)
out['dedup']=sql(6001,N,'SELECT COUNT(*),COUNT(DISTINCT id) FROM wide');save();print('KAFKA EXPANSION DONE',flush=True)
