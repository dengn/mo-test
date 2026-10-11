"""Probe direct Spark planning/execution of the multi-source SQL graphs."""
import os,json,time,sys
from pathlib import Path
from pyspark.sql import SparkSession
from data import ROOT,DB,SCHEMAS,tables,local_oracle
from graphs import query
from common import compare

def session():
    s=(SparkSession.builder.master('local[2]').appName('mo-cross-domain-native')
       .config('spark.jars',str(Path(os.getenv('MO_JAR_DIR',str(ROOT/'jars' if (ROOT/'jars').exists() else Path('/workspace/mo-ds-lab/jars'))))/'mysql-connector-j-8.0.33.jar'))
       .config('spark.driver.host','127.0.0.1').config('spark.driver.bindAddress','127.0.0.1')
       .config('spark.driver.memory','2g').config('spark.sql.shuffle.partitions','4')
       .config('spark.sql.analyzer.maxIterations','1000').config('spark.ui.enabled','false')
       .config('spark.ui.showConsoleProgress','false').config('spark.pyspark.python',sys.executable)
       .config('spark.executorEnv.OPENBLAS_NUM_THREADS','1').config('spark.executorEnv.OMP_NUM_THREADS','1')
       .config('spark.driver.extraJavaOptions','--add-opens=java.base/java.nio=ALL-UNNAMED -Dio.netty.tryReflectionSetAccessible=true')
       .config('spark.executor.extraJavaOptions','--add-opens=java.base/java.nio=ALL-UNNAMED -Dio.netty.tryReflectionSetAccessible=true')
       .config('spark.sql.execution.arrow.pyspark.enabled','true').getOrCreate())
    s.sparkContext.setLogLevel('ERROR')
    return s

def sources(s):
    url=f"jdbc:mysql://{os.getenv('MO_HOST','127.0.0.1')}:{os.getenv('MO_PORT','6001')}/{DB}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
    props={'driver':'com.mysql.cj.jdbc.Driver','user':os.getenv('MO_USER','root'),'password':os.getenv('MO_PASSWORD','111'),'isolationLevel':'READ_COMMITTED'}
    for name in SCHEMAS:
        df=s.read.jdbc(url,name,properties=props).cache();n=df.count();df.createOrReplaceTempView(name)
        print('source',name,n,flush=True)
    return url,props

def main():
    s=session();sources(s);o=local_oracle(tables());rows=[]
    for d in ['customer','product']:
        t=time.time();sql=query(d,0)
        try:
            df=s.sql(sql);plan=df._jdf.queryExecution().optimizedPlan().toString();(ROOT/f'spark-{d}-optimized.txt').write_text(plan)
            a=df.toPandas();e=o.execute(sql).fetchdf();compare(e,a)
            rows.append(dict(domain=d,status='pass',rows=len(a),seconds=time.time()-t));print(rows[-1],flush=True)
        except Exception as exc:
            rows.append(dict(domain=d,status='error',error=str(exc)));print(rows[-1],flush=True)
    (ROOT/'spark-probe.json').write_text(json.dumps(rows,indent=2));s.stop();o.close()
if __name__=='__main__':main()
