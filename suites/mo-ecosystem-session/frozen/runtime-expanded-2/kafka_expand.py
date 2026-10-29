from common import *
out={'runtime_ref':REF,'profile':'Kafka 3.9.1 / Debezium source and JDBC sink 3.1.2.Final / adaptive_time_microseconds / pre-created target tables','semantics':'at-least-once with PK upsert; equality and duplicate-key checks, no exactly-once claim','cases':[],'faults':[]}
N='rt2_kafka';names=['wide','composite','ren','drp','widen','nullability','defaultcol']
def save():dump(B/'kafka-expanded-result.json',out)
def status():return {n:api('GET','/connectors/rt2-'+n+'/status') for n in ['source']+names}
def rows(port,table):
 if table=='wide':
  raw=sql(port,N,'SELECT id,s,u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc,updated FROM wide ORDER BY id')
  return [tuple(r[:7])+(json.loads(r[7]) if r[7] is not None else None,)+tuple(r[8:]) for r in raw]
 return sql(port,N,'SELECT * FROM '+table+' ORDER BY 1,2')
def wait(name,table,timeout=70):
 start_t=time.monotonic();expected=rows(13306,table);last=None
 while time.monotonic()-start_t<timeout:
  try:last=rows(6001,table)
  except Exception as e:last=str(e)
  if expected==last:
   out['cases'].append({'name':name,'status':'passed','source':expected,'sink':last,'elapsed_s':round(time.monotonic()-start_t,2)});save();print(name,'PASS',flush=True);return True
  time.sleep(1)
 out['cases'].append({'name':name,'status':'failed','source':expected,'sink':last,'connector_status':api('GET','/connectors/rt2-'+table+'/status')});save();print(name,'FAIL',flush=True);return False
for port in [13306,6001]:sql(port,None,'CREATE DATABASE '+N)
ddl={'wide':'id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(100),name VARCHAR(300),ts DATETIME(6),doc JSON,updated BIGINT','composite':'a BIGINT,b VARCHAR(50),v VARCHAR(100),PRIMARY KEY(a,b)'}
ddl.update({n:'id INT PRIMARY KEY,v VARCHAR(10),n SMALLINT,nullable VARCHAR(10),dropped VARCHAR(10)' for n in names if n not in ddl})
for n in names:
 for port in [13306,6001]:sql(port,N,'CREATE TABLE '+n+'('+ddl[n]+')')
for i,u in enumerate([0,2**53,2**63-1,2**63,2**63+1,2**64-1,None],1):
 sql(13306,N,'INSERT INTO wide VALUES('+','.join(['%s']*9)+')',(i,-2**63 if i==1 else 2**63-1,u,'12345678901234567890.123456789012345678',b'\xff\x00\x80','边界😀\n引号\"','2026-10-11 18:00:00.123456',json.dumps({'n':9007199254740993,'arr':[True,None,'中文']}),i))
sql(13306,N,"INSERT INTO composite VALUES(9007199254740993,'中文😀','初始'),(9007199254740993,'B','另一键'),(2,'空','')")
for n in names[2:]:sql(13306,N,'INSERT INTO '+n+" VALUES(1,'short',30000,NULL,'old')")
source=json.loads((OLD/'mo-exact-source.json').read_text());source.update({'database.server.id':'7722','topic.prefix':'rt2cdc','database.include.list':N,'table.include.list':N+'.*','schema.history.internal.kafka.topic':'rt2-schema'})
dump(B/'source-config.json',source);api('PUT','/connectors/rt2-source/config',source)
for n in names:
 sink=json.loads((OLD/'mo-exact-sink.json').read_text());sink.update({'topics':'rt2cdc.'+N+'.'+n,'connection.url':'jdbc:mysql://127.0.0.1:6001/'+N+'?useSSL=false','collection.name.format':n,'primary.key.fields':'a,b' if n=='composite' else 'id'})
 api('PUT','/connectors/rt2-'+n+'/config',sink);dump(B/(n+'-sink-config.json'),sink)
