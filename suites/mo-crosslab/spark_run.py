"""200 Spark workflows: native SQL/ML, executor pandas+NumPy, JDBC publication."""
import argparse,json,os,sys,time,traceback
from pathlib import Path
import numpy as np,pandas as pd
from pyspark.sql import functions as F,Window
from pyspark.sql.types import StructType,StructField,IntegerType,StringType
from pyspark.ml import Pipeline
from pyspark.ml.feature import VectorAssembler,StandardScaler,PCA
from pyspark.ml.clustering import KMeans
from data import ROOT,connect,tables,local_oracle
from graphs import QUESTIONS,query,params
from models import CF,PF,calculate
from common import compare,equal,receipt
from spark_probe import session,sources

def native_ml(s,df,domain,i):
    key='cid' if domain=='customer' else 'pid';cols=CF if domain=='customer' else PF;p=params(i)
    # Spark windows, group statistics, joins and repartitioning precede ML fitting.
    group='region' if domain=='customer' else 'category';w=Window.partitionBy(group).orderBy(F.col('margin').desc(),key)
    rank=df.withColumn('segment_rank',F.row_number().over(w))
    summary=rank.groupBy(group).agg(F.sum('margin').alias('segment_margin'),F.count('*').alias('segment_size'))
    enriched=rank.join(summary,group,'left').repartition(2,group).cache();enriched.count()
    train=enriched.filter((F.col(key)%5)!=p['holdout'])
    pipe=Pipeline(stages=[VectorAssembler(inputCols=cols,outputCol='raw_vector'),
        StandardScaler(inputCol='raw_vector',outputCol='scaled_vector',withStd=True,withMean=True),
        PCA(k=6,inputCol='scaled_vector',outputCol='principal_vector'),
        KMeans(k=4,seed=p['seed'],featuresCol='principal_vector',predictionCol='cluster',maxIter=35,tol=1e-6)])
    model=pipe.fit(train);scored=model.transform(enriched).cache();scored.count()
    entries=scored.select(key,'scaled_vector','principal_vector','cluster').orderBy(key).collect()
    raw=enriched.select(key,*cols).orderBy(key).toPandas();rawx=raw[cols].to_numpy(float);tid=raw[key].to_numpy(int)%5!=p['holdout']
    mean=rawx[tid].mean(0);std=rawx[tid].std(0,ddof=1)
    # Exact constant input has mathematical variance zero. A two-pass NumPy
    # subtraction can leave ~1e-18 std, while Spark Welford correctly returns 0.
    constant=np.ptp(rawx[tid],axis=0)==0;std=np.where(constant,1,std);z=(rawx-mean)/std;z[:,constant]=0
    actual_z=np.vstack([r.scaled_vector.toArray() for r in entries]);assert np.allclose(z,actual_z,rtol=1e-7,atol=1e-7),'Spark standardization'
    component=model.stages[2].pc.toArray();projection=z@component;actual_pcs=np.vstack([r.principal_vector.toArray() for r in entries]);assert np.allclose(projection,actual_pcs,rtol=1e-6,atol=1e-6),'Spark PCA projection'
    cov=np.cov(z[tid],rowvar=False);spectrum=np.linalg.eigvalsh(cov);explained=spectrum[-6:][::-1]/spectrum.sum()
    assert np.allclose(model.stages[2].explainedVariance.toArray(),explained,rtol=1e-6,atol=1e-6),'Spark PCA variance'
    assert np.allclose(component.T@component,np.eye(6),rtol=1e-6,atol=1e-6),'Spark PCA orthogonality'
    centers=np.asarray(model.stages[3].clusterCenters());distance=((projection[:,None]-centers[None,:])**2).sum(2);labels=np.array([r.cluster for r in entries])
    assert np.all(distance[np.arange(len(labels)),labels]<=distance.min(1)+1e-6),'Spark cluster nearest centers'
    counts=np.bincount(labels,minlength=4);assert counts.sum()==len(raw),'Spark memberships'
    r={'parameter':i,'domain':domain,'rows':len(raw),'constant_training_features':[cols[j] for j in np.where(constant)[0]],'checks':{'native_scale':True,'native_pca_variance':True,'native_pca_projection':True,'native_pca_orthogonal':True,'native_cluster_distance':True,'native_cluster_memberships':True},'explained_variance':explained.tolist(),'centers':centers.tolist(),'memberships':counts.tolist(),'stages':['window ranking','group aggregation','segment join','repartition','VectorAssembler','StandardScaler','PCA','KMeans']}
    scored.unpersist();enriched.unpersist();return r

