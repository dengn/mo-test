"""Prepared native batch routes. Import performs no SQL, service startup or downloads."""
import base64, datetime, decimal, hashlib, json, os, re, subprocess, threading
from pathlib import Path
BASE=Path(__file__).resolve().parent
WINDOWS=Path('/tmp/mo-heavy-alternative-20261012/windowed')
DATAX=Path('/workspace/work/etl-expanded/datax')
SEATUNNEL=Path('/workspace/work/type-expanded/apache-seatunnel-2.3.12')
JDBC=SEATUNNEL/'lib/mysql-jdbc.jar'
SPARK=None
SPARK_LOCK=threading.RLock()
PROCESS_LOCK=threading.RLock() # Single JVM batch job prevents four nested partitions from exhausting memory.
ROUTES=['spark','datax','dataxjava8','seatunnel']

def text_value(v,p):
 if v is None:return None
 n=p['name']
 if n in ['blob','varbinary']:return base64.b64encode(bytes(v)).decode()
 if n=='bit64':return str(int(v))
 if n=='time6':
  us=(v.days*86400+v.seconds)*1000000+v.microseconds
  sign='-' if us<0 else '';s,u=divmod(abs(us),1000000);h,s=divmod(s,3600);m,s=divmod(s,60)
  return f'{sign}{h:02}:{m:02}:{s:02}.{u:06}'
 if isinstance(v,datetime.datetime):return v.isoformat(sep=' ',timespec='microseconds')
 if isinstance(v,datetime.date):return v.isoformat()
 if isinstance(v,decimal.Decimal):return format(v,'f')
 if isinstance(v,bool):return '1' if v else '0'
 if isinstance(v,float):return repr(v)
 return str(v)

def scrub(s):
 for k in ['MO_PASSWORD','MYSQL_PASSWORD']:
  v=os.environ.get(k)
  if v:s=s.replace(v,'[REDACTED]')
 return s

def identifier(s):
 if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',s):raise ValueError('Unsafe owned identifier')
 return s

def private_write(path,content):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as f:f.write(content)

def run_job(command,token,env=None):
 """Never persist raw engine output: configurations can contain endpoint passwords."""
 h.guard()
 with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',cwd=str(BASE),start_new_session=True,env=env) as proc:
  tail=[];size=0
  # Stream to bounded memory; stdout is not echoed and only a redacted tail is retained.
  import time, selectors, signal
  sel=selectors.DefaultSelector();sel.register(proc.stdout,selectors.EVENT_READ)
  deadline=time.monotonic()+int(os.environ.get('MO_BATCH_TIMEOUT','240'))
  try:
   while True:
    if time.monotonic()>deadline:raise TimeoutError('Native batch job deadline exceeded')
    events=sel.select(1)
    if events:
     line=proc.stdout.readline()
     if not line:break
     line=scrub(line);tail.append(line);size+=len(line)
     while size>131072 and tail:size-=len(tail.pop(0))
    elif proc.poll() is not None:
     rest=proc.stdout.read();tail.append(scrub(rest)[-131072:]);break
   rc=proc.wait(timeout=5)
  except BaseException:
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
   raise
  finally:sel.close()
 log=''.join(tail)[-131072:]
 slot=hashlib.sha256(str(threading.get_ident()).encode()).hexdigest()[:8]
 private_write(BASE/'runtime'/('last-'+slot+'.log'),log)
 if rc:raise RuntimeError(f'Native batch JVM exited {rc}: '+log[-3500:])
 return log

