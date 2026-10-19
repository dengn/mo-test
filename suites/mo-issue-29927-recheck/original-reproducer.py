import sys,time,json,threading,concurrent.futures,collections,math
from pathlib import Path
import pymysql,types
DB='index_race_repro_'+str(int(time.time()))
boot=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True,ssl_disabled=True)
with boot.cursor() as cur:cur.execute('create database '+DB)
boot.close()
def connect(engine='mo',timeout=20):
 c=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database=DB,autocommit=True,ssl_disabled=True,read_timeout=timeout)
 for sql in ['set experimental_hnsw_index=1','set experimental_fulltext2_index=1','set hnsw_threads_search=1','set probe_limit=128']:
  with c.cursor() as cur:cur.execute(sql)
 return c
def query(c,sql,params=None):
 with c.cursor() as cur:
  cur.execute(sql,params or None)
  return cur.fetchall() if cur.description else []
b=types.SimpleNamespace(connect=connect,query=query,norm=lambda x:x)

P=Path.cwd()/'index-race-output';P.mkdir(exist_ok=True);stop=threading.Event();mutex=threading.Lock();ack=[];errors=collections.Counter();counter=iter(range(1001,1000000));cases=[]
def vec(i):return json.dumps([((i*17+k*11)%101-50)/10 for k in range(64)])
c=b.connect('mo',timeout=180)
for t in ['race_h','race_i']:b.query(c,f'create table {t}(id bigint primary key,n bigint,v vecf32(64))')
for t in ['race_ft','race_ft2']:b.query(c,f'create table {t}(id bigint primary key,n bigint,body text)')
for t in ['race_h','race_i']:
 with c.cursor() as q:q.executemany(f'insert into {t} values(%s,%s,%s)',[(i,i*3,vec(i)) for i in range(1,501)])
for t in ['race_ft','race_ft2']:
 with c.cursor() as q:q.executemany(f'insert into {t} values(%s,%s,%s)',[(i,i*3,'racealpha beta token'+str(i)) for i in range(1,501)])
b.query(c,"create index ann using hnsw on race_h(v) op_type 'vector_l2_ops'");b.query(c,"create index ann using ivfflat on race_i(v) lists=16 op_type 'vector_l2_ops'");b.query(c,'create fulltext index txt on race_ft(body)');b.query(c,'create fulltext2 index txt on race_ft2(body)');c.close()
def writer(worker):
 c=b.connect('mo',timeout=20);tables=['race_h','race_i','race_ft','race_ft2'];t=tables[worker%4]
 try:
  while not stop.is_set():
   with mutex:i=next(counter)
   try:
    b.query(c,f'insert into {t} values(%s,%s,%s)',[i,i*3,vec(i) if t.startswith('race_h') or t.startswith('race_i') else 'racealpha beta token'+str(i)])
    with mutex:ack.append((t,i,i*3))
   except Exception as e:
    with mutex:errors['write:'+str(e.args[0])]+=1
 except Exception as e:
  with mutex:errors['writer_disconnect:'+str(e.args[0])]+=1
 finally:c.close()
def reader(worker):
 c=b.connect('mo',timeout=20)
 try:
  while not stop.is_set():
   try:
    if worker%4<2:
     t='race_h' if worker%4==0 else 'race_i';v=vec(worker+37);b.query(c,f'select id,l2_distance(v,%s) from {t} where n>=0 order by l2_distance(v,%s) limit 10',[v,v])
    elif worker%4==2:b.query(c,"select id from race_ft where match(body) against('+racealpha +beta' in boolean mode) order by id limit 50")
    else:b.query(c,"with a as(select id,n from race_ft2 where match(body) against('racealpha' in boolean mode)) select count(*),sum(n) from a")
   except Exception as e:
    with mutex:errors['read:'+str(e.args[0])]+=1
 finally:c.close()
ops=["alter table race_h alter reindex ann hnsw force_sync","alter table race_i alter reindex ann ivfflat lists=16","alter table race_ft2 alter reindex txt fulltext2 merge force_sync","create index ridx_{i} on race_h(n)","create index ridx_{i} on race_ft(n)"]
with concurrent.futures.ThreadPoolExecutor(40) as ex:
 futures=[ex.submit(writer,w) for w in range(8)]+[ex.submit(reader,w) for w in range(24)];time.sleep(1)
 def ddl(i):
  c=b.connect('mo',timeout=90);t=time.monotonic();sql=ops[i%5].format(i=i);err=None
  try:
   b.query(c,sql)
   if i%5==3:b.query(c,f'drop index ridx_{i} on race_h')
   if i%5==4:b.query(c,f'drop index ridx_{i} on race_ft')
  except Exception as e:err=str(e)
  finally:c.close()
  return {'id':f'R{i+1:03d}','sql':sql,'error':err,'seconds':time.monotonic()-t}
 for row in ex.map(ddl,range(25)):
  cases.append(row);print(json.dumps(row),flush=True)
 stop.set()
 for f in futures:f.result()
c=b.connect('mo',timeout=120);missing=[];corrupt=[]
for table in ['race_h','race_i','race_ft','race_ft2']:
 stored=dict(b.query(c,f'select id,n from {table} where id>=1001'))
 for t,i,n in ack:
  if t!=table:continue
  if i not in stored:missing.append((t,i))
  elif stored[i]!=n:corrupt.append((t,i))
counts={t:b.norm(b.query(c,f'select count(*) from {t}')) for t in ['race_h','race_i','race_ft','race_ft2']}
fts={}
for t in ['race_ft','race_ft2']:
 try:fts[t]=b.norm(b.query(c,f"select count(*) from {t} where match(body) against('racealpha' in boolean mode)"))
 except Exception as e:fts[t]=str(e)
c.close();summary={'ddl_cases':cases,'concurrency':32,'acknowledged_writes':len(ack),'missing':missing,'corrupt':corrupt,'client_errors':errors,'source_counts':counts,'fulltext_counts':fts,'ft2_visibility_note':'Post-index DML is asynchronous; a stale FT2 query snapshot is a freshness observation, not durable data loss.'};(P/'index-race-ledger.json').write_text(json.dumps(ack));(P/'index-race.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False));print(json.dumps({k:v for k,v in summary.items() if k!='ddl_cases'}),flush=True)

c=connect(timeout=90)
for sql,params in [('show create table race_h',None),('insert into race_h values(%s,%s,%s)',[99000002,297000006,json.dumps([1.0]*64)]),('alter table race_h alter reindex ann hnsw force_sync',None)]:
 try:print('POST_LOAD',sql,query(c,sql,params))
 except Exception as e:print('POST_LOAD',sql,str(e))
c.close()

