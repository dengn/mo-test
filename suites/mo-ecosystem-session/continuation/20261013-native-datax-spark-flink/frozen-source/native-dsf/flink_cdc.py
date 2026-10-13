"""Owned Flink cluster, real MySQL binlog, two JDBC sinks, typed full-row oracles."""
import os,sys,json,time,subprocess,signal,urllib.request,shutil,decimal,datetime,hashlib,re,collections
from pathlib import Path
D=Path(__file__).parent;B=D.parent
sys.path.insert(0,'/workspace/toolchains/python/lib/python3.12/site-packages');sys.path.insert(0,str(B/'windowed'));sys.path.insert(0,str(D))
import guard_6g;guard_6g.install()
import runtime as rt
from recycle_profile import register,archive_profile,encode
inv=json.loads((D/'java-runtime-inventory.json').read_text());F=Path(inv['flink']['home'])
W=D/'flink-cdc5-runtime';assert not W.exists();W.mkdir()
for name in ['conf','logs','pids','checkpoints','savepoints','tmp']:(W/name).mkdir()
for p in (F/'conf').iterdir():
 if p.is_file():shutil.copyfile(p,W/'conf'/p.name)
for src,name in [('/workspace/work/etl-expanded/jars/mysql-cdc-3.6.0-1.20.jar','owned-mysql-cdc.jar'),('/workspace/work/path-verification/jars/flink-jdbc.jar','owned-jdbc.jar'),('/workspace/work/path-verification/jars/mysql-jdbc.jar','owned-mysql-driver.jar')]:
 p=F/'lib'/name
 if not p.exists():p.symlink_to(src)
 else:assert p.resolve()==Path(src).resolve()
config=f'''jobmanager:
  rpc:
    address: 127.0.0.1
    port: 18123
  bind-host: 127.0.0.1
  memory:
    process:
      size: 768m
taskmanager:
  bind-host: 127.0.0.1
  host: 127.0.0.1
  numberOfTaskSlots: 2
  memory:
    process:
      size: 1024m
rest:
  address: 127.0.0.1
  bind-address: 127.0.0.1
  port: 18081
  bind-port: 18081
heartbeat:
  timeout: 10000
  interval: 1000
parallelism:
  default: 1
io:
  tmp:
    dirs: {W/'tmp'}
env:
  java:
    home: {inv['jre17']['home']}
  log:
    dir: {W/'logs'}
state:
  checkpoints:
    dir: file://{W/'checkpoints'}
    num-retained: 10000
  savepoints:
    dir: file://{W/'savepoints'}
'''
(W/'conf/config.yaml').write_text(config)
# Preserve runtime logs, keep DEBUG payload/config/password logging disabled.
for p in (W/'conf').glob('log4j*.properties'):
 s=p.read_text().replace('rootLogger.level = INFO','rootLogger.level = WARN').replace('rootLogger.level = info','rootLogger.level = WARN');p.write_text(s)