def spark_load(p,table,rows,role,token,transform):
 global SPARK
 from pyspark.sql import SparkSession,functions as F,types as T
 with SPARK_LOCK:
  if SPARK is None:
   scratch=BASE/'runtime/spark';scratch.mkdir(parents=True,exist_ok=True)
   os.environ.setdefault('PYSPARK_SUBMIT_ARGS','--driver-memory 512m pyspark-shell');os.environ.setdefault('SPARK_LOCAL_DIRS',str(scratch));os.environ.setdefault('SPARK_LOCAL_IP','127.0.0.1')
   # Spark 3.5.7 formally supports Java 8/11/17; Java21 is an unvalidated runtime candidate.
   SPARK=(SparkSession.builder.master('local[2]').appName('mo-heavy-owned-window')
    .config('spark.ui.enabled','false').config('spark.driver.memory','512m')
    .config('spark.jars',str(JDBC)).config('spark.sql.session.timeZone','UTC')
    .config('spark.sql.shuffle.partitions','2').config('spark.sql.warehouse.dir',str(scratch/'warehouse'))
    .getOrCreate())
   SPARK.sparkContext.setLogLevel('ERROR')
  n=p['name'];typ=T.StringType();converted=[]
  if n in ['tinyint','smallint','int32','int64']:typ=T.LongType();convert=lambda v:int(v)
  elif n in ['uint64','decimal20_0']:typ=T.DecimalType(20,0);convert=lambda v:decimal.Decimal(v)
  elif n=='decimal38_18':typ=T.DecimalType(38,18);convert=lambda v:decimal.Decimal(v)
  elif n in ['blob','varbinary']:typ=T.BinaryType();convert=lambda v:bytes(v)
  elif n=='bit64':typ=T.BinaryType();convert=lambda v:int(v).to_bytes(8,'big')
  elif n in ['double','float32']:typ=T.DoubleType();convert=lambda v:float(v)
  elif n=='boolean':typ=T.BooleanType();convert=lambda v:bool(v)
  else:convert=lambda v:text_value(v,p)
  for a,i,v,l,r in rows:converted.append((a,i,None if v is None else convert(v),l,r))
  schema=T.StructType([T.StructField('case_id',T.LongType(),False),T.StructField('id',T.LongType(),False),T.StructField('v',typ,True),T.StructField('label',T.StringType(),False),T.StructField('rev',T.LongType(),False)])
  frame=SPARK.createDataFrame(converted,schema)
  if transform is not None:frame=frame.filter(F.col('id')%2==transform%2).withColumn('label',F.concat('label',F.lit('→ETL'+str(transform)))).withColumn('rev',F.col('rev')+transform+1)
  e=h.endpoint(role)
  try:
   (frame.repartition(2).write.format('jdbc').mode('append').option('url',h.jdbc_url(role))
    .option('dbtable',identifier(table)).option('driver','com.mysql.cj.jdbc.Driver')
    .option('user',e['user']).option('password',e['password']).option('batchsize','17')
    .option('numPartitions','2').option('isolationLevel','READ_COMMITTED').save())
  except Exception as ex:raise RuntimeError(scrub(str(ex))) from None

def sql_text(s):
 if s is None:return 'NULL'
 # No SQL-mode-dependent backslash or quote escaping; explicit utf8mb4 fixture adapter.
 return "CONVERT(0x"+s.encode('utf8').hex()+" USING utf8mb4)" if s else "''"

