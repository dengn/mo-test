import json,time,pymysql
for i in range(120):
 try:
  c=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True,connect_timeout=3,read_timeout=180)
  with c.cursor() as q:q.execute('SELECT 1');assert q.fetchone()==(1,)
  break
 except Exception:
  if i==119:raise
  time.sleep(1)
with c.cursor() as q:
 q.execute('CREATE DATABASE mo_stress');q.execute('USE mo_stress')
 q.execute('CREATE TABLE items(id BIGINT PRIMARY KEY, grp INT, value BIGINT, payload VARCHAR(1024))')
 q.execute('CREATE TABLE accounts(id BIGINT PRIMARY KEY, balance BIGINT)')
 q.execute('CREATE TABLE events(id BIGINT PRIMARY KEY, grp INT, payload VARCHAR(256))')
 for lower in range(1,2000001,100000):
  t=time.time()
  q.execute(f"INSERT INTO items SELECT result,result%1000,result%100000,repeat(md5(cast(result AS varchar)),32) FROM generate_series({lower},{lower+99999}) g")
  print(json.dumps({'rows_seeded':lower+99999,'batch_seconds':time.time()-t}),flush=True)
 q.execute('INSERT INTO accounts SELECT result,100000 FROM generate_series(1,10000) g')
 q.execute('SELECT COUNT(*),SUM(id),SUM(length(payload)) FROM items');print(json.dumps({'seed_integrity':[int(x) for x in q.fetchone()]}),flush=True)
c.close()