env=dict(os.environ,JAVA_HOME=inv['jre17']['home'],FLINK_HOME=str(F),FLINK_CONF_DIR=str(W/'conf'),FLINK_LOG_DIR=str(W/'logs'),FLINK_PID_DIR=str(W/'pids'),TMPDIR=str(W/'tmp'),FLINK_IDENT_STRING='dsf-owned')
env['PATH']=env['JAVA_HOME']+'/bin:'+env['PATH'];owned=[];records=[];jid=None
def launch(name,args):
 rt.guard();log=(W/(name+'.console.log')).open('ab')
 p=subprocess.Popen(args,cwd=W,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
 owned.append(p);rt.dump(W/'owned-processes.json',[{'pid':x.pid,'exit_code':x.poll()} for x in owned]);return p
def api(path,method='GET',data=None):
 request=urllib.request.Request('http://127.0.0.1:18081/'+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=8) as r:return json.load(r)
def wait(fn,timeout=100):
 deadline=time.monotonic()+timeout;last=None
 while time.monotonic()<deadline:
  rt.guard()
  try:
   v=fn()
   if v:return v
  except Exception as e:last=str(e)[:300]
  time.sleep(.5)
 raise RuntimeError('Native Flink wait timeout: '+str(last))
def digest(rows):return hashlib.sha256(json.dumps([[['json',json.loads(v)] if i==8 and v is not None else encode(v) for i,v in enumerate(row)] for row in rows],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
cols='case_id,id,v,label,rev,u,b,ts,js'
def read(table,role):return rt.sql('SELECT '+cols+' FROM '+table+' ORDER BY case_id,id',port=role)
def check(stage):
 expected=read('t_flinkcdc5_native',13306);e=digest(expected)
 for role in [6001,13306]:
  start=time.monotonic();error=None
  try:
   wait(lambda:digest(read('s_flinkcdc5_native',role))==e,100)
   a=read('s_flinkcdc5_native',role);assert digest(a)==e
   # A second connection must agree before this phase can pass.
   assert digest(read('s_flinkcdc5_native',role))==e
   r={'id':'flinkcdc5_'+stage+'_'+str(role),'status':'passed','expected_rows':len(expected),'actual_rows':len(a),'expected_sha256':e,'actual_sha256':digest(a)}
  except Exception as ex:
   a=read('s_flinkcdc5_native',role);r={'id':'flinkcdc5_'+stage+'_'+str(role),'status':'failed','expected_rows':len(expected),'actual_rows':len(a),'expected_sha256':e,'actual_sha256':digest(a),'error':str(ex)}
  r.update(stage=stage,role=role,job_id=jid,elapsed_s=time.monotonic()-start,native_path='Flink mysql-cdc snapshot/binlog -> JDBC keyed upsert/delete',guarantee='ordinary JDBC at-least-once with idempotent primary-key effects, not XA exactly-once')
  records.append(r)
  with (D/'flink-cdc5-results.jsonl').open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
  print('FLINK_CDC',r['id'],r['status'],r['actual_rows'],flush=True)
def insert(start,count,cid=100001):
 values=[]
 for i in range(start,start+count):
  values.append((cid,i,decimal.Decimal('-12345678901234567890.123456789012345678') if i%2 else decimal.Decimal('99999999999999999999.999999999999999999'),'源表😀/'+str(i),0,2**64-1 if i%3 else 2**63,bytes(range(256)) if i%2 else b'',datetime.datetime(2024,2,29,12,34,56,123456+i%100),json.dumps({'n':2**64-1,'s':'文😀','a':[None,True]},ensure_ascii=False)))
 values=[tuple(None if (j in [2,5,6,7] and row[1]%11==0) or (j==8 and row[1]%13==0) else value for j,value in enumerate(row)) for row in values]
 with rt.db(13306,autocommit=False) as d,d.cursor() as c:c.executemany('INSERT INTO t_flinkcdc5_native VALUES('+','.join(['%s']*9)+')',values);d.commit()
try:
 assert rt.sql('SELECT @@log_bin,@@binlog_format,@@binlog_row_image',port=13306)==((1,'ROW','FULL'),)
 rt.dump(W/'source-binlog-settings.json',{'settings':rt.sql('SELECT @@log_bin,@@binlog_format,@@binlog_row_image,@@server_id',port=13306),'position_before':rt.sql('SHOW BINARY LOG STATUS',port=13306)})
 ddl='(case_id BIGINT,id BIGINT,v DECIMAL(38,18),label VARCHAR(8192),rev BIGINT,u BIGINT UNSIGNED,b VARBINARY(256),ts DATETIME(6),js JSON,PRIMARY KEY(case_id,id))'
 rt.sql('CREATE TABLE t_flinkcdc5_native'+ddl,port=13306);register(13306,'t_flinkcdc5_native','flinkcdc5','native')
 for role in [6001,13306]:rt.sql('CREATE TABLE s_flinkcdc5_native'+ddl,port=role);register(role,'s_flinkcdc5_native','flinkcdc5','native')
 insert(0,64)
 jm=launch('jobmanager',[str(F/'bin/jobmanager.sh'),'start-foreground'])
 wait(lambda:api('overview'),90)
 tm=launch('taskmanager',[str(F/'bin/taskmanager.sh'),'start-foreground'])
 wait(lambda:api('overview').get('slots-available',0)>=2,90)
 schema='case_id BIGINT,id BIGINT,v DECIMAL(38,18),label STRING,rev BIGINT,u DECIMAL(20,0),b BYTES,ts TIMESTAMP(6),js STRING,PRIMARY KEY(case_id,id) NOT ENFORCED'
 source=rt.endpoint(13306)
 sql="SET 'execution.target'='remote';\nSET 'rest.address'='127.0.0.1';\nSET 'rest.port'='18081';\nSET 'parallelism.default'='1';\nSET 'execution.checkpointing.interval'='2 s';\nSET 'execution.checkpointing.mode'='EXACTLY_ONCE';\nSET 'execution.checkpointing.externalized-checkpoint-retention'='RETAIN_ON_CANCELLATION';\nSET 'restart-strategy.type'='fixed-delay';\nSET 'restart-strategy.fixed-delay.attempts'='100';\nSET 'restart-strategy.fixed-delay.delay'='1 s';\n"
 sql+='CREATE TABLE source_rows ('+schema+") WITH ('connector'='mysql-cdc','hostname'='127.0.0.1','port'='23306','username'='root','password'='"+source['password']+"','database-name'='"+rt.DS+"','table-name'='t_flinkcdc5_native','server-id'='57300-57301','server-time-zone'='UTC','scan.startup.mode'='initial','scan.incremental.snapshot.enabled'='true');\n"
 for role,name in [(6001,'mo_rows'),(13306,'control_rows')]:
  e=rt.endpoint(role)
  sql+='CREATE TABLE '+name+' ('+schema+") WITH ('connector'='jdbc','url'='"+rt.jdbc_url(role)+"','table-name'='s_flinkcdc5_native','driver'='com.mysql.cj.jdbc.Driver','username'='root','password'='"+e['password']+"','sink.buffer-flush.max-rows'='17','sink.buffer-flush.interval'='100 ms','sink.max-retries'='0');\n"
 sql+='EXECUTE STATEMENT SET BEGIN\nINSERT INTO mo_rows SELECT * FROM source_rows;\nINSERT INTO control_rows SELECT * FROM source_rows;\nEND;\n'
 path=W/'pipeline.sql';path.write_text(sql);path.chmod(0o600)
 client=launch('sqlclient',[env['JAVA_HOME']+'/bin/java','-Xmx512m','--add-opens=java.base/java.lang=ALL-UNNAMED','--add-opens=java.base/java.util=ALL-UNNAMED','--add-opens=java.base/java.io=ALL-UNNAMED','-Djava.io.tmpdir='+str(W/'tmp'),'-Dlog4j.configurationFile='+str(W/'conf/log4j-console.properties'),'-cp',str(F/'lib/*'),'org.codehaus.janino.SimpleCompiler',str(D/'OwnedSqlSubmit.java'),'OwnedSqlSubmit',str(path)])
 wait(lambda:client.poll() is not None,120)
 rt.dump(W/'submission-exit.json',{'returncode':client.returncode,'submission_api':'official Flink TableEnvironment.executeSql via native Java helper; not SQL Client certification'})
 if client.returncode:raise RuntimeError('Native Table API submission failed; preserve output and source archive')
 jobs=wait(lambda:[j for j in api('jobs/overview')['jobs'] if j['state']=='RUNNING'],120);assert len(jobs)==1;jid=jobs[0]['jid']
 rt.dump(W/'submitted-job.json',api('jobs/'+jid));check('initial_snapshot')
 wait(lambda:api('jobs/'+jid+'/checkpoints')['counts']['completed']>0,90)
 rt.dump(W/'checkpoint-before-mutations.json',api('jobs/'+jid+'/checkpoints'))
 with rt.db(13306,autocommit=False) as d,d.cursor() as c:
  c.execute("UPDATE t_flinkcdc5_native SET v=%s,label=%s,rev=rev+1,u=%s,b=%s,ts=%s,js=%s WHERE id%%3=0",(decimal.Decimal('0.000000000000000001'),'更新😀',9007199254740993,b'\x00\xff\x80',datetime.datetime(2024,2,29,12,0,0,999999),'null'))
  c.execute('DELETE FROM t_flinkcdc5_native WHERE id%4=1');d.commit()
 insert(1000,32);check('update_delete_insert')
 rt.sql('UPDATE t_flinkcdc5_native SET id=id+10000 WHERE id<64 AND id%5=0',port=13306);check('primary_key_change')
 # A fixed Flink projection is tested across a source ADD COLUMN; new-field propagation is out of scope.
 rt.sql("ALTER TABLE t_flinkcdc5_native ADD COLUMN added_tag VARCHAR(64) DEFAULT '演进😀'",port=13306)
 rt.sql("UPDATE t_flinkcdc5_native SET label='DDL后😀',rev=rev+1 WHERE id>=1000",port=13306);check('source_add_column_fixed_projection')
 before=api('jobs/'+jid+'/checkpoints');rt.dump(W/'checkpoint-before-recovery.json',before)
 assert before['counts']['completed']>0
 # Kill only the newly launched TaskManager, preserving checkpoints and all source/sink data.
 tm.send_signal(signal.SIGTERM);tm.wait(timeout=30)
 with rt.db(13306,autocommit=False) as d,d.cursor() as c:
  c.execute("UPDATE t_flinkcdc5_native SET rev=rev+7,label='恢复增量😀' WHERE id%7=0")
  c.execute('DELETE FROM t_flinkcdc5_native WHERE id%11=0');d.commit()
 tm2=launch('taskmanager-restarted',[str(F/'bin/taskmanager.sh'),'start-foreground'])
 wait(lambda:api('jobs/'+jid)['state']=='RUNNING',120);check('taskmanager_restart_offline_deltas')
 restored=wait(lambda:api('jobs/'+jid+'/checkpoints').get('latest',{}).get('restored'),90)
 rt.dump(W/'checkpoint-restored.json',restored)
 # A rolled-back source transaction must not enter either sink.
 with rt.db(13306,autocommit=False) as d,d.cursor() as c:c.execute('UPDATE t_flinkcdc5_native SET rev=rev+999');d.rollback()
 time.sleep(3);check('rolled_back_source_transaction')
 rt.dump(W/'final-checkpoints.json',api('jobs/'+jid+'/checkpoints'));rt.dump(W/'final-job.json',api('jobs/'+jid))
finally:
 if jid:
  try:api('jobs/'+jid,'PATCH',None)
  except Exception as ex:rt.dump(W/'job-cancel-error.json',{'error':str(ex)})
 for p in reversed(owned):
  if p.poll() is None:p.send_signal(signal.SIGTERM)
 for p in reversed(owned):
  try:p.wait(timeout=20)
  except subprocess.TimeoutExpired:print('OWNED_FLINK_PROCESS_STILL_RUNNING',p.pid,flush=True)
 rt.dump(W/'exit-process-states.json',[{'pid':p.pid,'exit_code':p.poll()} for p in owned])
 rt.dump(D/'flink-cdc5-summary.json',{'cases':len(records),'counts':dict(collections.Counter(x['status'] for x in records)),'job_id':jid,'checkpoint_mode':'EXACTLY_ONCE','external_sink_guarantee':'JDBC at-least-once; no XA/EOS certification'})
 # Archive only after all owned Flink writers have exited; full typed archive + fresh reread.
 if all(p.poll() is not None for p in owned):
  try:receipt=archive_profile('flinkcdc5','native',apply=True);rt.dump(D/'flink-cdc5-archive-receipt.json',receipt)
  except Exception as ex:rt.dump(D/'flink-cdc5-archive-error.json',{'error':str(ex),'tables_retained':True})
