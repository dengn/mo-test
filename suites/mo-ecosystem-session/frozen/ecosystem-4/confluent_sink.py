from runtime import *
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
import base64,datetime as dt
topic='eco4_confluent';a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));a.create_topics([NewTopic(topic,1,1)]);a.close()
fields=[{'field':'id','type':'int64','optional':False},{'field':'s','type':'int64','optional':True},{'field':'u','type':'bytes','optional':True,'name':'org.apache.kafka.connect.data.Decimal','parameters':{'scale':'0','connect.decimal.precision':'20'}},{'field':'d','type':'bytes','optional':True,'name':'org.apache.kafka.connect.data.Decimal','parameters':{'scale':'18','connect.decimal.precision':'38'}},{'field':'payload','type':'bytes','optional':True},{'field':'name','type':'string','optional':True},{'field':'ts','type':'string','optional':True},{'field':'doc','type':'string','optional':True}]
value_schema={'type':'struct','name':'eco4.CanonicalRow','optional':False,'fields':fields};key_schema={'type':'struct','name':'eco4.RecordKey','optional':False,'fields':[fields[0]]}
def encoded_decimal(value,scale):
 if value is None:return None
 with decimal.localcontext() as ctx:ctx.prec=80;i=int(decimal.Decimal(value)*(decimal.Decimal(10)**scale))
 return base64.b64encode(i.to_bytes(max(1,(i.bit_length()+8)//8),'big',signed=True)).decode()
expected={1:[1,9007199254740993,2**64-1,'12345678901234567890.123456789012345678','00FF80','Confluent中文😀','2026-10-11 12:00:00.123456',{'big':9007199254740993}],2:[2,-2**63,0,'-0.000000000000000001','','','2026-10-11 00:00:00',[]],3:[3,None,None,None,None,None,None,None]}
p=KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),acks='all',key_serializer=lambda x:json.dumps(x).encode(),value_serializer=lambda x:None if x is None else json.dumps(x).encode())
def send(row=None,id=None):
 id=row[0] if row else id;key={'schema':key_schema,'payload':{'id':id}}
 if row:
  val={'schema':value_schema,'payload':dict(zip(['id','s','u','d','payload','name','ts','doc'],[row[0],row[1],encoded_decimal(row[2],0),encoded_decimal(row[3],18),base64.b64encode(bytes.fromhex(row[4])).decode() if row[4] is not None else None,row[5],row[6],json.dumps(row[7],ensure_ascii=False) if row[7] is not None else None]))}
 else:val=None
 with (B/'confluent-input-records.jsonl').open('a') as f:f.write(json.dumps({'key':key,'value':val},ensure_ascii=False)+'\n')
 return p.send(topic,key=key,value=val).get(timeout=10)
for port in [13306,6001]:
 sql(port,'eco4','CREATE TABLE cf_sink(id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(80),name VARCHAR(300),ts DATETIME(6),doc JSON)')
 cfg={'connector.class':'io.confluent.connect.jdbc.JdbcSinkConnector','tasks.max':'1','topics':topic,'connection.url':f'jdbc:mysql://127.0.0.1:{port}/eco4?useSSL=false&serverTimezone=UTC','connection.user':'root','connection.password':'111' if port==6001 else 'types-local','table.name.format':'cf_sink','insert.mode':'upsert','pk.mode':'record_key','pk.fields':'id','delete.enabled':'true','auto.create':'false','auto.evolve':'false','batch.size':'50','max.retries':'2','retry.backoff.ms':'500','errors.tolerance':'all','errors.deadletterqueue.topic.name':'eco4-cf-dlq-'+str(port),'errors.deadletterqueue.topic.replication.factor':'1','errors.deadletterqueue.context.headers.enable':'true'}
 api('PUT','/connectors/eco4-cf-'+str(port)+'/config',cfg);dump(B/('confluent-'+str(port)+'-config.json'),cfg)
out={'runtime_ref':REF,'tool':'Confluent JDBC10.8.4 / Kafka3.9.1','scope':'real standard-schema producer to native JDBC sink, MO/MySQL controls; unsigned via Decimal(20,0), exact timestamp via string; native key/tombstone, pause/resume and DLQ','cases':[]}
def actual(port):
 rr=sql(port,'eco4','SELECT id,s,u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc FROM cf_sink ORDER BY id');result=[]
 for row in rr:
  r=list(row);r[-1]=json.loads(r[-1]) if isinstance(r[-1],str) else r[-1]
  if r[-2] and r[-2].endswith('.000000'):r[-2]=r[-2][:-7]
  result.append(r)
 return result
def check(name,ports=[13306,6001]):
 for port in ports:
  r={'case':name,'port':port}
  try:poll(lambda:actual(port)==[expected[id] for id in sorted(expected)],60);r['status']='passed'
  except Exception as e:r['status']='failed';r['error']=str(e);r['task_status']=api('GET','/connectors/eco4-cf-'+str(port)+'/status')
  r['target_rows']=actual(port);r['expected_rows']=[expected[id] for id in sorted(expected)];out['cases'].append(r);dump(B/'confluent-sink-result.json',out);print('CF',name,port,r['status'],flush=True)
for row in expected.values():send(row)
check('initial_complex_types_and_NULL_empty_binary')
expected[1][5]='更新😀';expected[1][3]='0.000000000000000123';send(expected[1]);send(id=2);del expected[2];expected[30]=list(expected[3]);expected[30][0]=30;send(expected[30]);send(id=3);del expected[3];check('update_delete_and_key_migration')
api('PUT','/connectors/eco4-cf-6001/pause');poll(lambda:all(t['state']=='PAUSED' for t in api('GET','/connectors/eco4-cf-6001/status')['tasks']),30);expected[1][5]='暂停期间😀';send(expected[1]);send(id=30);del expected[30];expected[4]=[4,9007199254740995,2**64-1,'0.000000000000000001','','恢复😀',None,None];send(expected[4]);time.sleep(2);api('PUT','/connectors/eco4-cf-6001/resume');check('pause_backlog_and_resume')
bad=[88,1,1,'1.000000000000000000','','x'*301,None,None];send(bad);expected[77]=[77,1,1,'1.000000000000000000','','有效后续😀',None,None];send(expected[77]);check('invalid_record_DLQ_valid_record_continues')
for port in [13306,6001]:
 c=KafkaConsumer('eco4-cf-dlq-'+str(port),bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),auto_offset_reset='earliest',enable_auto_commit=False,consumer_timeout_ms=5000);records=[]
 for rec in c:records.append({'offset':rec.offset,'key':json.loads(rec.key),'value':json.loads(rec.value),'headers':[(k,v.decode(errors='replace')) for k,v in rec.headers]})
 c.close();out.setdefault('DLQ',{})[str(port)]=records;dump(B/'confluent-sink-result.json',out)
p.close();print('CF COMPLETE',flush=True)