def datax_load(p,table,rows,role,token,transform):
 with PROCESS_LOCK:
  overlay=BASE/'runtime/datax';overlay.mkdir(parents=True,exist_ok=True)
  for d in ['lib','plugin']:
   path=overlay/d
   if not path.exists():path.symlink_to(DATAX/d,target_is_directory=True)
  (overlay/'conf').mkdir(exist_ok=True)
  (overlay/'conf/core.json').write_bytes((DATAX/'conf/core.json').read_bytes())
  logback='<configuration><appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender"><encoder><pattern>%level %logger{0} - %msg%n</pattern></encoder></appender><root level="INFO"><appender-ref ref="STDOUT"/></root></configuration>'
  (overlay/'conf/logback.xml').write_text(logback)
  # Real mysqlreader reads synthetic SELECT constants. This is an explicit fixture-source adapter.
  query=' UNION ALL '.join('SELECT '+','.join([str(a)+' AS case_id',str(i)+' AS id',sql_text(text_value(v,p))+' AS v',sql_text(l)+' AS label',str(r)+' AS rev']) for a,i,v,l,r in rows)
  query=os.environ.get('MO_DATAX_ACTUAL_QUERY',query)
  reader_role=13306 if os.environ.get('MO_DATAX_ACTUAL_QUERY') else role
  e=h.endpoint(reader_role)
  reader={'name':'mysqlreader','parameter':{'username':e['user'],'password':e['password'],'connection':[{'jdbcUrl':[h.jdbc_url(reader_role)],'querySql':[query]}]}}
  e=h.endpoint(role)
  writer={'name':'mysqlwriter','parameter':{'username':e['user'],'password':e['password'],'column':h.COLS,'writeMode':'insert','batchSize':17,'connection':[{'jdbcUrl':h.jdbc_url(role),'table':[identifier(table)]}]}}
  code='' 
  if p['name'] in ['blob','varbinary'] and not os.environ.get('MO_DATAX_RAW_READ'):code+='if(record.getColumn(2).getRawData()!=null) record.setColumn(2,new BytesColumn(java.util.Base64.getDecoder().decode(record.getColumn(2).asString())));\n'
  if p['name']=='bit64':code+='if(record.getColumn(2).getRawData()!=null){ byte[] b=new byte[8]; java.math.BigInteger x=new java.math.BigInteger(record.getColumn(2).asString()); for(int z=7;z>=0;z--){b[z]=x.byteValue();x=x.shiftRight(8);} record.setColumn(2,new BytesColumn(b));}\n'
  if transform is not None:code+=f'if(record.getColumn(1).asLong()%2 != {transform%2}) return null; record.setColumn(3,new StringColumn(record.getColumn(3).asString()+"→ETL{transform}")); record.setColumn(4,new LongColumn(record.getColumn(4).asLong()+{transform+1}));\n'
  code+='return record;'
  content={'reader':reader,'writer':writer,'transformer':[{'name':'dx_groovy','parameter':{'code':code,'extraPackage':[]}}]}
  job={'job':{'setting':{'speed':{'channel':1},'errorLimit':{'record':0,'percentage':0}},'content':[content]}}
  config=overlay/'job.json';private_write(config,json.dumps(job,ensure_ascii=False))
  command=['java','-Xms128m','-Xmx512m','-Dfile.encoding=UTF-8','-Ddatax.home='+str(overlay),'-Dlogback.configurationFile='+str(overlay/'conf/logback.xml'),'-cp',str(DATAX/'lib/*'),'com.alibaba.datax.core.Engine','-mode','standalone','-jobid','-1','-job',str(config)]
  run_job(command,token)