def executor_analysis(pdf):
    # Runs on Spark Python workers, not the driver. All inputs are already verified facts.
    import os,json,pandas as pd
    from models import calculate
    family=int(pdf.family.iloc[0]);i=int(pdf.parameter.iloc[0]);case=int(pdf.case_id.iloc[0])
    domain='customer' if family<10 else 'product';key='cid' if domain=='customer' else 'pid'
    frame=pdf.drop(columns=['family','parameter','case_id']).sort_values(key).reset_index(drop=True)
    result=calculate(family,frame,i,'pandas');result['executor_pid']=os.getpid()
    return pd.DataFrame({'case_id':[case],'model_json':[json.dumps(result,allow_nan=False)]})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pilot',action='store_true');args=ap.parse_args()
    os.environ['PYSPARK_PYTHON']=sys.executable
    out=ROOT/'results'/('spark-pilot' if args.pilot else 'spark');out.mkdir(parents=True,exist_ok=True)
    s=session();s.sparkContext.addPyFile(str(ROOT/'models.py'));s.sparkContext.addPyFile(str(ROOT/'graphs.py'));url,props=sources(s)
    oracle=local_oracle(tables());c=connect();started=time.time();rows=[];ml=[]
    indices=[249] if args.pilot else list(map(int,np.linspace(0,499,10,dtype=int)))
    with c.cursor() as q:q.execute('CREATE TABLE IF NOT EXISTS spark_cross_decisions(case_id INT,entity DOUBLE,allocation DOUBLE,benefit DOUBLE)');q.execute('SELECT COUNT(*) FROM spark_cross_decisions');assert q.fetchone()[0]==0
    try:
        for i in indices:
            for domain in ['customer','product']:
                t=time.time();sql=query(domain,i);expected=oracle.execute(sql).fetchdf();key='cid' if domain=='customer' else 'pid'
                facts=s.sql(sql).cache();a=facts.orderBy(key).toPandas();compare(expected,a)
                (out/f'{domain}-{i}-physical-plan.txt').write_text(facts._jdf.queryExecution().executedPlan().toString())
                print('Spark facts',domain,i,len(a),'pass',flush=True)
                mr=native_ml(s,facts,domain,i);ml.append(mr);print('Spark native ML',domain,i,'pass',flush=True)
                families=range(10) if domain=='customer' else range(10,20)
                configuration=s.createDataFrame([(int(f),int(i),int(f*500+i)) for f in families],'family int,parameter int,case_id int')
                processed=facts.crossJoin(F.broadcast(configuration)).repartition(2,'case_id').groupBy('case_id').applyInPandas(executor_analysis,schema='case_id int,model_json string').collect()
                batch=[];saved=[]
                for item in processed:
                    case=item.case_id;f=case//500;domain0,mission,question=QUESTIONS[f];actual=json.loads(item.model_json);worker_pid=actual.pop('executor_pid');reference=calculate(f,expected,i)
                    r={'case_id':case,'parameter':i,'parameters':params(i),'requirement':mission,'question':question,'client':'spark_native_executor','sql':sql,'expected_facts':receipt(expected),'actual_facts':receipt(a),'expected_analysis':reference,'actual_analysis':actual,'native_spark_ml':mr,'worker_pid':worker_pid,'phase':'analysis'}
                    assert worker_pid!=os.getpid(),'scientific computation executed on driver'
                    assert all(actual['checks'].values()) and all(reference['checks'].values()),'Spark executor constraints'
                    assert equal(reference,actual),'Spark executor model result mismatch'
                    saved.extend((case,*v) for v in actual['decisions']);batch.append(r)
                # Round-trip publication uses Spark JDBC, then an independent MySQL reader.
                sink=s.createDataFrame(saved,'case_id int,entity double,allocation double,benefit double').repartition(2)
                sink.write.jdbc(url,'spark_cross_decisions',mode='append',properties=props)
                for r in batch:
                    with c.cursor() as q:q.execute('SELECT entity,allocation,benefit FROM spark_cross_decisions WHERE case_id=%s ORDER BY entity',(r['case_id'],));read=q.fetchall()
                    assert equal(r['expected_analysis']['decisions'],read),'Spark JDBC decision roundtrip'
                    r.update(status='pass',publication_rows=len(read),batch_seconds=time.time()-t);rows.append(r)
                    with (out/'cases.jsonl').open('a') as file:file.write(json.dumps(r,allow_nan=False)+'\n')
                with c.cursor() as q:q.execute('DELETE FROM spark_cross_decisions')
                facts.unpersist();(out/'native-ml.json').write_text(json.dumps(ml,indent=2));print('Spark completed',len(rows),'business workflows',flush=True)
    except Exception as exc:
        (out/'failure.json').write_text(json.dumps({'error':str(exc),'traceback':traceback.format_exc()},indent=2));raise
    finally:
        (out/'meta.json').write_text(json.dumps({'workflows':len(rows),'target':len(indices)*20,'counts':{'pass':len(rows)},'native_ml_pipelines':len(ml),'seconds':time.time()-started,'scope':'Native Spark SQL on 30 cached JDBC source tables; native windows/joins/standardization/PCA/KMeans; pandas/NumPy/SciPy science on Spark Python workers; Spark JDBC decision publication. Facts shared within each domain/parameter batch of 10 business questions; original-data DuckDB references and independent native ML checks.'},indent=2))
        s.stop();c.close();oracle.close()
    assert len(rows)==len(indices)*20
if __name__=='__main__':main()
