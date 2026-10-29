import datetime,json,traceback
from decimal import Decimal
from pathlib import Path
import pymysql
from pyspark.sql import SparkSession,types as T
B=Path(__file__).parent
out={'spark':'3.5.7','jdbc_driver':'mysql-connector-j-8.4.0','cases':[]}
s=SparkSession.builder.master('local[2]').appName('mo-etl-jdbc').config('spark.ui.enabled','false').config('spark.driver.memory','512m').config('spark.jars','/workspace/work/path-verification/jars/mysql-jdbc.jar').config('spark.sql.session.timeZone','UTC').getOrCreate();s.sparkContext.setLogLevel('ERROR')
d=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True);c=d.cursor();c.execute('CREATE DATABASE IF NOT EXISTS etl_spark');c.execute('DROP TABLE IF EXISTS etl_spark.spark_rows');c.execute('CREATE TABLE etl_spark.spark_rows(id BIGINT PRIMARY KEY,name VARCHAR(100),amount DECIMAL(18,2),ts DATETIME(6))')
url='jdbc:mysql://127.0.0.1:6001/etl_spark?useSSL=false&rewriteBatchedStatements=true'
props={'user':'root','password':'111','driver':'com.mysql.cj.jdbc.Driver','batchsize':'64','isolationLevel':'READ_COMMITTED'}
rows=[(i,None if i%7==0 else ('' if i%7==1 else '中文 😀'+str(i)),None if i%5==0 else Decimal(i-500)/100,None if i%3==0 else datetime.datetime(2026,10,10,12,0,0,123456)) for i in range(1,1004)]
schema=T.StructType([T.StructField('id',T.LongType(),False),T.StructField('name',T.StringType()),T.StructField('amount',T.DecimalType(18,2)),T.StructField('ts',T.TimestampType())])
def case(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],flush=True)
def write():
 s.createDataFrame(rows,schema).repartition(4).write.jdbc(url,'spark_rows',mode='append',properties=props)
 c.execute('SELECT * FROM etl_spark.spark_rows ORDER BY id');got=list(c.fetchall());assert got==rows,(got[:3],rows[:3]);return {'rows':len(got),'write_partitions':4,'batch_size':64}
case('spark_jdbc_parallel_batch_write_exact_types',write)
def read():
 df=s.read.jdbc(url,'spark_rows',column='id',lowerBound=1,upperBound=1004,numPartitions=4,properties=props)
 got=[tuple(r) for r in df.orderBy('id').collect()];assert got==rows,(got[:3],rows[:3]);return {'rows':len(got),'read_partitions':df.rdd.getNumPartitions(),'schema':df.schema.simpleString()}
case('spark_jdbc_partitioned_read',read)
def filter_read():
 df=s.read.jdbc(url,'spark_rows',properties=props).filter('id>=990 AND amount IS NOT NULL').select('id','amount')
 got=[tuple(r) for r in df.orderBy('id').collect()];want=[(r[0],r[2]) for r in rows if r[0]>=990 and r[2] is not None];assert got==want
 return {'rows':len(got),'plan':df._jdf.queryExecution().executedPlan().toString()}
case('spark_jdbc_filter_projection_pushdown',filter_read)
def failed_partition_atomic():
 c.execute('DROP TABLE IF EXISTS etl_spark.duplicate_rows');c.execute('CREATE TABLE etl_spark.duplicate_rows(id BIGINT PRIMARY KEY,name VARCHAR(100),amount DECIMAL(18,2),ts DATETIME(6))')
 dup=[rows[0],rows[1],rows[0]]
 try:s.createDataFrame(dup,schema).coalesce(1).write.jdbc(url,'duplicate_rows',mode='append',properties=props);raise AssertionError('duplicate accepted')
 except Exception as e:
  if isinstance(e,AssertionError):raise
  error=str(e)[:800]
 c.execute('SELECT count(*) FROM etl_spark.duplicate_rows');count=c.fetchone()[0];assert count==0,('partial transaction',count)
 s.createDataFrame(rows[:3],schema).coalesce(1).write.jdbc(url,'duplicate_rows',mode='append',properties=props);c.execute('SELECT * FROM etl_spark.duplicate_rows ORDER BY id');assert list(c.fetchall())==rows[:3]
 return {'expected_rejection':error,'partial_rows':count,'recovery_rows':3}
case('spark_jdbc_failed_partition_rollback_and_retry',failed_partition_atomic)
s.stop();c.close();d.close();(B/'spark-jdbc-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
