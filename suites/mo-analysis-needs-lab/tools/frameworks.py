"""Actual Spark streaming and Flink JDBC aggregate supplements; shared jobs, 10000 group assertions each."""
import sys,os,json,time,hashlib,shutil,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np,pandas as pd
from data import ROOT,DB,EPOCH,connect,read,compare,values,plain
N=10000
TABLE='framework_events'
COLUMNS='row_id case_id phase event_min uid v weight flag'.split()
def events():
 rows=[]
 for cid in range(N):
  for phase in range(4):
   for tick in [0,1]:
    rows.append([len(rows)+1,cid,phase,phase*4+tick,1+cid%32,float(1+(cid*13+phase*7+tick*3)%97)/7,1+(cid+tick)%5,int((cid+phase+tick)%3==0)])
  # Guaranteed very late after the first window has already closed.
  rows.append([len(rows)+1,cid,3,1,1+cid%32,1000.+cid%7,2.,1])
 rows.append([len(rows)+1,-1,4,50,1,0.,1.,0])
 return pd.DataFrame(rows,columns=COLUMNS)
def prepare(data):
 c=connect()
 with c.cursor() as q:
  q.execute(f'DROP TABLE IF EXISTS {TABLE}');q.execute(f'CREATE TABLE {TABLE}(row_id INT PRIMARY KEY,case_id INT,phase INT,event_min INT,uid INT,v DOUBLE,weight DOUBLE,flag INT)')
  for k in range(0,len(data),512):q.executemany(f'INSERT INTO {TABLE} VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',list(data.iloc[k:k+512].itertuples(index=False,name=None)))
 compare(data,read(c,f'SELECT * FROM {TABLE} ORDER BY row_id'),1e-12);c.close()
def expected(data,late):
 a=data[data.case_id>=0].copy()
 if not late:a=a[~((a.phase==3)&(a.event_min==1))]
 a['bucket']=(a.event_min//2).astype(int);rows=[]
 for (cid,bucket),g in a.groupby(['case_id','bucket'],sort=True):
  x=g.v.to_numpy(float);w=g.weight.to_numpy(float);m=sum(float(v) for v in x)/len(x);rows.append([int(cid),int(bucket),len(x),float(sum(x)),m,float(sum((float(v)-m)**2 for v in x)/len(x)),float(min(x)),float(max(x)),float(sum(float(v)*float(wi) for v,wi in zip(x,w))),int(g.flag.sum()),int(g.uid.nunique())])
 return pd.DataFrame(rows,columns='case_id bucket n total mean_val var_val minimum maximum weighted n_flag n_uid'.split())
def jdbc():
 url=f"jdbc:mysql://{os.getenv('MO_HOST','127.0.0.1')}:{os.getenv('MO_PORT','6001')}/{DB}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
 return url,dict(driver='com.mysql.cj.jdbc.Driver',user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),isolationLevel='READ_COMMITTED')
def verify(out,g,a,name):
 a=a.sort_values(['case_id','bucket']).reset_index(drop=True);g=g.sort_values(['case_id','bucket']).reset_index(drop=True);assert len(a)==len(g);records=[]
 with (out/'cases.jsonl').open('w') as f:
  for cid in range(N):
   gg=g[g.case_id==cid].reset_index(drop=True);aa=a[a.case_id==cid].reset_index(drop=True);r=dict(case_id=cid,engine=name,status='pass',columns=list(g),expected=values(gg),actual=values(aa),profile=cid%10)
   try:compare(gg,aa,1e-7)
   except Exception as e:r.update(status='fail',error=str(e))
   f.write(json.dumps(plain(r),separators=(',',':'))+'\n');records.append(r['status'])
 return dict(cases=N,passed=records.count('pass'),failed=records.count('fail'),rows=len(a),scope='10000 group assertions in a shared native framework pipeline; supplemental, not 10000 independent JVM jobs or primary case replacements')
