"""Supplement: native Spark SQL/ML + actual executor-side deep training + JDBC serving."""
import hashlib,json,os,sys,time
from pathlib import Path
import numpy as np,pandas as pd
from data import ROOT,DB,SCHEMAS,tables,native,query,compare,connect
from models import MISSIONS,prepared,fit,predict,serialize,reload,numpy_forward,evaluate,params
from pyspark.sql import SparkSession
from pyspark.sql.types import *
from pyspark.ml import Pipeline,PipelineModel
from pyspark.ml.feature import VectorAssembler,StandardScaler,PCA
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.regression import LinearRegression
def session():
 return (SparkSession.builder.master('local[2]').appName('mo-deep-ml-validation')
  .config('spark.jars',str(Path(os.getenv('MO_JAR_DIR',str(ROOT/'jars' if (ROOT/'jars').exists() else Path('/workspace/mo-ds-lab/jars'))))/'mysql-connector-j-8.0.33.jar'))
  .config('spark.driver.host','127.0.0.1').config('spark.driver.bindAddress','127.0.0.1')
  .config('spark.driver.memory','1g').config('spark.sql.shuffle.partitions','2')
  .config('spark.sql.analyzer.maxIterations','1000').config('spark.ui.enabled','false').config('spark.ui.showConsoleProgress','false')
  .config('spark.pyspark.python',sys.executable).config('spark.executorEnv.OPENBLAS_NUM_THREADS','1').config('spark.executorEnv.OMP_NUM_THREADS','1')
  .config('spark.driver.extraJavaOptions','--add-opens=java.base/java.nio=ALL-UNNAMED -Dio.netty.tryReflectionSetAccessible=true').config('spark.executor.extraJavaOptions','--add-opens=java.base/java.nio=ALL-UNNAMED -Dio.netty.tryReflectionSetAccessible=true').config('spark.sql.execution.arrow.pyspark.enabled','true').getOrCreate())
def deep_group(f,edges):
 from models import prepared,fit,numpy_forward,evaluate,serialize
 from data import params
 import os,time,json,hashlib,numpy as np,pandas as pd
 t=time.perf_counter();i=int(f['config_i'].iloc[0]);m=int(f['mission_id'].iloc[0]);cid=m*1000+i
 raw=f.drop(columns=['config_i','mission_id','case_id']).sort_values(['eid','day']).reset_index(drop=True)
 p=prepared(raw,i,edges);net,out,metrics=fit(p,m,i);ni=numpy_forward(net,p);np.testing.assert_allclose(ni,out,rtol=3e-5,atol=3e-5);blob=serialize(net)
 return pd.DataFrame([dict(case_id=cid,model_data=blob,model_hash=hashlib.sha256(blob).hexdigest(),predictions=json.dumps(out.tolist(),separators=(',',':')),metadata=json.dumps(dict(i=i,m=m,worker_pid=os.getpid(),training=metrics,metrics=evaluate(out,p,net.task),numpy_error=float(np.max(np.abs(out-ni))),seconds=time.perf_counter()-t),separators=(',',':')))])
def native_ml(s,p,i):
 x=np.concatenate([p['x'][:,-1],p['x'].mean(1)],1).astype(float);cols=[f'f{k}' for k in range(x.shape[1])];rows=[]
 for j in range(64):rows.append(tuple([int(j),int(p['sp'][j]),float(p['y'][j,1]),float(p['y'][j,0])]+x[j].tolist()))
 df=s.createDataFrame(rows,['node','split','risk','response']+cols);tr=df.filter('split=0');stats=[]
 for task in ['classification','forecast']:
  est=LogisticRegression(featuresCol='pc',labelCol='risk',regParam=.1,elasticNetParam=.2,maxIter=25) if task=='classification' else LinearRegression(featuresCol='pc',labelCol='response',regParam=.1,maxIter=25)
  model=Pipeline(stages=[VectorAssembler(inputCols=cols,outputCol='raw'),StandardScaler(inputCol='raw',outputCol='scaled',withMean=True,withStd=True),PCA(k=6,inputCol='scaled',outputCol='pc'),est]).fit(tr)
  sc=model.stages[1];mean=np.array(sc.mean);std=np.array(sc.std);constant=np.ptp(x[:40],axis=0)==0
  np.testing.assert_allclose(mean,x[:40].mean(0),rtol=1e-9,atol=1e-9);expected=x[:40].std(0,ddof=1);expected[constant]=0;np.testing.assert_allclose(std,expected,rtol=1e-9,atol=1e-9)
  z=(x-mean)/np.where(std==0,1,std);z[:,std==0]=0;pc=model.stages[2];mat=np.array(pc.pc.toArray());np.testing.assert_allclose(mat.T@mat,np.eye(6),rtol=1e-7,atol=1e-7)
  v=np.linalg.eigvalsh(np.cov(z[:40].T))[::-1];np.testing.assert_allclose(np.array(pc.explainedVariance),v[:6]/v.sum(),rtol=1e-6,atol=1e-6)
  fitted=model.stages[3];score=z@mat@np.array(fitted.coefficients)+float(fitted.intercept);result=model.transform(df).orderBy('node').collect();pcgot=np.array([np.array(r.pc) for r in result]);np.testing.assert_allclose(pcgot,z@mat,rtol=1e-7,atol=1e-7)
  if task=='classification':got=np.array([r.probability[1] for r in result]);np.testing.assert_allclose(got,1/(1+np.exp(-score)),rtol=1e-6,atol=1e-6)
  else:got=np.array([r.prediction for r in result]);np.testing.assert_allclose(got,score,rtol=1e-7,atol=1e-7)
  dst=ROOT/'spark-native-models'/f'{i}-{task}';model.write().overwrite().save(str(dst))
  restored=PipelineModel.load(str(dst));again=restored.transform(df).orderBy('node').collect()
  restored_values=np.array([r.probability[1] if task=='classification' else r.prediction for r in again]);np.testing.assert_array_equal(restored_values,got)
  stats.append(dict(i=i,task=task,status='pass',train_entities=40,holdout_entities=24,pca_dimensions=6,independent_coefficient_inference=True,serialized_pipeline_reload_exact=True))
 return stats