def seatunnel_load(p,table,rows,role,token,transform):
 with PROCESS_LOCK:
  overlay=BASE/'runtime/seatunnel';overlay.mkdir(parents=True,exist_ok=True)
  for d in ['lib','connectors','starter']:
   path=overlay/d
   if not path.exists():path.symlink_to(SEATUNNEL/d,target_is_directory=True)
  (overlay/'config').mkdir(exist_ok=True)
  for name in ['seatunnel.yaml','hazelcast.yaml','hazelcast-client.yaml']:
   config_text=(SEATUNNEL/'config'/name).read_text()
   if name=='seatunnel.yaml':
    config_text=config_text.replace('/tmp/seatunnel/checkpoint_snapshot',str(overlay/'checkpoint_snapshot')).replace('scheduled-deletion-enable: true','scheduled-deletion-enable: false').replace('enable-http: true','enable-http: false')
   else:config_text=config_text.replace('cluster-name: seatunnel','cluster-name: owned-heavy-batch').replace('5801','15801')
   (overlay/'config'/name).write_text(config_text)
  source=overlay/'input.jsonl'
  private_write(source,'\n'.join(json.dumps(dict(zip(h.COLS,[a,i,text_value(v,p),l,r])),ensure_ascii=False) for a,i,v,l,r in rows)+'\n')
  e=h.endpoint(role);quoted=lambda s:json.dumps(str(s),ensure_ascii=False)
  value='FROM_BASE64(?)' if p['name'] in ['blob','varbinary'] else 'CAST(? AS UNSIGNED)' if p['name']=='bit64' else '?'
  # SQL expression is confined to sink value binding; SeaTunnel still owns reads, transforms and batched JDBC writes.
  query='INSERT INTO '+identifier(table)+'(case_id,id,v,label,rev) VALUES(?,?,'+value+',?,?)'
  sqltransform=''
  sinkinput='input_rows'
  if transform is not None:
   q=f"SELECT case_id,id,v,CONCAT(label,'→ETL{transform}') AS label,rev+{transform+1} AS rev FROM input_rows WHERE MOD(id,2)={transform%2}"
   sqltransform='transform { Sql { plugin_input="input_rows" plugin_output="transformed" query='+quoted(q)+' } }\n';sinkinput='transformed'
  conf=('env { job.mode="BATCH" parallelism=1 }\n'
   'source { LocalFile { plugin_output="input_rows" path='+quoted(source)+' file_format_type="json" schema { fields { case_id="BIGINT" id="BIGINT" v="STRING" label="STRING" rev="BIGINT" } } } }\n'+sqltransform+
   'sink { Jdbc { plugin_input='+quoted(sinkinput)+' url='+quoted(h.jdbc_url(role))+' driver="com.mysql.cj.jdbc.Driver" user='+quoted(e['user'])+' password='+quoted(e['password'])+' query='+quoted(query)+' batch_size=17 max_retries=0 is_exactly_once=false auto_commit=false } }\n')
  config=overlay/'job.conf';private_write(config,conf)
  logconfig=overlay/'config/log4j2.properties';logconfig.write_text('status=error\nname=owned-console\nappender.console.type=Console\nappender.console.name=console\nappender.console.layout.type=PatternLayout\nappender.console.layout.pattern=%p %c{1} %m%n\nrootLogger.level=info\nrootLogger.appenderRef.console.ref=console\n')
  cmd=['java','-Xms128m','-Xmx512m','-Dseatunnel.home='+str(overlay),'-Dseatunnel.config='+str(overlay/'config/seatunnel.yaml'),'-Dhazelcast.config='+str(overlay/'config/hazelcast.yaml'),'-Dhazelcast.client.config='+str(overlay/'config/hazelcast-client.yaml'),'-Dlog4j.configurationFile='+str(logconfig),'-cp',str(overlay/'lib/*')+':'+str(overlay/'starter/seatunnel-starter.jar'),'org.apache.seatunnel.core.starter.seatunnel.SeaTunnelClient','--config',str(config),'--deploy-mode','local']
  job_env=dict(os.environ);job_env['SEATUNNEL_HOME']=str(overlay)
  log=run_job(cmd,token,job_env)
  if 'FINISHED' not in log:raise RuntimeError('SeaTunnel process exited but no FINISHED receipt: '+log[-3000:])

def install():
 global h
 import heavy as h
 previous=h.load
 def load(route,p,table,rows,role,token,transform=None):
  if route not in ROUTES:return previous(route,p,table,rows,role,token,transform)
  h.guard();identifier(table)
  {'spark':spark_load,'datax':datax_load,'dataxjava8':datax_load,'seatunnel':seatunnel_load}[route](p,table,rows,role,token,transform)
 h.load=load
 original_case=h.run_case
 def run_case(route,p,*args,**kwargs):
  result=original_case(route,p,*args,**kwargs)
  if route in ROUTES:
   result['native_engine']={'spark':'PySpark 3.5.7 DataFrame/JDBC','datax':'DataX 3 mysqlreader/Groovy/mysqlwriter','dataxjava8':'DataX 3 mysqlreader/Groovy/mysqlwriter on verified Java 8','seatunnel':'SeaTunnel 2.3.12 Zeta LocalFile/Sql/Jdbc'}[route]
   result['path']='native_batch_engine_with_explicit_value_bindings_and_shared_SQL_effect_adapter'
   result['type_adapter']='declared text/decimal/binary bindings; full-row oracle remains authoritative'
   result['partition_scope']='Spark 2 JDBC partitions per write; DataX channel=1; SeaTunnel parallelism=1; parallel_chunked is 4 engine invocations, not guaranteed engine-native partitioning'
   result['cdc_scope']='batch only; no binlog streaming/checkpoint/exactly-once claim'
  return result
 h.run_case=run_case
 for route in ROUTES:
  if route not in h.ROUTES:h.ROUTES.append(route)
 return h
