"""Eight complete requirement workflows via engine SQL + JDBC + scientific models."""
import json,os,re,time
from pathlib import Path
import pandas as pd
from data import ROOT,DB,SCHEMAS,tables,connect,local_oracle
from catalog import MISSIONS,queries
from run import plain,rows_equal,equal
from analysis import calculate
JARS=Path(os.getenv('MO_JAR_DIR',str(ROOT/'jars' if (ROOT/'jars').exists() else Path('/workspace/mo-ds-lab/jars'))))
FAMILIES=[0,6,8,16,20,28,29,39]
def main(name):
 out=ROOT/'results'/name;out.mkdir(parents=True,exist_ok=True);data=tables();oracle=local_oracle(data);c=connect();started=time.time();rows=[]
 url=f"jdbc:mysql://{os.getenv('MO_HOST','127.0.0.1')}:{os.getenv('MO_PORT','6001')}/{DB}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
 if name=='spark':
  from pyspark.sql import SparkSession
  sp=(SparkSession.builder.master('local[2]').appName('mo-business-demand').config('spark.jars',str(JARS/'mysql-connector-j-8.0.33.jar')).config('spark.driver.host','127.0.0.1').config('spark.driver.bindAddress','127.0.0.1').config('spark.sql.analyzer.maxIterations','500').config('spark.sql.shuffle.partitions','2').config('spark.ui.enabled','false').getOrCreate());sp.sparkContext.setLogLevel('ERROR');props={'driver':'com.mysql.cj.jdbc.Driver','user':os.getenv('MO_USER','root'),'password':os.getenv('MO_PASSWORD','111'),'isolationLevel':'READ_COMMITTED'}
  for table in SCHEMAS:sp.read.jdbc(url,table,properties=props).createOrReplaceTempView(table)
  def execute(sql,sink,cols):
   from pyspark.sql import functions as F
   frame=sp.sql(sql);frame.select(*[F.col(k).cast('double').alias('c'+str(j)) for j,k in enumerate(cols)]).write.jdbc(url,sink,mode='append',properties=props)
  close=sp.stop
 else:
  from pyflink.table import EnvironmentSettings,TableEnvironment
  te=TableEnvironment.create(EnvironmentSettings.in_batch_mode());cfg=te.get_config().get_configuration();cfg.set_string('pipeline.jars',';'.join(p.resolve().as_uri() for p in sorted(JARS.glob('*.jar'))));cfg.set_string('parallelism.default','2');cfg.set_string('rest.bind-address','127.0.0.1');cfg.set_string('rest.address','127.0.0.1')
  def options(table):
   esc=lambda x:x.replace("'","''")
   return f"'connector'='jdbc','url'='{esc(url)}','table-name'='{table}','driver'='com.mysql.cj.jdbc.Driver','username'='{esc(os.getenv('MO_USER','root'))}','password'='{esc(os.getenv('MO_PASSWORD','111'))}'"
  for table,frame in data.items():
   fields=','.join('`'+col+'` '+('TIMESTAMP(0)' if 'datetime' in str(dtype) else 'DOUBLE' if 'float' in str(dtype) else 'INT') for col,dtype in frame.dtypes.items());te.execute_sql(f'CREATE TABLE {table}({fields}) WITH ({options(table)})')
  def execute(sql,sink,cols):
   quote=lambda s:re.sub(r'\b[a-z][a-z0-9_]*\b',lambda m:'`'+m[0]+'`',s)
   te.execute_sql(f'CREATE TABLE {sink}('+','.join(f'c{j} DOUBLE' for j in range(len(cols)))+f') WITH ({options(sink)})');view='view_'+sink;te.create_temporary_view(view,te.sql_query(quote(sql)));cast=','.join(f'CAST(`{col}` AS DOUBLE)' for col in cols);te.execute_sql(f'INSERT INTO {sink} SELECT {cast} FROM {view}').wait(180000)
  close=lambda:None
 with (out/'cases.jsonl').open('w') as file:
  try:
   for f in FAMILIES:
    i=31;m=MISSIONS[f];t=time.perf_counter();r={'requirement':m['key'],'question':m['question'],'parameter':i,'engine':name,'stages':[]};expected=[];actual=[];state='engine_sql'
    try:
     for j,sql in enumerate(queries(f,i)):
      e=oracle.execute(sql).fetchdf();columns=list(e);sink=f'{name}_facts_{f}_{j}'
      with c.cursor() as q:q.execute(f'CREATE TABLE IF NOT EXISTS {sink}('+','.join(f'c{k} DOUBLE' for k in range(len(columns)))+')');q.execute(f'TRUNCATE TABLE {sink}')
      execute(sql,sink,columns)
      with c.cursor() as q:q.execute(f'SELECT * FROM {sink}');a=pd.DataFrame(q.fetchall(),columns=columns)
      # Restore the business dataset's ORDER BY keys without requiring identical
      # floating bit patterns from independent SUM implementations.
      order=[col.strip().split('.')[-1] for col in sql.rsplit(' ORDER BY ',1)[1].split(',')]
      e=e.sort_values(order,na_position='last').reset_index(drop=True);a=a.sort_values(order,na_position='last').reset_index(drop=True);ok=rows_equal(e,a);r['stages'].append({'sql':sql,'rows':len(a),'status':'pass' if ok else 'mismatch'})
      if not ok:r['expected_failed_stage']=plain(e.replace({float('nan'):None}).values.tolist());r['actual_failed_stage']=plain(a.replace({float('nan'):None}).values.tolist());raise AssertionError('engine fact mismatch')
      expected.append(e);actual.append(a)
     state='scientific_model';em=plain(calculate(m['key'],expected,i));am=plain(calculate(m['key'],actual,i));r.update(expected_analysis=em,actual_analysis=am)
     if not equal(em,am) or not all(em['checks'].values()):raise AssertionError('engine workflow decision mismatch')
     state='decision_jdbc';sink=f'{name}_decisions_{f}';records=am['decisions']
     with c.cursor() as q:
      q.execute(f'CREATE TABLE IF NOT EXISTS {sink}(entity INT,allocation DOUBLE,benefit DOUBLE)');q.execute(f'TRUNCATE TABLE {sink}')
      if records:q.executemany(f'INSERT INTO {sink} VALUES(%s,%s,%s)',records)
      q.execute(f'SELECT entity,allocation,benefit FROM {sink} ORDER BY entity');saved=q.fetchall()
     assert equal(plain(sorted(em['decisions'])),plain(saved));r['status']='pass'
    except Exception as exc:r.update(status='pipeline_error',phase=state,error=str(exc)[:5000])
    r['ms']=(time.perf_counter()-t)*1000;rows.append(r);file.write(json.dumps(r)+'\n');file.flush();print(name,m['key'],r['status'],r.get('error','')[:700],flush=True)
  finally:close()
 meta={'tool':name,'workflows':8,'counts':{s:sum(r['status']==s for r in rows) for s in set(r['status'] for r in rows)},'started_at':started,'ended_at':time.time(),'seconds':time.time()-started,'scope':'Supplemental eight business workflows, excluded from canonical 10000. Engine SQL runs against JDBC source facts and writes them through JDBC. NumPy/SciPy scientific decisions run in Python, then persist through MySQL protocol. Final conclusions match an original-data DuckDB reference.'};(out/'meta.json').write_text(json.dumps(meta,indent=2));oracle.close();c.close()
