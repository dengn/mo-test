"""100 actual native Spark window programs on audited MO JDBC sources, with JDBC sinks."""
import json,os,sys,time,traceback
from pathlib import Path
import numpy as np
from pyspark.sql import SparkSession,functions as F
from data import ROOT,DB,SCHEMAS,tables,oracle,connect,read,compare
from scenarios import QUESTIONS,sql_for,params
from run import records

def session():
 os.environ['PYSPARK_PYTHON']=sys.executable;os.environ['PYSPARK_DRIVER_PYTHON']=sys.executable
 jar=Path(os.getenv('MO_JAR_DIR',str(ROOT/'jars')))/'mysql-connector-j-8.0.33.jar'
 s=(SparkSession.builder.master('local[2]').appName('mo-time-series-windows')
    .config('spark.jars',str(jar)).config('spark.driver.host','127.0.0.1').config('spark.driver.bindAddress','127.0.0.1')
    .config('spark.driver.memory','1g').config('spark.sql.shuffle.partitions','2').config('spark.sql.analyzer.maxIterations','1000')
    .config('spark.ui.enabled','false').config('spark.ui.showConsoleProgress','false')
    .config('spark.sql.execution.arrow.pyspark.enabled','true').config('spark.pyspark.python',sys.executable)
    .config('spark.driver.extraJavaOptions','--add-opens=java.base/java.nio=ALL-UNNAMED -Dio.netty.tryReflectionSetAccessible=true')
    .config('spark.executor.extraJavaOptions','--add-opens=java.base/java.nio=ALL-UNNAMED -Dio.netty.tryReflectionSetAccessible=true').getOrCreate())
 s.sparkContext.setLogLevel('ERROR');return s

def main():
 assert not (ROOT/'spark-summary.json').exists(),'Do not overwrite completed evidence'
 data=tables();ref=oracle(data);c=connect();s=session();start=time.time();rows=[];sources=[]
 url=f"jdbc:mysql://{os.getenv('MO_HOST','127.0.0.1')}:{os.getenv('MO_PORT','6001')}/{DB}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
 props=dict(driver='com.mysql.cj.jdbc.Driver',user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),isolationLevel='READ_COMMITTED',batchsize='512')
 with c.cursor() as q:q.execute('CREATE TABLE IF NOT EXISTS ts_spark_sink(case_id INT,eid INT,point_id BIGINT,ordinal BIGINT,value DOUBLE)');q.execute('SELECT COUNT(*) FROM ts_spark_sink');assert q.fetchone()[0]==0
 try:
  for name in SCHEMAS:
   df=s.read.jdbc(url,name,properties=props).cache();count=df.count();a=df.toPandas().sort_values(list(data[name])).reset_index(drop=True);gold=data[name].sort_values(list(data[name])).reset_index(drop=True);compare(gold,a,1e-12);df.createOrReplaceTempView(name);sources.append(dict(table=name,rows=count,full_values_verified=True));print('Spark source',name,count,'audited',flush=True)
  for i in [0,17,28,59,60,61,99,125,177,199]:
   for f in [0,2,4,6,18,21,35,37,38,39]:
    t=time.time();sql=sql_for(f,i);r=dict(case_id=f*200+i,question=QUESTIONS[f][2],family=f,parameter=i,sql=sql,status='started');gold=ref.execute(sql).fetchdf()
    try:
     result=s.sql(sql).cache();a=result.toPandas();compare(gold,a)
     key='day' if 'day' in a.columns else 'minute';point='day' if 'day' in a.columns else 'event_id';case=int(r['case_id'])
     sink=result.select(F.lit(case).cast('int').alias('case_id'),F.col('eid').cast('int'),F.col(point).cast('long').alias('point_id'),F.col(key).cast('long').alias('ordinal'),F.col('x').cast('double').alias('value')).repartition(2)
     sink.write.jdbc(url,'ts_spark_sink',mode='append',properties=props);saved=read(c,f'SELECT eid,point_id,ordinal,value FROM ts_spark_sink WHERE case_id={case} ORDER BY eid,ordinal,point_id')
     check=gold[['eid',point,key,'x']].copy();check.columns=['eid','point_id','ordinal','value'];check=check.sort_values(['eid','ordinal','point_id']).reset_index(drop=True);compare(check,saved)
     with c.cursor() as q:q.execute('DELETE FROM ts_spark_sink WHERE case_id=%s',(case,))
     r.update(status='pass',rows=len(a),columns=list(a),expected=records(gold),actual=records(a),jdbc_sink_rows=len(saved),native_windows=True,seconds=time.time()-t)
     if f==39 and i==60:(ROOT/'spark-session-physical-plan.txt').write_text(result._jdf.queryExecution().executedPlan().toString())
     result.unpersist()
    except Exception as exc:r.update(status='error',error=str(exc),traceback=traceback.format_exc(),seconds=time.time()-t)
    rows.append(r)
    with (ROOT/'spark-cases.jsonl').open('a') as output:output.write(json.dumps(r,allow_nan=False)+'\n')
    print('Spark windows',len(rows),r['case_id'],r['status'],round(r['seconds'],2),flush=True)
 finally:
  s.stop();c.close();ref.close()
 from collections import Counter
 summary=dict(expected=100,completed=len(rows),counts=dict(Counter(r['status'] for r in rows)),sources=sources,seconds=time.time()-start,isolation='READ_COMMITTED',scope='Native Spark SQL on all 18 full-content audited JDBC sources; every result cell vs original-data DuckDB; actual Spark JDBC sink readback and cleanup. Supplemental case IDs overlap canonical IDs and are excluded from the 10000 main count.')
 (ROOT/'spark-summary.json').write_text(json.dumps(summary,indent=2));assert len(rows)==100
if __name__=='__main__':main()
