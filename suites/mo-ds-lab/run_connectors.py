"""1,000 group-specific computation/read/write assertions per JVM engine.

Each engine runs 10 JDBC pipelines, each returning 100 independent groups.
Job timings belong to pipelines; they are never summed as per-case latencies.
"""
import argparse
import importlib.metadata as metadata
import json
import os
import time

from common import (ROOT,DATABASE,CONNECTOR_AGGS,connection,connector_expected,
                    equal,plain,setup)

def jdbc():
    host=os.getenv('MO_HOST','127.0.0.1'); port=os.getenv('MO_PORT','6001')
    return f'jdbc:mysql://{host}:{port}/{DATABASE}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC'

def prepare(name):
    c=connection()
    with c.cursor() as q:
        q.execute(f'CREATE TABLE IF NOT EXISTS {name}_output (cid INT,family VARCHAR(32),v DOUBLE)')
        # Only this harness-owned output table is reset for a new canonical run.
        q.execute(f'TRUNCATE TABLE {name}_output')
    c.close()

def readback(name,family):
    c=connection()
    with c.cursor() as q:
        q.execute(f'SELECT cid,v FROM {name}_output WHERE family=%s ORDER BY cid',(family,))
        rows=q.fetchall()
    c.close()
    result={}
    for cid,value in rows:
        if cid in result: raise AssertionError(f'Duplicate output cid {cid}')
        result[cid]=plain(value)
    return result

def spark_runner(out):
    from pyspark.sql import SparkSession,functions as F
    spark=(SparkSession.builder.master('local[2]').appName('mo-ds-compatibility')
       .config('spark.jars',str(ROOT/'jars/mysql-connector-j-8.0.33.jar'))
       .config('spark.driver.bindAddress','127.0.0.1')
       .config('spark.driver.host','127.0.0.1')
       .config('spark.sql.shuffle.partitions','2')
       .config('spark.ui.enabled','false').getOrCreate())
    spark.sparkContext.setLogLevel('ERROR')
    props={'driver':'com.mysql.cj.jdbc.Driver','user':os.getenv('MO_USER','root'),
           'password':os.getenv('MO_PASSWORD','111')}
    if os.getenv('SPARK_JDBC_ISOLATION'):
        props['isolationLevel']=os.environ['SPARK_JDBC_ISOLATION']
    def run(family,expr):
        raw=spark.read.jdbc(jdbc(),'connector_input',properties=props)
        result=raw.groupBy('cid').agg(F.expr(expr).cast('double').alias('v')).withColumn('family',F.lit(family)).select('cid','family','v')
        (out/f'{family}-plan.txt').write_text(result._jdf.queryExecution().toString())
        result.write.jdbc(jdbc(),'spark_output',mode='append',properties=props)
        return readback('spark',family)
    return run,spark.stop

def flink_runner(out):
    from pyflink.table import EnvironmentSettings,TableEnvironment
    t=TableEnvironment.create(EnvironmentSettings.in_batch_mode())
    jars=[p.resolve().as_uri() for p in sorted((ROOT/'jars').glob('*.jar'))]
    t.get_config().get_configuration().set_string('pipeline.jars',';'.join(jars))
    t.get_config().get_configuration().set_string('parallelism.default','2')
    t.get_config().get_configuration().set_string('rest.bind-address','127.0.0.1')
    t.get_config().get_configuration().set_string('rest.address','127.0.0.1')
    def options(table):
        # Escape SQL string literals. Do not include credentials in evidence.
        esc=lambda v:v.replace("'","''")
        return f"""'connector'='jdbc','url'='{esc(jdbc())}',
          'table-name'='{table}','driver'='com.mysql.cj.jdbc.Driver',
          'username'='{esc(os.getenv('MO_USER','root'))}',
          'password'='{esc(os.getenv('MO_PASSWORD','111'))}'"""
    t.execute_sql(f"CREATE TABLE mo_source(id BIGINT,cid INT,x DOUBLE,y DOUBLE,nx DOUBLE,k INT) WITH ({options('connector_input')})")
    t.execute_sql(f"CREATE TABLE mo_sink(cid INT,family STRING,v DOUBLE) WITH ({options('flink_output')})")
    def run(family,expr):
        sql=f"INSERT INTO mo_sink SELECT cid,'{family}',CAST({expr} AS DOUBLE) FROM mo_source GROUP BY cid"
        # Flink EXPLAIN may serialize JDBC options. Save no plan with secrets.
        result=t.execute_sql(sql)
        result.wait(120000)
        return readback('flink',family)
    return run,lambda:None

def main():
    p=argparse.ArgumentParser(); p.add_argument('tool',choices=['spark','flink'])
    p.add_argument('--out'); args=p.parse_args()
    name=args.tool; out=ROOT/args.out if args.out else ROOT/'results'/name; out.mkdir(parents=True,exist_ok=True)
    setup(); prepare(name); start=time.time()
    factory=spark_runner if name=='spark' else flink_runner
    run,close=factory(out)
    offset=98000 if name=='spark' else 99000
    jobs=[]
    with (out/'cases.jsonl').open('w') as f:
        try:
            for j,(family,expr) in enumerate(CONNECTOR_AGGS.items()):
                begin=time.perf_counter(); error=None; actual={}
                try: actual=run(family,expr)
                except Exception as exc:
                    error=f'{type(exc).__name__}: {str(exc)}'
                    print(f'{family} FAILED: {error[:1000]}',flush=True)
                ms=(time.perf_counter()-begin)*1000
                jobs.append({'job_id':j,'family':family,'pipeline_ms':ms,
                    'groups_expected':100,'groups_returned':len(actual),
                    'status':'pipeline_error' if error else 'executed',
                    'error':error})
                for cid in range(100):
                    expected=connector_expected(family,cid)
                    r={'case_id':offset+j*100+cid,'tool':name,'family':family,
                       'parameter':cid,'job_id':j,'expected':expected,
                       'actual':actual.get(cid),'status':'pipeline_error' if error else
                         'missing_output' if cid not in actual else
                         'pass' if equal(expected,actual[cid]) else 'mismatch'}
                    if error: r['error']=error
                    f.write(json.dumps(r)+'\n')
                f.flush(); print(f'{name}/{family}: {len(actual)} groups in {ms:.1f} ms',flush=True)
        finally: close()
    (out/'jobs.json').write_text(json.dumps(jobs,indent=2))
    (out/'meta.json').write_text(json.dumps({'tool':name,'version':metadata.version('pyspark' if name=='spark' else 'apache-flink'),
        'execution_seconds':time.time()-start,'cases':1000,'pipelines':10,
        'input_rows':6400,'groups':100,'java':'OpenJDK 21.0.12.1',
        'driver':'mysql-connector-j 8.0.33',
        'jdbc_connector':'4.1.0-2.1' if name=='flink' else 'Spark built-in JDBC',
        'spark_isolation':os.getenv('SPARK_JDBC_ISOLATION','default READ_UNCOMMITTED') if name=='spark' else None,
        'scope':'JDBC source -> engine group computation -> JDBC sink -> independent Python verification',
        'timing_scope':'pipeline wall time, including source, computation, sink and readback; no individual case latency'},indent=2))

if __name__=='__main__': main()
