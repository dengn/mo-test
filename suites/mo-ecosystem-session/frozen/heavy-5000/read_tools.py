import sys,pathlib,decimal,time,json,collections,concurrent.futures,hashlib,datetime,traceback,argparse
sys.path.append('/workspace/toolchains/python/lib/python3.12/site-packages')
from heavy import *
P=argparse.ArgumentParser();P.add_argument('--tool',choices=['connectorx','ibis','odbc','matrixone_sdk','jdbc'],required=True);P.add_argument('--workers',type=int,default=4);a=P.parse_args();scenes=['ordered_full','parallel_partition','keyset_pages','filter_nulls','group_null_counts','self_join','union_replay','window_topk','reused_query_context','stream_batches'];out=B/'reader-results';out.mkdir(exist_ok=True);path=out/(a.tool+'.jsonl');done={json.loads(l)['id'] for l in path.read_text().splitlines()} if path.exists() else set();counts=collections.Counter(json.loads(l)['status'] for l in path.read_text().splitlines()) if path.exists() else collections.Counter();start=time.monotonic()
JVM_LOCK=threading.Lock()
CLIENTS=threading.local()
def query(q,port,mode='normal'):
 if a.tool in ['odbc','matrixone_sdk','jdbc']:
  if not hasattr(CLIENTS,'connections'):CLIENTS.connections={}
  if port not in CLIENTS.connections:
   if a.tool=='matrixone_sdk':
    sys.path.insert(0,'/workspace/matrixone/clients/python');from matrixone import Client
    c=Client();c.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='heavy5000',ssl_mode='disabled',on_connect=[])
   elif a.tool=='odbc':
    import pyodbc
    driver='MatrixOne ODBC 9.7 Unicode Driver'
    c=pyodbc.connect(f'DRIVER={{{driver}}};SERVER=127.0.0.1;PORT={port};UID=root;PWD={"111" if port==6001 else "types-local"};DATABASE=heavy5000;SSLMODE=DISABLED;CHARSET=utf8mb4',autocommit=True)
   else:
    import jaydebeapi,jpype
    with JVM_LOCK:
     if not jpype.isJVMStarted():jpype.startJVM(jpype.getDefaultJVMPath(),'-Xmx384m','-XX:ActiveProcessorCount=4',classpath=['/workspace/work/path-verification/jars/mysql-jdbc.jar'],convertStrings=True)
    c=jaydebeapi.connect('com.mysql.cj.jdbc.Driver',f'jdbc:mysql://127.0.0.1:{port}/heavy5000?useSSL=false&characterEncoding=utf8&serverTimezone=UTC',{'user':'root','password':'111' if port==6001 else 'types-local'})
   CLIENTS.connections[port]=c
  c=CLIENTS.connections[port]
  if a.tool=='matrixone_sdk':return [list(r) for r in c.execute(q,log_mode='off').rows]
  cursor=c.cursor()
  try:cursor.execute(q);return [list(r) for r in cursor.fetchall()]
  finally:cursor.close()
 if a.tool=='connectorx':
  import connectorx as cx
  t=cx.read_sql(f'mysql://root:{"111" if port==6001 else "types-local"}@127.0.0.1:{port}/heavy5000',q,return_type='arrow')
  return [[r[k] for k in t.column_names] for r in t.to_pylist()]
 import ibis
 con=ibis.mysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='heavy5000')
 try:
  table=con.sql(q)
  if mode=='stream':
   batches=table.to_pyarrow_batches(chunk_size=31);rs=[]
   for t in batches:
    rs.extend([[r[k] for k in t.schema.names] for r in t.to_pylist()])
   return rs
  t=table.to_pyarrow();return [[r[k] for k in t.column_names] for r in t.to_pylist()]
 finally:con.disconnect()
def wire_expr(p,prefix='b.'):
 v=prefix+'v';name=p['name']
 if name in ['varbinary','blob']:return 'HEX('+v+')'
 if name=='bit64':return 'CAST(CAST('+v+' AS UNSIGNED) AS CHAR)'
 if name in ['double','float32']:return v
 return 'CAST('+v+' AS CHAR)'
def decode(v,p):
 if v is None:return None
 n=p['name']
 if n.startswith('decimal'):return decimal.Decimal(v)
 if n in ['tinyint','smallint','int32','int64','uint64','bit64']:return int(v)
 if n in ['varbinary','blob']:return bytes.fromhex(v)
 if n=='boolean':return bool(int(v))
 if n=='date':return datetime.date.fromisoformat(v)
 if n=='datetime6':return datetime.datetime.fromisoformat(v)
 if n=='time6':
  neg=v.startswith('-');v=v.lstrip('-');hh,mm,ss=v.split(':');sec=decimal.Decimal(ss);return datetime.timedelta(microseconds=int((decimal.Decimal(hh)*3600+int(mm)*60+sec)*1000000))*(-1 if neg else 1)
 return v
# Actual typed source rows from the first preflight remain in old preserved namespace; no new writes.
sources={}
for pi,p in enumerate(PROFILES):
 cid=100000+caseid(pi,0,0)
 for port in [6001,13306]:
  rs=sql('SELECT case_id,id,v,label,rev FROM t_petl_'+p['name']+' WHERE case_id=%s ORDER BY id',(cid,),port=port);assert len(rs)==32,(p['name'],port,len(rs));sources[(p['name'],port)]=rs
plan=[]
for pi,p in enumerate(PROFILES):
 for si,sc in enumerate(scenes):
  for seed in range(10):
   for port in [6001,13306]:plan.append({'id':f'{a.tool}_{p["name"]}_{sc}_{seed}_{port}','profile':p['name'],'scenario':sc,'seed':seed,'port':port,'pi':pi,'si':si})
