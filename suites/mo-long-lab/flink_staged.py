"""Same long mathematical program, explicitly materialized at feature-block boundaries."""
import json,os,re,time
from data import ROOT,tables,SCHEMAS,connect,local_oracle
from scenarios import BLOCKS,OUTPUT,profile,parameters,sql_for
from run import equal,plain
from connectors import jdbc,schema,JARS
from pyflink.table import EnvironmentSettings,TableEnvironment

quote=lambda sql:re.sub(r'\b[a-z][a-z0-9_]*\b',lambda m:'`'+m[0]+'`',sql)

def main():
 out=ROOT/'results/flink-staged';out.mkdir(parents=True,exist_ok=True);started=time.time();data=tables();oracle=local_oracle(data);c=connect()
 te=TableEnvironment.create(EnvironmentSettings.in_batch_mode());cfg=te.get_config().get_configuration();cfg.set_string('pipeline.jars',';'.join(p.resolve().as_uri() for p in sorted(JARS.glob('*.jar'))));cfg.set_string('parallelism.default','2');cfg.set_string('rest.bind-address','127.0.0.1');cfg.set_string('rest.address','127.0.0.1')
 def options(table):
  esc=lambda v:v.replace("'","''")
  return f"'connector'='jdbc','url'='{esc(jdbc())}','table-name'='{table}','driver'='com.mysql.cj.jdbc.Driver','username'='{esc(os.getenv('MO_USER','root'))}','password'='{esc(os.getenv('MO_PASSWORD','111'))}'"
 for table in SCHEMAS:te.execute_sql(f'CREATE TABLE {table}({schema(table)}) WITH ({options(table)})')
 for b in BLOCKS:
  table='flink_features_'+b
  with c.cursor() as q:q.execute(f'CREATE TABLE IF NOT EXISTS {table}(cid INT,x DOUBLE,y DOUBLE,z DOUBLE)')
  te.execute_sql(f'CREATE TABLE staged_{b}(cid INT,x DOUBLE,y DOUBLE,z DOUBLE) WITH ({options(table)})')
  oracle.execute(f'CREATE TABLE staged_{b}(cid INT,x DOUBLE,y DOUBLE,z DOUBLE)')
 with c.cursor() as q:q.execute('CREATE TABLE IF NOT EXISTS flink_staged_output(cid INT,family VARCHAR(48),v DOUBLE)');q.execute('TRUNCATE TABLE flink_staged_output')
 te.execute_sql(f"CREATE TABLE final_sink(cid INT,family STRING,v DOUBLE) WITH ({options('flink_staged_output')})")
 jobs=[];counts={};block_checks=[]
 with (out/'cases.jsonl').open('w') as file:
  for j,f in enumerate([30,38]):
   t=time.perf_counter();family='long_chain_'+str(f);error=None;actual={}
   reference=sql_for(f,0,rows=True).replace('cid>=1 AND cid<91','cid>=1 AND cid<1001');expected_rows=oracle.execute(reference).fetchall();expected={r[0]:r[5] for r in expected_rows};assert len(expected)==1000
   try:
    selected,_=profile(f)
    for b in selected:
     table='flink_features_'+b
     with c.cursor() as q:q.execute(f'TRUNCATE TABLE {table}')
     base='WITH selected_customers AS (SELECT * FROM customers WHERE cid>=1 AND cid<1001),oo AS (SELECT o.* FROM orders o JOIN selected_customers c ON o.cid=c.cid WHERE o.day BETWEEN {d0} AND {d1}-1),ee AS (SELECT e.* FROM events e JOIN selected_customers c ON e.cid=c.cid WHERE e.day BETWEEN {d0} AND {d1}-1),'
     sql=(base+BLOCKS[b]+' SELECT cid,x,y,z FROM '+OUTPUT[b]).format(**parameters(0));expected_block=oracle.execute(sql+' ORDER BY cid').fetchall()
     oracle.execute(f'DELETE FROM staged_{b}')
     if expected_block:oracle.executemany(f'INSERT INTO staged_{b} VALUES(?,?,?,?)',expected_block)
     view=f'block_{j}_{b}';te.create_temporary_view(view,te.sql_query(quote(sql)))
     te.execute_sql(f'INSERT INTO staged_{b} SELECT cid,CAST(x AS DOUBLE),CAST(y AS DOUBLE),CAST(z AS DOUBLE) FROM {view}').wait(180000)
     with c.cursor() as q:q.execute(f'SELECT cid,x,y,z FROM {table} ORDER BY cid');actual_block=q.fetchall()
     ok=equal(expected_block,actual_block);block_checks.append({'pipeline':family,'block':b,'rows':len(actual_block),'status':'pass' if ok else 'mismatch'})
     if not ok:raise AssertionError('block mismatch '+b)
     print(family,'block',b,len(actual_block),'pass',flush=True)
    final=sql_for(f,0,rows=True,materialized=True).replace('cid>=1 AND cid<91','cid>=1 AND cid<1001')
    final=final[:final.rfind('SELECT cid,tier,region,score,')]+', pipeline_metric AS ('+final[final.rfind('SELECT cid,tier,region,score,'):].replace(' ORDER BY cid','')+') SELECT cid,weighted v FROM pipeline_metric'
    assert equal(sorted(expected.items()),oracle.execute(final+' ORDER BY cid').fetchall()),'staging altered reference semantics'
    view=f'final_{j}';te.create_temporary_view(view,te.sql_query(quote(final)));te.execute_sql(f"INSERT INTO final_sink SELECT cid,'{family}',CAST(v AS DOUBLE) FROM {view}").wait(180000)
    with c.cursor() as q:q.execute('SELECT cid,v FROM flink_staged_output WHERE family=%s ORDER BY cid',(family,));r=q.fetchall()
    actual=dict(r);assert len(actual)==len(r),'duplicate output'
   except Exception as exc:error=str(exc)
   jobs.append({'family':family,'pipeline_ms':(time.perf_counter()-t)*1000,'error':error,'groups_returned':len(actual)})
   for cid in range(1,1001):
    status='pipeline_error' if error else 'missing_output' if cid not in actual else 'pass' if equal([[expected[cid]]],[[actual[cid]]]) else 'mismatch';counts[status]=counts.get(status,0)+1
    row={'case_id':j*1000+cid-1,'family':family,'cid':cid,'status':status,'expected':plain(expected[cid]),'actual':plain(actual.get(cid))}
    if error:row['error']=error[:5000]
    file.write(json.dumps(row)+'\n')
   file.flush();print(family,'final',len(actual),'error',error[:1000] if error else None,flush=True)
 (out/'jobs.json').write_text(json.dumps(jobs,indent=2));(out/'block-checks.json').write_text(json.dumps(block_checks,indent=2));(out/'meta.json').write_text(json.dumps({'tool':'flink-staged','cases':2000,'pipelines':2,'counts':counts,'seconds':time.time()-started,'started_at':started,'ended_at':time.time(),'scope':'Flink feature blocks -> MO JDBC materialization -> dependent normalization/feedback chain -> MO JDBC sink; same program checked against unmaterialized DuckDB SQL; excluded from canonical 10000'},indent=2));c.close();oracle.close()
if __name__=='__main__':main()