for n in names:wait('snapshot-'+n,n)
sql(13306,N,"UPDATE composite SET a=9223372036854775807,b='新键😀',v='主键迁移' WHERE b='中文😀'")
sql(13306,N,"DELETE FROM composite WHERE b='B'");sql(13306,N,"INSERT INTO composite VALUES(-9223372036854775808,'零','新增')")
wait('composite-primary-key-change-and-delete','composite')
sql(13306,N,"UPDATE wide SET id=101,name='主键已变更😀',updated=100 WHERE id=1");sql(13306,N,'DELETE FROM wide WHERE id=2');wait('single-primary-key-change-and-delete','wide')
# Crash the distributed worker with source-side commits made while it is absent.
out['faults'].append(kill_owned('connect','org.apache.kafka.connect.cli.ConnectDistributed'));save()
sql(13306,N,"UPDATE wide SET name='worker SIGKILL recovery😀',ts='2026-10-11 18:01:00.000001',updated=200 WHERE id=3")
sql(13306,N,'DELETE FROM wide WHERE id=4');sql(13306,N,"INSERT INTO wide(id,u,name,updated) VALUES(102,18446744073709551615,'停机新增',201)")
start('connect');poll(lambda:api('GET','/connectors'),90);wait('worker-SIGKILL-restart-catchup','wide',100)
# Crash/restart single-node KRaft with the same disk, not a replicated durability test.
out['faults'].append(kill_owned('kafka','kafka.Kafka'));save()
sql(13306,N,"UPDATE wide SET name='broker SIGKILL recovery😀',updated=300 WHERE id=3");sql(13306,N,'DELETE FROM wide WHERE id=5')
start('kafka');wait('broker-SIGKILL-same-disk-restart','wide',100)
# Independent DDL cases; retain actual sink schemas and failure traces.
changes={'ren':("ALTER TABLE ren RENAME COLUMN v TO renamed_v","UPDATE ren SET renamed_v='renamed' WHERE id=1"),'drp':('ALTER TABLE drp DROP COLUMN dropped',"UPDATE drp SET v='dropped' WHERE id=1"),'widen':('ALTER TABLE widen MODIFY COLUMN n BIGINT','UPDATE widen SET n=2147483648 WHERE id=1'),'nullability':('ALTER TABLE nullability MODIFY COLUMN nullable VARCHAR(10) NOT NULL DEFAULT \'fill\'',None),'defaultcol':("ALTER TABLE defaultcol ALTER COLUMN v SET DEFAULT 'def'",'INSERT INTO defaultcol(id,n) VALUES(2,2)')}
# A populated NULL must be filled before the valid NOT NULL migration.
sql(13306,N,"UPDATE nullability SET nullable='fill' WHERE id=1");wait('nullability-backfill','nullability')
for n,(change,update) in changes.items():
 sql(13306,N,change)
 if update:sql(13306,N,update)
 else:sql(13306,N,"INSERT INTO nullability(id,v,n) VALUES(2,'new',2)")
 time.sleep(4)
 result={'name':'schema-'+n,'source_schema':sql(13306,N,'SHOW COLUMNS FROM '+n),'sink_schema':sql(6001,N,'SHOW COLUMNS FROM '+n),'connector_status':api('GET','/connectors/rt2-'+n+'/status')}
 result['source_rows']=sql(13306,N,'SELECT * FROM '+n+' ORDER BY id');result['sink_rows']=sql(6001,N,'SELECT * FROM '+n+' ORDER BY id')
 result['rows_equal']=result['source_rows']==result['sink_rows'];result['schemas_equal']=result['source_schema']==result['sink_schema'];out['cases'].append(result);save();print('schema',n,'row_equal',result['rows_equal'],'task',result['connector_status']['tasks'][0]['state'],flush=True)
 # Pause only this owned test sink to avoid repeated bad DDL work.
 api('PUT','/connectors/rt2-'+n+'/pause')
out['dedup']=sql(6001,N,'SELECT COUNT(*),COUNT(DISTINCT id) FROM wide');out['final_status']=status();save();print('KAFKA DONE',flush=True)