def spark(data,out):
 from pyspark.sql import SparkSession,functions as F,types as T
 url,props=jdbc();sp=(SparkSession.builder.master('local[2]').appName('mo-needs-watermark-recovery').config('spark.jars',str(ROOT/'jars/mysql-connector-j-8.0.33.jar')).config('spark.driver.host','127.0.0.1').config('spark.driver.bindAddress','127.0.0.1').config('spark.sql.shuffle.partitions','4').config('spark.ui.enabled','false').config('spark.driver.memory','1g').getOrCreate());sp.sparkContext.setLogLevel('ERROR')
 source=sp.read.jdbc(url,TABLE,properties=props).cache();original=source.orderBy('row_id').toPandas();compare(data,original,1e-12)
 feed=out/'feed';feed.mkdir();pending=out/'pending';pending.mkdir();checkpoint=out/'checkpoint';sink='spark_window_results';c=connect()
 with c.cursor() as q:q.execute(f'DROP TABLE IF EXISTS {sink}');q.execute(f'CREATE TABLE {sink}(case_id INT,bucket INT,n BIGINT,total DOUBLE,mean_val DOUBLE,var_val DOUBLE,minimum DOUBLE,maximum DOUBLE,weighted DOUBLE,n_flag BIGINT,n_uid BIGINT,PRIMARY KEY(case_id,bucket))')
 c.close();journal=[]
 def save(df,batch_id):
  a=df.filter(F.col('case_id')>=0).select('case_id',((F.unix_timestamp('window.start')-EPOCH*60)/120).cast('int').alias('bucket'),'n','total','mean_val','var_val','minimum','maximum','weighted','n_flag','n_uid').toPandas()
  con=connect();con.begin()
  try:
   with con.cursor() as q:
    if len(a):q.executemany(f'REPLACE INTO {sink} VALUES('+','.join(['%s']*len(a.columns))+')',[tuple(x.item() if isinstance(x,np.generic) else x for x in row) for row in a.itertuples(index=False,name=None)])
   con.commit()
  except:con.rollback();raise
  finally:con.close()
  journal.append(dict(batch_id=int(batch_id),rows=len(a)));(out/'microbatch-journal.json').write_text(json.dumps(journal,indent=2))
 schema=T.StructType([T.StructField(k,T.IntegerType() if k not in ['v','weight'] else T.DoubleType(),False) for k in COLUMNS])
 def start():
  incoming=sp.readStream.schema(schema).option('maxFilesPerTrigger',1).json(str(feed));incoming=incoming.withColumn('ts',F.to_timestamp(F.from_unixtime(F.lit(EPOCH*60)+F.col('event_min')*60)))
  result=incoming.withWatermark('ts','2 minutes').groupBy(F.window('ts','2 minutes'),F.col('case_id')).agg(F.count('*').alias('n'),F.sum('v').alias('total'),F.avg('v').alias('mean_val'),F.var_pop('v').alias('var_val'),F.min('v').alias('minimum'),F.max('v').alias('maximum'),F.sum(F.col('v')*F.col('weight')).alias('weighted'),F.sum('flag').alias('n_flag'),F.size(F.collect_set('uid')).cast('long').alias('n_uid'))
  return result.writeStream.outputMode('append').option('checkpointLocation',str(checkpoint)).foreachBatch(save).start()
 query=start();progress=[]
 try:
  for phase in range(5):
   folder=pending/f'phase-{phase}';source.filter(F.col('phase')==phase).coalesce(1).write.mode('error').json(str(folder));part=next(folder.glob('part-*.json'));shutil.move(str(part),str(feed/f'phase-{phase}.json'));query.processAllAvailable();progress.extend(query.recentProgress)
   if phase==1:query.stop();query=start()
  query.stop();c=connect();a=read(c,f'SELECT * FROM {sink} ORDER BY case_id,bucket');c.close();result=verify(out,expected(data,False),a,'spark_structured_streaming');result.update(restarted_from_checkpoint=True,very_late_input_rows=N,jdbc_source_rows=len(original),sink='foreachBatch bounded MySQL-protocol transaction with composite-key idempotent upsert',native_operators=['event-time watermark','tumbling window','count','sum','mean','population variance','min','max','weighted sum','conditional sum','distinct uid'])
  (out/'stream-progress.json').write_text(json.dumps(progress,indent=2));return result
 finally:
  if query.isActive:query.stop()
  sp.stop()
