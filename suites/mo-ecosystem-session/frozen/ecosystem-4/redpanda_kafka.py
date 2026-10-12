from runtime import *
from kafka import KafkaProducer,KafkaConsumer
from kafka.admin import KafkaAdminClient,NewTopic
from kafka.structs import TopicPartition
import sys
resume="--resume" in sys.argv
exe=str(B/'redpanda-connect/redpanda-connect');topic='eco4_rpc_stream';group=lambda p:f'eco4-rpc-{p}'
admin=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092');(None if resume else admin.create_topics([NewTopic(topic,1,1),NewTopic('eco4-rpc-dlq-6001',1,1),NewTopic('eco4-rpc-dlq-13306',1,1)]));admin.close()
producer=KafkaProducer(bootstrap_servers='127.0.0.1:19092',acks='all');procs={};expected={};offset=-1;tag_added=False
out={'runtime_ref':REF,'component':'Redpanda Connect 4.113.0','scope':'real Kafka franz input -> prepared SQL output -> Kafka fallback DLQ. Explicit JSON profile: 64-bit integers and decimal are strings; binary hex; timestamp text with 6 digits. Upsert final-state idempotence only, not exactly-once. Coordinated nullable schema change, not auto-DDL.','cases':[]}
for port in ([] if resume else [6001,13306]):sql(port,'eco4','CREATE TABLE rpc_stream(id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(80),name VARCHAR(300),ts DATETIME(6),doc JSON)')
def conf(port):
 dsn=f"root:{'111' if port==6001 else 'types-local'}@tcp(127.0.0.1:{port})/eco4?parseTime=true&loc=UTC&readTimeout=15s&writeTimeout=15s"
 extra=',tag' if tag_added else '';placeholders='?,?,?,?,UNHEX(?),?,?,?'+(',?' if tag_added else '')
 upsert=f'INSERT INTO rpc_stream(id,s,u,d,payload,name,ts,doc{extra}) VALUES({placeholders}) ON DUPLICATE KEY UPDATE s=VALUES(s),u=VALUES(u),d=VALUES(d),payload=VALUES(payload),name=VALUES(name),ts=VALUES(ts),doc=VALUES(doc)'+(',tag=VALUES(tag)' if tag_added else '')
 def raw(q,args):return {'sql_raw':{'driver':'mysql','dsn':dsn,'query':q,'args_mapping':args,'max_in_flight':1}}
 output={'switch':{'cases':[{'check':'this.op == "delete"','output':raw('DELETE FROM rpc_stream WHERE id=?','root = [this.id]')},{'output':raw(upsert,'root = [this.id,this.s,this.u,this.d,this.hex,this.name,this.ts,this.doc'+(',this.tag' if tag_added else '')+']')}]}}
 return {'http':{'enabled':False},'input':{'kafka_franz':{'seed_brokers':['127.0.0.1:19092'],'topics':[topic],'consumer_group':group(port),'start_offset':'earliest','commit_period':'1s','checkpoint_limit':1}},'pipeline':{'threads':1},'output':{'fallback':[output,{'kafka_franz':{'seed_brokers':['127.0.0.1:19092'],'topic':f'eco4-rpc-dlq-{port}','key':'${! this.id }'}}]},'shutdown_timeout':'5s','logger':{'level':'INFO'}}