dump(out/(a.tool+'-case-plan.json'),{'planned':5000,'definition':'25 native SQL source datatype profiles x10 reader-specific complex query scenarios x10seeds x2endpoints; explicit source CAST/HEX representation to avoid known inference losses; native connector read APIs; notnativealltypesmappingcertification','cases':plan})
def execute(spec):
 decimal.getcontext().prec=100;p=PROFILES[spec['pi']];port=spec['port'];seed=spec['seed'];sc=spec['scenario'];cid=caseid(spec['pi'],spec['si'],seed);sourcecid=100000+caseid(spec['pi'],0,0);N=[32,64,128,64,256,32,128,256,64,128][seed];k=N//32;t='t_petl_'+p['name'];reps=' UNION ALL '.join('SELECT '+str(j)+' AS r' for j in range(k));expr=wire_expr(p)
 base=f'SELECT {cid} AS case_id,b.id+r.r*32 AS id,{expr} AS v,b.label,b.rev FROM {t} AS b CROSS JOIN ({reps}) AS r WHERE b.case_id={sourcecid}';q='SELECT * FROM ('+base+') AS x';expected=[[cid,int(row[1])+j*32,row[2],row[3],row[4]] for j in range(k) for row in sources[(p['name'],port)]];r=dict(spec,tool=a.tool,input_virtual_rows=N,query_scope='Native typed source with explicit exact-text/hex projection,real component read API; read-specificcases,noCDC/write/EOSclaim');s=time.monotonic()
 try:
  if sc=='filter_nulls':q+=' WHERE MOD(id,3)='+str(seed%3)+' AND v IS NOT NULL';expected=[r for r in expected if r[1]%3==seed%3 and r[2] is not None]
  if sc=='self_join':q=f'SELECT x.case_id,x.id,x.v,x.label,x.rev FROM ({base}) AS x JOIN ({base}) AS y ON x.case_id=y.case_id AND x.id=y.id'
  if sc=='union_replay':q=f'SELECT * FROM ({base}) AS x UNION ALL SELECT * FROM ({base}) AS y';expected+=list(expected)
  if sc=='window_topk':
   top=seed%3+1;q=f'SELECT case_id,id,v,label,rev FROM (SELECT x.*,ROW_NUMBER() OVER(PARTITION BY MOD(id,4) ORDER BY id DESC) AS rn FROM ({base}) AS x) AS ranked WHERE rn<={top}';expected=[r for r in expected if ((N-1-r[1])//4)<top]
  if sc=='reused_query_context':q=f'SELECT case_id,id,v,CONCAT(label,\'/ctx{seed}\') AS label,rev+{seed} AS rev FROM ({base}) AS x';expected=[[r[0],r[1],r[2],r[3]+'/ctx'+str(seed),r[4]+seed] for r in expected]
  if sc=='group_null_counts':
   q=f'SELECT MOD(id,4) AS bucket,COUNT(*) AS n,SUM(CASE WHEN v IS NULL THEN 1 ELSE 0 END) AS missing FROM ({base}) AS x GROUP BY MOD(id,4) ORDER BY bucket';want=[[i,sum(r[1]%4==i for r in expected),sum(r[1]%4==i and r[2] is None for r in expected)] for i in range(4)];actual=query(q,port);actual=[[int(v) for v in row] for row in actual];e=want;ac=actual
  else:
   actual=[]
   if sc=='keyset_pages':
    for after in range(0,N,31):actual+=query(q+f' WHERE id>={after} AND id<{after+31} ORDER BY id',port)
   elif sc=='parallel_partition':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     f=[pool.submit(query,q+f' WHERE MOD(id,2)={i} ORDER BY id',port) for i in range(2)]
     for fut in f:actual+=fut.result()
   else:actual=query(q,port,'stream' if sc=='stream_batches' else 'normal')
   actual=[[r[0],r[1],decode(r[2],p),r[3],r[4]] for r in actual];ac=canon(actual,p);e=canon(expected,p)
  r.update(status='passed' if ac==e else 'fidelity_failed',expected_rows=len(e),actual_rows=len(ac),expected_sha256=sha(e),actual_sha256=sha(ac))
  if ac!=e:r.update(expected_sample=e[:2],actual_sample=ac[:2])
 except Exception as e:r.update(status='execution_failed',error=repr(e)[:1200],traceback=traceback.format_exc()[-2400:])
 r['elapsed_s']=time.monotonic()-s;return r
with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
 for pi,p in enumerate(PROFILES):
  pending=[s for s in plan if s['pi']==pi and s['id'] not in done];jobs=[pool.submit(execute,s) for s in pending]
  for f in concurrent.futures.as_completed(jobs):
   r=f.result()
   with path.open('a') as handle:handle.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
   done.add(r['id']);counts[r['status']]+=1
   if r['status']!='passed':print('FAIL',r['id'],r.get('error','')[:160],flush=True)
   if len(done)%100==0:dump(out/(a.tool+'-progress.json'),{'completed':len(done),'planned':5000,'counts':dict(counts),'elapsed_s':time.monotonic()-start,'resources':resources()});print('PROGRESS',a.tool,len(done),dict(counts),flush=True)
dump(out/(a.tool+'-completion.json'),{'completed':len(done),'counts':dict(counts),'scope':'Native read-only component APIs against previously generatedcurrentroundtyped source; querycomplexityand32-256virtualrows percase; notwrite/scenario simulation or nativeexactlyonce'});print('COMPLETE',a.tool,len(done),dict(counts),flush=True)
