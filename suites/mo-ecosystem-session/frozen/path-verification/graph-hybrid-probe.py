import json,traceback,time
from pathlib import Path
import pymysql
out={'matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','cases':[]}
with pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True) as d:
 with d.cursor() as c:
  c.execute('CREATE DATABASE graph_audit');c.execute('USE graph_audit')
  c.execute('CREATE TABLE vertices(id BIGINT PRIMARY KEY, name VARCHAR(100))')
  c.execute('CREATE TABLE edges(src BIGINT,dst BIGINT)')
  c.execute("INSERT INTO vertices VALUES(1,'root'),(2,'a'),(3,'b'),(4,'c')")
  c.execute('INSERT INTO edges VALUES(1,2),(2,3),(3,2),(3,4)')
  c.execute('CREATE TABLE docs(id BIGINT PRIMARY KEY, content TEXT, embedding VECF32(3))')
  c.execute("INSERT INTO docs VALUES(2,'database graph lakehouse','[1,0,0]'),(3,'graph processing','[0,1,0]'),(4,'lakehouse analytics','[0,0,1]')")
  c.execute('CREATE FULLTEXT INDEX ft ON docs(content)')
  probes=[('bounded-recursive-graph-traversal',"WITH RECURSIVE reach(node,depth) AS (SELECT dst,1 FROM edges WHERE src=1 UNION ALL SELECT e.dst,r.depth+1 FROM edges e JOIN reach r ON e.src=r.node WHERE r.depth<3) SELECT DISTINCT node FROM reach ORDER BY node",[(2,),(3,),(4,)]),('graph-join-fulltext-vector',"SELECT d.id FROM edges e JOIN docs d ON d.id=e.dst WHERE e.src=1 AND MATCH(d.content) AGAINST('+lakehouse' IN BOOLEAN MODE) ORDER BY L2_DISTANCE(d.embedding,'[1,0,0]') LIMIT 1",[(2,)])]
  for name,sql,expected in probes:
   r={'name':name,'sql':sql}
   try:c.execute(sql);actual=c.fetchall();r.update(actual=actual,expected=expected,status='passed' if list(actual)==expected else 'failed')
   except Exception as e:r.update(status='failed',error=str(e))
   out['cases'].append(r)
  for name,sql in [('property-graph-ddl', 'CREATE PROPERTY GRAPH g VERTEX TABLES (vertices KEY (id)) EDGE TABLES (edges SOURCE KEY (src) REFERENCES vertices(id) DESTINATION KEY (dst) REFERENCES vertices(id))'),('sql-pgq-query', 'SELECT * FROM GRAPH_TABLE(g MATCH (a)-[e]->(b) COLUMNS(a.id,b.id))'),('cypher-query','MATCH (a)-[e]->(b) RETURN a,b')]:
   r={'name':name,'sql':sql}
   try:c.execute(sql);r.update(status='accepted',actual=c.fetchall())
   except Exception as e:r.update(status='unsupported-probe',error=str(e))
   out['cases'].append(r)
  c.execute('SET experimental_hnsw_index=1')
  c.execute('CREATE TABLE vectors(id BIGINT PRIMARY KEY,v VECF32(3))')
  c.execute("INSERT INTO vectors VALUES(1,'[0,0,0]'),(2,'[1,1,1]')")
  try:
   c.execute("CREATE INDEX h USING HNSW ON vectors(v) OP_TYPE 'vector_l2_ops'")
   c.execute("SELECT index_table_name FROM mo_catalog.mo_indexes WHERE name='h' AND algo='hnsw' AND algo_table_type='hnsw_meta' AND table_id IN(SELECT rel_id FROM mo_catalog.mo_tables WHERE reldatabase='graph_audit' AND relname='vectors') LIMIT 1")
   meta=c.fetchone()[0];deadline=time.monotonic()+60
   while True:
    c.execute(f'SELECT COUNT(*) FROM graph_audit.`{meta}`');n=c.fetchone()[0]
    if n:break
    if time.monotonic()>deadline:raise TimeoutError('HNSW metadata not published in 60 seconds')
    time.sleep(1)
   q="SELECT id FROM vectors ORDER BY L2_DISTANCE(v,'[0,0,0]') LIMIT 1"
   c.execute(q);actual=c.fetchall();c.execute('EXPLAIN '+q);plan=[str(r) for r in c.fetchall()]
   out['cases'].append({'name':'hnsw-async-publish-and-query','status':'passed' if actual==((1,),) and any('hnsw_search' in p.lower() for p in plan) else 'failed','actual':actual,'plan':plan,'experimental':True})
  except Exception as e:out['cases'].append({'name':'hnsw-async-publish-and-query','status':'failed','error':str(e)})
Path('graph-hybrid-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