def main():
 start=time.time();d=tables();s=session();s.sparkContext.setLogLevel('ERROR')
 for name in ['data.py','models.py']:s.sparkContext.addPyFile(str(ROOT/name))
 url=f"jdbc:mysql://{os.getenv('MO_HOST','127.0.0.1')}:{os.getenv('MO_PORT','6001')}/{DB}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
 props={'driver':'com.mysql.cj.jdbc.Driver','user':os.getenv('MO_USER','root'),'password':os.getenv('MO_PASSWORD','111'),'isolationLevel':'READ_COMMITTED'}
 for n in SCHEMAS:
  df=s.read.jdbc(url,n,properties=props).cache();assert df.count()==len(d[n]);a=df.toPandas().astype(float).sort_values(list(d[n])).reset_index(drop=True);b=d[n].astype(float).sort_values(list(d[n])).reset_index(drop=True);compare(a,b,1e-12);df.createOrReplaceTempView(n);print('source_verified',n,len(a),flush=True)
 c=connect()
 with c.cursor() as q:q.execute('CREATE TABLE IF NOT EXISTS ml_spark_models(case_id INT PRIMARY KEY,model_data LONGBLOB,model_hash VARCHAR(64),predictions TEXT,metadata TEXT)');q.execute('SELECT COUNT(*) FROM ml_spark_models');assert q.fetchone()[0]==0
 schema=StructType([StructField('case_id',IntegerType()),StructField('model_data',BinaryType()),StructField('model_hash',StringType()),StructField('predictions',StringType()),StructField('metadata',StringType())]);records=[];native_records=[]
 (ROOT/'spark-native-models').mkdir(exist_ok=True);(ROOT/'spark-models').mkdir(exist_ok=True)
 edges=d['edges']
 for i in [0,55,111,199,333,443,555,777,888,999]:
  sql=query(i);ref=native(d,i);nativefacts=s.sql(sql).toPandas().astype(float);compare(ref,nativefacts)
  direct=s.read.jdbc(url,f'({sql}) as ml_features',properties=props).toPandas().astype(float).sort_values(['eid','day']).reset_index(drop=True);compare(ref,direct)
  if i==0:(ROOT/'spark-optimized-plan.txt').write_text(s.sql(sql)._jdf.queryExecution().optimizedPlan().toString())
  p=prepared(nativefacts,i,edges);native_records.extend(native_ml(s,p,i))
  frames=[]
  for m in range(20):
   f=nativefacts.copy();f['config_i']=i;f['mission_id']=m;f['case_id']=m*1000+i;frames.append(f)
  inp=s.createDataFrame(pd.concat(frames,ignore_index=True));trained=inp.repartition(2,'case_id').groupBy('case_id').applyInPandas(lambda f:deep_group(f,edges),schema).cache()
  got=trained.toPandas();assert len(got)==20
  # Actual executor weights/outputs are written through Spark JDBC, not driver oracle.
  trained.write.jdbc(url,'ml_spark_models',mode='append',properties=props)
  stored=s.read.jdbc(url,'ml_spark_models',properties=props).toPandas();assert len(stored)==20
  for row in stored.itertuples(index=False):
   m=int(row.case_id)//1000;meta=json.loads(row.metadata);blob=bytes(row.model_data);assert hashlib.sha256(blob).hexdigest()==row.model_hash
   assert meta['worker_pid']!=os.getpid();net,out,metrics=fit(prepared(ref,i,edges),m,i);actual=np.array(json.loads(row.predictions),dtype=np.float32);np.testing.assert_array_equal(actual,out);assert metrics==meta['training']
   restored=reload(blob,m,i);np.testing.assert_array_equal(predict(restored,p),out)
   for k,v in net.state_dict().items():np.testing.assert_array_equal(v.numpy(),restored.state_dict()[k].numpy())
   (ROOT/'spark-models'/f'{int(row.case_id):05d}.pt').write_bytes(blob)
   r=dict(case_id=int(row.case_id),status='pass',mission=MISSIONS[m],i=i,worker_pid=meta['worker_pid'],training=meta['training'],metrics=meta['metrics'],numpy_error=meta['numpy_error'],model_bytes=len(blob),model_sha256=row.model_hash,direct_mo_jdbc_facts=True,native_spark_sql_facts=True,spark_jdbc_model_write=True,reload_exact=True,seconds=meta['seconds']);records.append(r)
   with (ROOT/'spark-cases.jsonl').open('a') as log:log.write(json.dumps(r,separators=(',',':'))+'\n')
  with c.cursor() as q:q.execute('DELETE FROM ml_spark_models');q.execute('SELECT COUNT(*) FROM ml_spark_models');assert q.fetchone()[0]==0
  trained.unpersist();print(json.dumps(dict(i=i,passed=len(records),native_ml=len(native_records),seconds=time.time()-start)),flush=True)
 (ROOT/'spark-summary.json').write_text(json.dumps(dict(passed=len(records),failed=0,native_ml=native_records,seconds=time.time()-start,driver_pid=os.getpid(),worker_pids=sorted({r['worker_pid'] for r in records}),isolation='READ_COMMITTED',java=os.getenv('JAVA_HOME')),indent=2));c.close();s.stop()
if __name__=='__main__':main()
