"""Supplemental complex Spark/Flink JDBC pipelines; excluded from main 100k count."""
import argparse,json,os,time,re
from pathlib import Path
from data import ROOT,DB,connect,tables,local_oracle,SCHEMAS
from run import compare,plain
JARS=Path(os.getenv('MO_JAR_DIR',str(ROOT/'jars' if (ROOT/'jars').exists() else Path('/workspace/mo-ds-lab/jars'))))
BASE='''WITH scope AS (SELECT * FROM customers WHERE cid<=1000),
oo AS (SELECT o.* FROM orders o JOIN scope c ON o.cid=c.cid WHERE o.day>=20 AND o.day<70),
ee AS (SELECT e.* FROM events e JOIN scope c ON e.cid=c.cid WHERE e.day>=20 AND e.day<70)'''
P=[]
def add(n,b):P.append((n,BASE+b))
add('net_revenue', ''', p AS (SELECT oid,SUM(CASE WHEN success=1 THEN paid ELSE 0 END) paid FROM payments GROUP BY oid),r AS (SELECT oid,SUM(refunded) refunded FROM refunds GROUP BY oid),a AS (SELECT o.cid,SUM(COALESCE(p.paid,0)-COALESCE(r.refunded,0)) v FROM oo o LEFT JOIN p ON o.oid=p.oid LEFT JOIN r ON o.oid=r.oid WHERE o.cancelled=0 GROUP BY o.cid) SELECT c.cid,COALESCE(a.v,0) v FROM scope c LEFT JOIN a ON c.cid=a.cid''')
add('category_diversity', ''', a AS (SELECT o.cid,COUNT(DISTINCT p.category) v FROM oo o JOIN items i ON o.oid=i.oid JOIN products p ON i.pid=p.pid GROUP BY o.cid) SELECT c.cid,CAST(COALESCE(a.v,0) AS DOUBLE) v FROM scope c LEFT JOIN a ON c.cid=a.cid''')
add('rolling_order_mean', ''', a AS (SELECT cid,AVG(amount) OVER(PARTITION BY cid ORDER BY day,oid ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) ma FROM oo),b AS (SELECT cid,SUM(ma) v FROM a GROUP BY cid) SELECT c.cid,COALESCE(b.v,0) v FROM scope c LEFT JOIN b ON c.cid=b.cid''')
add('session_conversion', ''', a AS (SELECT cid,session_id,MIN(CASE WHEN kind=0 THEN day END) viewed,MAX(CASE WHEN kind=3 THEN day END) purchased FROM ee GROUP BY cid,session_id),b AS (SELECT cid,SUM(CASE WHEN purchased>=viewed THEN 1 ELSE 0 END) v FROM a GROUP BY cid) SELECT c.cid,CAST(COALESCE(b.v,0) AS DOUBLE) v FROM scope c LEFT JOIN b ON c.cid=b.cid''')
add('last_touch', ''', a AS (SELECT o.cid,o.oid,o.amount,e.kind,ROW_NUMBER() OVER(PARTITION BY o.oid ORDER BY e.day DESC,e.eid DESC) rn FROM oo o JOIN ee e ON o.cid=e.cid AND e.day<=o.day AND e.day>=o.day-7),b AS (SELECT cid,SUM(amount*kind) v FROM a WHERE rn=1 GROUP BY cid) SELECT c.cid,COALESCE(b.v,0) v FROM scope c LEFT JOIN b ON c.cid=b.cid''')
add('activity_streak', ''', a AS (SELECT DISTINCT cid,day FROM ee),b AS (SELECT cid,day-ROW_NUMBER() OVER(PARTITION BY cid ORDER BY day) island FROM a),d AS (SELECT cid,island,COUNT(*) n FROM b GROUP BY cid,island),f AS (SELECT cid,MAX(n) v FROM d GROUP BY cid) SELECT c.cid,CAST(COALESCE(f.v,0) AS DOUBLE) v FROM scope c LEFT JOIN f ON c.cid=f.cid''')
add('credit_imputation', ''', a AS (SELECT tier,AVG(credit) v FROM scope GROUP BY tier) SELECT c.cid,COALESCE(c.credit,a.v) v FROM scope c JOIN a ON c.tier=a.tier''')
add('neighbor_credit', ''', a AS (SELECT c.cid,SUM(n.credit*e.weight)/NULLIF(SUM(CASE WHEN n.credit IS NOT NULL THEN e.weight ELSE 0 END),0) v FROM scope c JOIN edges e ON c.cid=e.src JOIN customers n ON e.dst=n.cid GROUP BY c.cid) SELECT cid,COALESCE(v,0) v FROM a''')
add('decay_attribution', ''', a AS (SELECT o.cid,o.oid,o.amount,e.kind,EXP(-CAST(0.1 AS DOUBLE)*(o.day-e.day)) w FROM oo o JOIN ee e ON o.cid=e.cid AND e.day<=o.day AND e.day>=o.day-7),b AS (SELECT cid,oid,amount,kind,w,SUM(w) OVER(PARTITION BY oid) total FROM a),d AS (SELECT cid,SUM(amount*w/total*kind) v FROM b GROUP BY cid) SELECT c.cid,COALESCE(d.v,0) v FROM scope c LEFT JOIN d ON c.cid=d.cid''')
add('channel_entropy', ''', a AS (SELECT cid,channel,COUNT(*) n FROM oo GROUP BY cid,channel),b AS (SELECT cid,CAST(n AS DOUBLE)/SUM(n) OVER(PARTITION BY cid) p FROM a),d AS (SELECT cid,-SUM(p*LN(p)) v FROM b GROUP BY cid) SELECT c.cid,COALESCE(d.v,0) v FROM scope c LEFT JOIN d ON c.cid=d.cid''')

