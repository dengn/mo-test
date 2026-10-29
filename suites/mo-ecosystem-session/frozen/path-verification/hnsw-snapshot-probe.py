import json,time,traceback
from pathlib import Path
import pymysql
out={'experimental':True,'cases':[]}
d=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True)
snapshot=False
try:
 with d.cursor() as c:
  c.execute('USE graph_audit');c.execute('SET experimental_hnsw_index=1')
  c.execute("SELECT index_table_name FROM mo_catalog.mo_indexes WHERE name='h' AND algo='hnsw' AND algo_table_type='hnsw_meta' AND table_id IN(SELECT rel_id FROM mo_catalog.mo_tables WHERE reldatabase='graph_audit' AND relname='vectors') LIMIT 1");meta=c.fetchone()[0]
  c.execute(f'SELECT MIN(checksum) FROM `{meta}`');baseline=c.fetchone()[0]
  c.execute('CREATE SNAPSHOT graph_audit_snapshot FOR ACCOUNT');snapshot=True
  c.execute("INSERT INTO vectors VALUES(3,'[0.01,0.01,0.01]')")
  deadline=time.monotonic()+60
  while True:
   c.execute(f'SELECT COUNT(*) FROM `{meta}` WHERE checksum<>%s',(baseline,))
   if c.fetchone()[0]>0:break
   if time.monotonic()>deadline:raise TimeoutError('HNSW insert not published within 60 seconds')
   time.sleep(1)
  probes=[('hnsw-current-generation',"SELECT id FROM vectors ORDER BY L2_DISTANCE(v,'[0.01,0.01,0.01]') LIMIT 1",3),('snapshot-exact-knn',"SELECT id FROM vectors {snapshot='graph_audit_snapshot'} ORDER BY L2_DISTANCE(v,'[0.01,0.01,0.01]') LIMIT 1 BY RANK WITH OPTION 'mode=force'",1),('snapshot-historical-hnsw',"SELECT id FROM vectors {snapshot='graph_audit_snapshot'} ORDER BY L2_DISTANCE(v,'[0.01,0.01,0.01]') LIMIT 1",1)]
  for name,q,expected in probes:
   c.execute(q);actual=c.fetchall();r={'name':name,'actual':actual,'expected':[[expected]],'status':'passed' if actual==((expected,),) else 'failed'}
   if name=='snapshot-historical-hnsw':
    c.execute('EXPLAIN '+q);r['plan']=[str(x) for x in c.fetchall()]
    if not any('hnsw_search' in x.lower() for x in r['plan']):r['status']='failed'
   out['cases'].append(r)
 out['status']='passed' if all(x['status']=='passed' for x in out['cases']) else 'failed'
except Exception as e:out.update(status='failed',error=str(e));traceback.print_exc()
finally:
 if snapshot:
  with d.cursor() as c:c.execute('DROP SNAPSHOT graph_audit_snapshot')
 d.close()
 Path('hnsw-snapshot-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
