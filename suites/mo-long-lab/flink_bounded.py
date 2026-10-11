"""Materialize feature blocks AND feedback chunks to bound client planning."""
import json,time
from flink_staged import quote,ROOT,tables,local_oracle,connect,BLOCKS,OUTPUT,profile,parameters,sql_for,equal,plain,jdbc,schema,JARS,SCHEMAS,os,EnvironmentSettings,TableEnvironment

def main():
 out=ROOT/'results/flink-bounded';out.mkdir(parents=True,exist_ok=True);started=time.time();oracle=local_oracle(tables());c=connect()
 te=TableEnvironment.create(EnvironmentSettings.in_batch_mode());cfg=te.get_config().get_configuration()
 cfg.set_string('pipeline.jars',';'.join(p.resolve().as_uri() for p in sorted(JARS.glob('*.jar'))));cfg.set_string('parallelism.default','2');cfg.set_string('rest.bind-address','127.0.0.1');cfg.set_string('rest.address','127.0.0.1')
 def options(table):
  esc=lambda v:v.replace("'","''")
  return f"'connector'='jdbc','url'='{esc(jdbc())}','table-name'='{table}','driver'='com.mysql.cj.jdbc.Driver','username'='{esc(os.getenv('MO_USER','root'))}','password'='{esc(os.getenv('MO_PASSWORD','111'))}'"
 for table in SCHEMAS:te.execute_sql(f'CREATE TABLE {table}({schema(table)}) WITH ({options(table)})')
 cols=['cid','tier','region']+[f'f{k}' for k in range(1,25)]+['score'];colstr=','.join(cols)
 ddl=','.join(k+(' INT' if k in cols[:3] else ' DOUBLE') for k in cols)
 checks=[];jobs=[];counts={};sequence=0
 def register(name,definition):
  with c.cursor() as q:q.execute(f'CREATE TABLE IF NOT EXISTS {name}({definition})')
  te.execute_sql(f'CREATE TABLE {name}({definition}) WITH ({options(name)})');oracle.execute(f'CREATE TABLE {name}({definition})')
 for b in BLOCKS:register('staged_'+b,'cid INT,x DOUBLE,y DOUBLE,z DOUBLE')
 for name in ['score_a','score_b']:register(name,ddl)
 def execute(sql,target,tag):
  nonlocal sequence
  expected=oracle.execute(sql+' ORDER BY cid').fetchall()
  oracle.execute(f'DELETE FROM {target}')
  if expected:oracle.executemany(f'INSERT INTO {target} VALUES('+','.join('?' for _ in expected[0])+')',expected)
  with c.cursor() as q:q.execute(f'TRUNCATE TABLE {target}')
  view='bounded_view_'+str(sequence);sequence+=1;te.create_temporary_view(view,te.sql_query(quote(sql)));te.execute_sql(f'INSERT INTO {target} SELECT * FROM {view}').wait(180000)
  with c.cursor() as q:q.execute(f'SELECT * FROM {target} ORDER BY cid');actual=q.fetchall()
  ok=equal(expected,actual);checks.append({'step':tag,'rows':len(actual),'status':'pass' if ok else 'mismatch','sql':sql})
  (out/'step-checks.json').write_text(json.dumps(checks,indent=2))
  print(tag,len(actual),'pass' if ok else 'mismatch',flush=True)
  if not ok:raise AssertionError('intermediate mismatch '+tag)
  return actual
 with (out/'cases.jsonl').open('w') as file:
  for j,f in enumerate([30,38]):
   family='long_chain_'+str(f);t=time.perf_counter();error=None;actual={};selected,depth=profile(f);n=3*len(selected)
   reference=sql_for(f,0,rows=True).replace('cid>=1 AND cid<91','cid>=1 AND cid<1001');expected={r[0]:r[5] for r in oracle.execute(reference).fetchall()};assert len(expected)==1000
   try:
    for b in selected:
     base='WITH selected_customers AS (SELECT * FROM customers WHERE cid>=1 AND cid<1001),oo AS (SELECT o.* FROM orders o JOIN selected_customers c ON o.cid=c.cid WHERE o.day BETWEEN {d0} AND {d1}-1),ee AS (SELECT e.* FROM events e JOIN selected_customers c ON e.cid=c.cid WHERE e.day BETWEEN {d0} AND {d1}-1),'
     execute((base+BLOCKS[b]+' SELECT cid,CAST(x AS DOUBLE),CAST(y AS DOUBLE),CAST(z AS DOUBLE) FROM '+OUTPUT[b]).format(**parameters(0)),'staged_'+b,family+' block '+b)
    full=sql_for(f,0,rows=True,materialized=True).replace('cid>=1 AND cid<91','cid>=1 AND cid<1001')
    seed=full[:full.index(',\nfeedback_1 AS')]
    fields=['cid','tier','region']+[f'f{k}' if k<=n else f'CAST(0 AS DOUBLE) f{k}' for k in range(1,25)]+['score']
    execute(seed+' SELECT '+','.join(fields)+' FROM feedback_0','score_a',family+' seed')
    source='score_a'
    for start in range(1,depth+1,3):
     finish=min(depth,start+2);ctes=[];previous=source
     for k in range(start,finish+1):
      name='update_'+str(k);mix=f'CAST({.12+.01*(k%7):.4f} AS DOUBLE)*score+CAST({.003+.001*(k%5):.4f} AS DOUBLE)*LN(1+ABS(f{1+k%n}))'
      ctes.append(f'{name} AS (SELECT '+','.join(cols[:-1])+f',(score+1/(1+EXP(-LEAST(30,GREATEST(-30,{mix})))))/2 score FROM {previous})');previous=name
     target='score_b' if source=='score_a' else 'score_a'
     execute('WITH '+','.join(ctes)+' SELECT '+colstr+' FROM '+previous,target,family+f' feedback {start}-{finish}');source=target
    total='+'.join(f'f{k}' for k in range(1,n+1));week=(parameters(0)['d1']-1)//7
    final=f'SELECT s.cid,score*({total}) v FROM {source} s JOIN targets t ON s.tier=t.tier AND t.week={week}'
    assert equal(sorted(expected.items()),oracle.execute(final+' ORDER BY s.cid').fetchall()),'materialization altered reference semantics'
    sink='flink_bounded_output_'+str(f);register(sink,'cid INT,v DOUBLE');actual=dict(execute(final,sink,family+' final'))
   except Exception as exc:error=str(exc)
   jobs.append({'family':family,'pipeline_ms':(time.perf_counter()-t)*1000,'error':error,'groups_returned':len(actual)})
   for cid in range(1,1001):
    status='pipeline_error' if error else 'missing_output' if cid not in actual else 'pass' if equal([[expected[cid]]],[[actual[cid]]]) else 'mismatch';counts[status]=counts.get(status,0)+1
    row={'case_id':j*1000+cid-1,'family':family,'cid':cid,'status':status,'expected':plain(expected[cid]),'actual':plain(actual.get(cid))}
    if error:row['error']=error[:5000]
    file.write(json.dumps(row)+'\n')
   file.flush();print(family,'complete',len(actual),'error',error[:1000] if error else None,flush=True)
 (out/'jobs.json').write_text(json.dumps(jobs,indent=2));(out/'meta.json').write_text(json.dumps({'tool':'flink-bounded','cases':2000,'pipelines':2,'counts':counts,'seconds':time.time()-started,'started_at':started,'ended_at':time.time(),'feedback_chunk':3,'scope':'14 JDBC sources, each feature block materialized, independent normalization, feedback chunks of 3, final JDBC sink; all intermediate values and final unmaterialized reference verified; excluded from canonical 10000'},indent=2));c.close();oracle.close()
if __name__=='__main__':main()
