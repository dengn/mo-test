from runtime import *
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient,NewTopic
out={'runtime_ref':REF,'scope':'three independent topics per format, valid two-field records; strict and non-strict projection controls; no crash during this probe','cases':[]}
a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0))
p=KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),acks='all')
for fmt in ['jsonl','csv']:
 for rep in range(1,4):
  t=f'cert3proj-{fmt}-{rep}';ext=f'proj_{fmt}_{rep}'
  a.create_topics([NewTopic(t,1,1)]);p.send(t,b'{"event_id":"valid-event","delta":1}' if fmt=='jsonl' else b'valid-event,1').get(timeout=10)
  sql(6001,'cert3',f"CREATE EXTERNAL TABLE {ext}(event_id VARCHAR(96),delta BIGINT) ENGINE=KAFKA WITH('brokers'='127.0.0.1:19092','topic'='{t}','partition'='0','autocommit'='false','group'='{t}-group','format'='{fmt}')")
  for mode in ['STRICT_TRANS_TABLES','']:
   with db() as d,d.cursor() as c:
    c.execute('SET SESSION sql_mode=%s',(mode,))
    for projection in ['*','event_id','delta','__mo_message_id','__mo_message_id,event_id','__mo_message_id,event_id,delta']:
     q=f'SELECT {projection} FROM {ext} WHERE __mo_read_start_id=0 AND __mo_read_size=1 AND __mo_read_timeout=2'
     r={'format':fmt,'repeat':rep,'sql_mode':mode,'projection':projection,'sql':q}
     try:c.execute(q);r['rows']=c.fetchall();r['status']='returned'
     except Exception as e:r['error']=str(e);r['status']='failed'
     out['cases'].append(r);dump(B/'kafka-projection-controls-result.json',out);print(json.dumps(r),flush=True)
  sql(6001,'cert3',f'CREATE TABLE proj_dest_{fmt}_{rep}(offset_id BIGINT,event_id VARCHAR(96),delta BIGINT)')
  q=f'INSERT INTO proj_dest_{fmt}_{rep} SELECT __mo_message_id,event_id,delta FROM {ext} WHERE __mo_read_start_id=0 AND __mo_read_size=1 AND __mo_read_timeout=2'
  r={'format':fmt,'repeat':rep,'sql':q,'control':'full fields INSERT SELECT'}
  try:r['affected']=sql(6001,'cert3',q);r['rows']=sql(6001,'cert3',f'SELECT * FROM proj_dest_{fmt}_{rep}');r['status']='returned'
  except Exception as e:r['error']=str(e);r['status']='failed'
  out['cases'].append(r);dump(B/'kafka-projection-controls-result.json',out)
p.close();a.close();print('PROJECTION CONTROLS COMPLETE',flush=True)
