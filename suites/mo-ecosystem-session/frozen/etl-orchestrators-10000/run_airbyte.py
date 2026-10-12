import sys,pathlib,json,subprocess,time,datetime,collections,hashlib
B=pathlib.Path(__file__).resolve().parent;A=B/'airbyte';A.mkdir(exist_ok=True);sys.path.insert(0,str(B));from codec import canon
import pymysql
D=['env','-u','DOCKER_HOST','-u','DOCKER_CONTEXT','-u','DOCKER_TLS','-u','DOCKER_TLS_VERIFY','-u','DOCKER_CERT_PATH','docker','--host=unix:///var/run/docker.sock'];cs=json.loads((B/'fixtures.json').read_text());db=pymysql.connect(host='127.0.0.1',port=13306,user='root',password='types-local',database='orchestrator10000',charset='utf8mb4',autocommit=True,read_timeout=90)
seq=0;events=[]
with db.cursor() as cur:
 cur.execute('CREATE TABLE IF NOT EXISTS airbyte_events(event_seq BIGINT PRIMARY KEY,case_id BIGINT,row_id BIGINT,profile VARCHAR(32),payload TEXT,deleted BOOLEAN)');cur.execute('DELETE FROM airbyte_events')
 for c in cs:
  cid=c['logical_case_id'];p=c['profile'];cur.execute('SELECT case_id,id,v,label,rev FROM dbt_'+p+' WHERE case_id=%s ORDER BY id',(cid,));rows=canon(cur.fetchall(),p)
  if c['scenario']=='native_transform':rows=[[r[0],r[1],r[2],r[3]+'→ETL'+str(c['seed']),r[4]+c['seed']+1] for r in rows if r[1]%2==c['seed']%2]
  for r in rows:seq+=1;events.append([seq,cid,r[1],p,json.dumps(r,ensure_ascii=False,separators=(',',':')),False])
  if c['scenario']=='staging_merge':
   cur.execute('SELECT case_id,id,v,label,rev FROM dbt_delta_'+p+' WHERE case_id=%s ORDER BY id',(cid,));changes=canon(cur.fetchall(),p)
   for r in changes:seq+=1;events.append([seq,cid,r[1],p,json.dumps(r,ensure_ascii=False,separators=(',',':')),False])
  if c['scenario']=='tombstone_delete':
   for rid in c['dead']:seq+=1;events.append([seq,cid,rid,p,'null',True])
 cur.executemany('INSERT INTO airbyte_events VALUES(%s,%s,%s,%s,%s,%s)',events)
db.close();(A/'fixture-receipt.json').write_text(json.dumps({'events':len(events),'cases':len(cs),'mapping':'Source typed native SQL rows -> canonical lossless STRING envelope plus event sequence/delete flag; explicit outbox, not native CDC delete. FLOAT32 six significant digits/CHAR trailing trim semantics match first matrix.','profiles':list(dict.fromkeys(c['profile'] for c in cs))},indent=2))
config={'host':'172.17.0.1','port':13306,'database':'orchestrator10000','username':'root','password':'types-local','replication_method':{'method':'STANDARD'},'ssl_mode':{'mode':'preferred'},'tunnel_method':{'tunnel_method':'NO_TUNNEL'},'table_filters':[{'database_name':'orchestrator10000','table_name_patterns':['airbyte_events']}],'checkpoint_target_interval_seconds':5}
(A/'source.json').write_text(json.dumps(config));
def run(image,args,output,input_file=None,name=None):
 name=name or 'mo-etl10000-'+output.stem
 cmd=D+['run','--rm','--name',name,'-i','-v',str(A)+':/config:ro',image]+args;start=time.monotonic()
 with output.open('w') as f:
  with input_file.open('r') if input_file else open('/dev/null') as inp:r=subprocess.run(cmd,stdin=inp,stdout=f,stderr=subprocess.STDOUT,timeout=600)
 receipt={'command':cmd,'exit_code':r.returncode,'elapsed_s':time.monotonic()-start,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()};(output.with_suffix('.receipt.json')).write_text(json.dumps(receipt,indent=2));print(output.name,r.returncode,flush=True)
 return r.returncode
run('airbyte/source-mysql:3.53.7',['discover','--config','/config/source.json'],A/'discover.jsonl')
msgs=[]
for l in (A/'discover.jsonl').read_text().splitlines():
 try:msgs.append(json.loads(l))
 except ValueError:pass
cat=next(x['catalog'] for x in msgs if x.get('type')=='CATALOG');stream=next(x for x in cat['streams'] if x['name']=='airbyte_events');configured={'streams':[{'stream':stream,'sync_mode':'full_refresh','destination_sync_mode':'append'}]};(A/'catalog-source.json').write_text(json.dumps(configured))
run('airbyte/source-mysql:3.53.7',['read','--config','/config/source.json','--catalog','/config/catalog-source.json'],A/'read.jsonl')
records=[];states=[];errors=[]
for l in (A/'read.jsonl').read_text().splitlines():
 try:x=json.loads(l)
 except ValueError:continue
 if x.get('type')=='RECORD':records.append(x)
 if x.get('type')=='STATE':states.append(x)
 if x.get('type')=='TRACE' and x['trace']['type']=='ERROR':errors.append(x)
(A/'source-receipt.json').write_text(json.dumps({'expected_records':len(events),'actual_records':len(records),'states':len(states),'errors':errors},indent=2));assert len(records)==len(events) and states and not errors
for engine,port,password in [('mo',6001,'111'),('mysql',13306,'types-local')]:
 ns='airbyte10k_'+engine
 d=pymysql.connect(host='127.0.0.1',port=port,user='root',password=password,autocommit=True)
 with d.cursor() as cur:cur.execute('CREATE DATABASE IF NOT EXISTS '+ns)
 d.close()
 dest={'host':'172.17.0.1','port':port,'username':'root','password':password,'database':ns,'ssl':False,'raw_data_schema':ns,'tunnel_method':{'tunnel_method':'NO_TUNNEL'}};(A/f'dest-{engine}.json').write_text(json.dumps(dest));catalog=json.loads(json.dumps(configured));catalog['streams'][0]['stream']['namespace']=ns;(A/f'catalog-{engine}.json').write_text(json.dumps(catalog));protocol=[]
 for item in records:
  copy=json.loads(json.dumps(item));copy['record']['namespace']=ns;protocol.append(copy)
 # Use a runner-owned global state; its acknowledgement is evidence for this destination only.
 protocol.append({'type':'STATE','state':{'data':{'runner':'etl10000','expected_records':len(records),'end':True}}});(A/f'protocol-{engine}.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in protocol))
 run('airbyte/destination-mysql:1.1.1',['write','--config',f'/config/dest-{engine}.json','--catalog',f'/config/catalog-{engine}.json'],A/f'write-{engine}.jsonl',A/f'protocol-{engine}.jsonl')
