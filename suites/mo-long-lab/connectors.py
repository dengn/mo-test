"""Supplemental complex Spark/Flink JDBC pipelines; excluded from main 100k count."""
import argparse,json,os,time,re
from pathlib import Path
from data import ROOT,DB,connect,tables,local_oracle,SCHEMAS
from run import equal,plain
from scenarios import sql_for
def compare(a,b):return equal([[a]],[[b]])
JARS=Path(os.getenv('MO_JAR_DIR',str(ROOT/'jars' if (ROOT/'jars').exists() else Path('/workspace/mo-ds-lab/jars'))))
P=[]
for family in [30,38]:
    query=sql_for(family,0,rows=True).replace('cid>=1 AND cid<91','cid>=1 AND cid<1001')
    # Preserve the entire dependent analysis chain; emit one weighted metric per customer.
    final=query.rfind('SELECT cid,tier,region,score,')
    body=query[final:].replace(' ORDER BY cid','')
    query=query[:final]+', pipeline_metric AS ('+body+') SELECT cid,weighted v FROM pipeline_metric'
    P.append(('long_chain_'+str(family),query))

def jdbc():return f"jdbc:mysql://{os.getenv('MO_HOST','127.0.0.1')}:{os.getenv('MO_PORT','6001')}/{DB}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"

def schema(name):
    df=tables()[name];parts=[]
    for col,dtype in df.dtypes.items():
        typ='TIMESTAMP(0)' if 'datetime' in str(dtype) else 'DOUBLE' if 'float' in str(dtype) else 'INT'
        parts.append(f'`{col}` {typ}')
    return ','.join(parts)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('tool',choices=['spark','flink']);args=ap.parse_args();name=args.tool
    out=ROOT/'results'/name;out.mkdir(parents=True,exist_ok=True);started_at=time.time();c=connect();sink=name+'_long_output'
    with c.cursor() as q:
        q.execute(f'CREATE TABLE IF NOT EXISTS {sink}(cid INT,family VARCHAR(48),v DOUBLE)');q.execute(f'TRUNCATE TABLE {sink}')
    if name=='spark':
        from pyspark.sql import SparkSession,functions as F
        sp=(SparkSession.builder.master('local[2]').appName('mo-long-analytics').config('spark.jars',str(JARS/'mysql-connector-j-8.0.33.jar')).config('spark.driver.bindAddress','127.0.0.1').config('spark.driver.host','127.0.0.1').config('spark.sql.analyzer.maxIterations',os.getenv('LONG_SPARK_ANALYZER_ITERATIONS','100')).config('spark.sql.shuffle.partitions','2').config('spark.ui.enabled','false').getOrCreate());sp.sparkContext.setLogLevel('ERROR')
        props={'driver':'com.mysql.cj.jdbc.Driver','user':os.getenv('MO_USER','root'),'password':os.getenv('MO_PASSWORD','111'),'isolationLevel':'READ_COMMITTED'}
        for table in SCHEMAS:sp.read.jdbc(jdbc(),table,properties=props).createOrReplaceTempView(table)
        def run(family,sql):
            result=sp.sql(sql).withColumn('family',F.lit(family)).select('cid','family',F.col('v').cast('double').alias('v'))
            result.write.jdbc(jdbc(),sink,mode='append',properties=props)
        close=sp.stop
    else:
        from pyflink.table import EnvironmentSettings,TableEnvironment
        te=TableEnvironment.create(EnvironmentSettings.in_batch_mode());cfg=te.get_config().get_configuration()
        cfg.set_string('pipeline.jars',';'.join(p.resolve().as_uri() for p in sorted(JARS.glob('*.jar'))));cfg.set_string('parallelism.default','2');cfg.set_string('rest.bind-address','127.0.0.1');cfg.set_string('rest.address','127.0.0.1')
        def options(table):
            esc=lambda x:x.replace("'","''")
            return f"'connector'='jdbc','url'='{esc(jdbc())}','table-name'='{table}','driver'='com.mysql.cj.jdbc.Driver','username'='{esc(os.getenv('MO_USER','root'))}','password'='{esc(os.getenv('MO_PASSWORD','111'))}'"
        for table in SCHEMAS:te.execute_sql(f'CREATE TABLE {table}({schema(table)}) WITH ({options(table)})')
        te.execute_sql(f"CREATE TABLE mo_sink(cid INT,family STRING,v DOUBLE) WITH ({options(sink)})")
        def run(family,sql):
            # Flink's parser does not accept this nested WITH form in FROM.
            # Let the Table API parse the analytical query at top level.
            # SCOPE is reserved in Calcite; DAY and table identifiers are
            # quoted explicitly for the Flink SQL dialect.
            sql=re.sub(r'\b[a-z][a-z0-9_]*\b',lambda m:'`'+m[0]+'`',sql)
            view='calc_'+family
            te.create_temporary_view(view,te.sql_query(sql))
            te.execute_sql(f"INSERT INTO mo_sink SELECT cid,'{family}',CAST(v AS DOUBLE) FROM {view}").wait(240000)
        close=lambda:None
    oracle=local_oracle(tables());jobs=[];start=time.time()
    with (out/'cases.jsonl').open('w') as file:
        try:
            for j,(family,sql) in enumerate(P):
                expected=dict(oracle.execute(sql).fetchall());assert len(expected)==1000
                t=time.perf_counter();error=None;actual={}
                try:
                    run(family,sql)
                    with c.cursor() as q:q.execute(f'SELECT cid,v FROM {sink} WHERE family=%s ORDER BY cid',(family,));rows=q.fetchall()
                    actual=dict(rows)
                    if len(actual)!=len(rows):raise AssertionError('duplicate sink keys')
                except Exception as exc:error=str(exc)
                jobs.append({'family':family,'status':'pipeline_error' if error else 'executed','pipeline_ms':(time.perf_counter()-t)*1000,'groups_returned':len(actual),'error':error})
                for cid in range(1,1001):
                    status='pipeline_error' if error else 'missing_output' if cid not in actual else 'pass' if compare(expected[cid],actual[cid]) else 'mismatch'
                    row={'case_id':j*1000+cid-1,'tool':name,'family':family,'cid':cid,'expected':plain(expected[cid]),'actual':plain(actual.get(cid)),'status':status}
                    if error:row['error']=error[:3000]
                    file.write(json.dumps(row)+'\n')
                file.flush();print(name,family,len(actual),'error',error[:800] if error else None,flush=True)
        finally:close()
    oracle.close();c.close();(out/'jobs.json').write_text(json.dumps(jobs,indent=2));(out/'meta.json').write_text(json.dumps({'tool':name,'cases':2000,'pipelines':2,'seconds':time.time()-start,'setup_and_execution_seconds':time.time()-started_at,'started_at':started_at,'ended_at':time.time(),'scope':'supplemental; JDBC multiple sources -> engine complex SQL -> JDBC sink -> DuckDB comparison; not included in canonical 10000; actual overlap recorded from timestamps','isolation':'READ_COMMITTED' if name=='spark' else 'Flink JDBC default','spark_analyzer_max_iterations':int(os.getenv('LONG_SPARK_ANALYZER_ITERATIONS','100')) if name=='spark' else None},indent=2))
if __name__=='__main__':main()