def flink(data,out):
 from pyflink.table import EnvironmentSettings,TableEnvironment
 te=TableEnvironment.create(EnvironmentSettings.in_batch_mode());cfg=te.get_config().get_configuration();cfg.set_string('pipeline.jars',';'.join(p.resolve().as_uri() for p in sorted((ROOT/'jars').glob('*.jar'))));cfg.set_string('parallelism.default','2');cfg.set_string('rest.bind-address','127.0.0.1');cfg.set_string('rest.address','127.0.0.1');url,props=jdbc()
 esc=lambda x:x.replace("'","''")
 def options(table):return f"'connector'='jdbc','url'='{esc(url)}','table-name'='{table}','driver'='com.mysql.cj.jdbc.Driver','username'='{esc(props['user'])}','password'='{esc(props['password'])}'"
 te.execute_sql('CREATE TABLE events('+','.join(f'`{k}` '+('DOUBLE' if k in ['v','weight'] else 'INT') for k in COLUMNS)+f') WITH ({options(TABLE)})')
 te.execute_sql(f'CREATE TABLE units(uid INT,region INT,sector INT,scale DOUBLE) WITH ({options("units")})')
 sink='flink_window_results';c=connect()
 with c.cursor() as q:q.execute(f'DROP TABLE IF EXISTS {sink}');q.execute(f'CREATE TABLE {sink}(case_id INT,bucket INT,n BIGINT,total DOUBLE,mean_val DOUBLE,var_val DOUBLE,minimum DOUBLE,maximum DOUBLE,weighted DOUBLE,n_flag BIGINT,n_uid BIGINT)')
 c.close();columns='case_id bucket n total mean_val var_val minimum maximum weighted n_flag n_uid'.split();te.execute_sql('CREATE TABLE sink('+','.join(f'`{k}` '+('BIGINT' if k in ['n','n_flag','n_uid'] else 'INT' if k in ['case_id','bucket'] else 'DOUBLE') for k in columns)+f') WITH ({options(sink)})')
 query='''INSERT INTO sink SELECT e.case_id,CAST(FLOOR(CAST(e.event_min AS DOUBLE)/2) AS INT) bucket,COUNT(*),SUM(e.v),AVG(e.v),VAR_POP(e.v),MIN(e.v),MAX(e.v),SUM(e.v*e.weight),SUM(CAST(e.flag AS BIGINT)),COUNT(DISTINCT e.uid) FROM events e JOIN units u ON e.uid=u.uid WHERE e.case_id>=0 GROUP BY e.case_id,CAST(FLOOR(CAST(e.event_min AS DOUBLE)/2) AS INT)'''
 (out/'query.sql').write_text(query);te.execute_sql(query).wait(300000);c=connect();a=read(c,f'SELECT * FROM {sink} ORDER BY case_id,bucket');c.close();result=verify(out,expected(data,True),a,'flink_bounded_jdbc');result.update(jdbc_source_rows=len(data),native_operators=['JDBC source','dimension join','event-time bucket','count','sum','mean','population variance','min','max','weighted sum','conditional sum','count distinct','JDBC sink'],late_event_semantics='bounded complete-data recomputation includes all late rows; no Flink arrival-time watermark or restart claim');return result
if __name__=='__main__':
 name=sys.argv[1];out=ROOT/'results'/('supplement-'+name);out.mkdir(exist_ok=False);data=events();started=time.time();result={}
 try:
  if name=='prepare':prepare(data);result=dict(rows=len(data),audit='full JDBC-protocol source value comparison passed')
  else:result=globals()[name](data,out)
 except Exception as e:result=dict(status='error',error=str(e),traceback=traceback.format_exc());raise
 finally:result.update(elapsed_seconds=time.time()-started);(out/'summary.json').write_text(json.dumps(result,indent=2));print('SUMMARY',result,flush=True)