def jdbc():return f"jdbc:mysql://{os.getenv('MO_HOST','127.0.0.1')}:{os.getenv('MO_PORT','6001')}/{DB}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"

def schema(name):
    df=tables()[name];parts=[]
    for col,dtype in df.dtypes.items():
        typ='TIMESTAMP(0)' if 'datetime' in str(dtype) else 'DOUBLE' if 'float' in str(dtype) else 'INT'
        parts.append(f'`{col}` {typ}')
    return ','.join(parts)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('tool',choices=['spark','flink']);args=ap.parse_args();name=args.tool
    out=ROOT/'results'/name;out.mkdir(parents=True,exist_ok=True);started_at=time.time();c=connect();sink=name+'_complex_output'
    with c.cursor() as q:
        q.execute(f'CREATE TABLE IF NOT EXISTS {sink}(cid INT,family VARCHAR(48),v DOUBLE)');q.execute(f'TRUNCATE TABLE {sink}')
    if name=='spark':
        from pyspark.sql import SparkSession,functions as F
        sp=(SparkSession.builder.master('local[2]').appName('mo-complex-analytics').config('spark.jars',str(JARS/'mysql-connector-j-8.0.33.jar')).config('spark.driver.bindAddress','127.0.0.1').config('spark.driver.host','127.0.0.1').config('spark.sql.shuffle.partitions','2').config('spark.ui.enabled','false').getOrCreate());sp.sparkContext.setLogLevel('ERROR')
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
            sql=re.sub(r'\b(scope|day|value|events|orders|customers|products|items|payments|refunds|edges|calendar)\b',lambda m:'`'+m[0]+'`',sql)
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
    oracle.close();c.close();(out/'jobs.json').write_text(json.dumps(jobs,indent=2));(out/'meta.json').write_text(json.dumps({'tool':name,'cases':10000,'pipelines':10,'seconds':time.time()-start,'setup_and_execution_seconds':time.time()-started_at,'started_at':started_at,'ended_at':time.time(),'scope':'supplemental; JDBC multiple sources -> engine complex SQL -> JDBC sink -> DuckDB comparison; not included in canonical 100000; actual overlap recorded from timestamps','isolation':'READ_COMMITTED' if name=='spark' else 'Flink JDBC default'},indent=2))
if __name__=='__main__':main()
