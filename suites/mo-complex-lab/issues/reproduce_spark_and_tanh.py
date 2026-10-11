import json,os,time
from pathlib import Path
import pymysql
from pyspark.sql import SparkSession
root=Path(__file__).resolve().parent
c=pymysql.connect(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT',6001)),user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),database='ds_validation_20261011',autocommit=True)
evidence={}
with c.cursor() as q:
 q.execute('SELECT VERSION()'); evidence['version']=q.fetchone()[0]
 for sql in ['SELECT TANH(0.0)','SELECT TANH(1.0)','SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED','SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED']:
  try:q.execute(sql); evidence[sql]={'status':'ok','rows':q.fetchall()}
  except Exception as e:evidence[sql]={'status':'error','error':str(e)}
 q.execute('DROP TABLE IF EXISTS spark_isolation_issue_repro')
spark=(SparkSession.builder.master('local[1]').appName('mo-spark-isolation-repro').config('spark.jars','/workspace/mo-ds-lab/jars/mysql-connector-j-8.0.33.jar').config('spark.driver.bindAddress','127.0.0.1').config('spark.driver.host','127.0.0.1').config('spark.ui.enabled','false').getOrCreate())
spark.sparkContext.setLogLevel('ERROR')
df=spark.createDataFrame([(1,0.25),(2,0.75)],'id long, value double')
url='jdbc:mysql://127.0.0.1:6001/ds_validation_20261011?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC'
props={'driver':'com.mysql.cj.jdbc.Driver','user':os.getenv('MO_USER','root'),'password':os.getenv('MO_PASSWORD','111')}
for level in ['default','READ_COMMITTED']:
 p=dict(props)
 if level!='default':p['isolationLevel']=level
 try:
  df.write.jdbc(url,'spark_isolation_issue_repro',mode='append',properties=p)
  with c.cursor() as q:q.execute('SELECT COUNT(*),SUM(value) FROM spark_isolation_issue_repro'); rows=q.fetchall()
  evidence['spark_'+level]={'status':'ok','rows':rows}
 except Exception as e:evidence['spark_'+level]={'status':'error','error':str(e)}
 print(level,evidence['spark_'+level]['status'],flush=True)
spark.stop(); c.close()
(root/'fresh-reproduction.json').write_text(json.dumps(evidence,indent=2))