def start(port):
 path=B/f'rpc-stream-{port}-v{2 if tag_added else 1}.json';dump(path,conf(port));p=subprocess.Popen([exe,'run',str(path)],stdout=(B/f'rpc-stream-{port}.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True);procs[port]=p;(B/f'rpc-stream-{port}.pid').write_text(str(p.pid));return p
def emit(row,valid=True):
 global offset
 md=producer.send(topic,key=str(row['id']).encode(),value=json.dumps(row,ensure_ascii=False).encode()).get(timeout=10);offset=md.offset
 with (B/'rpc-stream-input.jsonl').open('a') as f:f.write(json.dumps({'offset':offset,'valid':valid,'record':row},ensure_ascii=False)+'\n')
 if valid:
  if row['op']=='delete':expected.pop(row['id'],None)
  else:expected[row['id']]=row
def template(i,**kw):
 r={'op':'upsert','id':str(i),'s':'9007199254740993','u':str(2**64-1),'d':'12345678901234567890.123456789012345678','hex':'00ff80','name':'RPC流式😀','ts':'2026-10-11 12:00:00.123456','doc':json.dumps({'big':9007199254740993,'nested':[None,True,'']},ensure_ascii=False)};r.update(kw);return r
def expected_rows():
 rows=[]
 for i,r in sorted(expected.items(),key=lambda x:int(x[0])):
  row=[int(i),int(r['s']) if r['s'] is not None else None,int(r['u']) if r['u'] is not None else None,decimal.Decimal(r['d']) if r['d'] is not None else None,r['hex'].upper() if r['hex'] is not None else None,r['name'],datetime.datetime.fromisoformat(r['ts']) if r['ts'] else None,json.loads(r['doc']) if r['doc'] is not None else None]
  if tag_added:row.append(r.get('tag'))
  rows.append(row)
 return rows
def actual(port):
 rr=sql(port,'eco4','SELECT id,s,u,d,HEX(payload),name,ts,doc'+(',tag' if tag_added else '')+' FROM rpc_stream ORDER BY id');return [list(r[:7])+[json.loads(r[7]) if r[7] is not None else None]+list(r[8:]) for r in rr]
def committed(port):
 c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',group_id=group(port),enable_auto_commit=False);n=c.committed(TopicPartition(topic,0));c.close();return n
def check(name):
 for port in [6001,13306]:
  r={'case':name,'port':port,'expected':expected_rows(),'last_input_offset':offset}
  try:poll(lambda:actual(port)==expected_rows(),45);poll(lambda:(committed(port) or 0)>=offset+1,15);r.update({'target':actual(port),'committed_next_offset':committed(port),'status':'passed'})
  except Exception as e:r.update({'status':'failed','error':str(e),'target':actual(port),'process_exit':procs[port].poll(),'log_tail':(B/f'rpc-stream-{port}.log').read_text()[-2500:]})
  out['cases'].append(r);dump(B/'redpanda-kafka-result.json',out);print('RPC KAFKA',name,port,r['status'],flush=True)
if resume:
 out=json.loads((B/'redpanda-kafka-result.json').read_text())
 out['harness_retry_note']='DLQ reader originally lacked snappy codec. Installed python-snappy and resumed on preserved topics/offsets, without replaying initial input.'
 for line in (B/'rpc-stream-input.jsonl').read_text().splitlines():
  v=json.loads(line);offset=v['offset'];r=v['record']
  if v['valid']:
   if r['op']=='delete':expected.pop(r['id'],None)
   else:expected[r['id']]=r
try:
 for port in [6001,13306]:start(port)
 if not resume:
  emit(template(1));emit(template(2,s=str(-2**63),u='0',d='-0.000000000000000001',hex='',name='',ts='2026-10-11 00:00:00.000001',doc='[]'));emit(template(3,s=None,u=None,d=None,hex=None,name=None,ts=None,doc=None));check('typed_snapshot_profile_NULL_empty_precision')
  emit(template(1,name='更新😀',d='0.000000000000000123'));emit({'op':'delete','id':'2'});emit(template(30,s=None,u=None,d=None,hex=None,name=None,ts=None,doc=None));emit({'op':'delete','id':'3'});check('update_delete_and_explicit_key_migration')
  emit(dict(expected['1']));emit(dict(expected['30']));check('duplicate_upsert_final_state_idempotence')
  emit(template(88,name='X'*301),False);emit(template(77,name='坏记录之后😀'));check('invalid_record_fallback_DLQ_valid_record_continues')
 for port in [6001,13306]:
  c=KafkaConsumer(f'eco4-rpc-dlq-{port}',bootstrap_servers='127.0.0.1:19092',group_id=f'eco4-rpc-audit-{port}',auto_offset_reset='earliest',enable_auto_commit=False);rec=[];deadline=time.monotonic()+8
  while time.monotonic()<deadline and not rec:
   for rr in c.poll(timeout_ms=500).values():rec.extend({'key':m.key.decode(),'record':json.loads(m.value),'offset':m.offset} for m in rr)
  c.close();out['cases'].append({'case':'DLQ_complete_original_bad_record','port':port,'messages':rec,'status':'passed' if len(rec)==1 and rec[0]['record']['id']=='88' and len(rec[0]['record']['name'])==301 else 'failed'})
 for port in [6001,13306]:
  os.kill(procs[port].pid,signal.SIGKILL);procs[port].wait(5);sql(port,'eco4','ALTER TABLE rpc_stream ADD COLUMN tag VARCHAR(60)')
 tag_added=True
 emit(template(1,name='离线更新😀',tag='新增列😀'));emit({'op':'delete','id':'30'});emit(template(4,hex='',tag='恢复😀'))
 for port in [6001,13306]:start(port)
 check('SIGKILL_restart_committed_offsets_offline_mutations_coordinated_schema_add')
finally:
 for p in procs.values():
  if p.poll() is None:p.terminate()
 for p in procs.values():
  try:p.wait(10)
  except subprocess.TimeoutExpired:p.kill();p.wait(5)
 producer.close();dump(B/'redpanda-kafka-result.json',out)
