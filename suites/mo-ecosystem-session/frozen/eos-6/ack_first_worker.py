from protocol import *
from kafka import KafkaConsumer,TopicPartition,OffsetAndMetadata
c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),group_id='eos6-ack-first-group',enable_auto_commit=False,auto_offset_reset='earliest',value_deserializer=json.loads);tp=TopicPartition('eos6-ack-first',0);c.assign([tp]);c.seek(tp,0)
rec=poll(lambda:next(iter(c.poll(timeout_ms=500,max_records=1).get(tp,[])),None),30);c.commit({tp:OffsetAndMetadata(rec.offset+1,'',-1)})
d=db(autocommit=False);q=d.cursor();e=rec.value;q.execute('INSERT INTO ledger VALUES(%s,%s,%s,%s,0,%s)',('ack_first',e['event_id'],digest(e),e['delta'],rec.offset));q.execute('UPDATE totals SET n=n+%s WHERE scope=%s',(e['delta'],'ack_first'));q.execute('UPDATE checkpoints SET last_offset=%s WHERE scope=%s',(rec.offset,'ack_first'))
dump(B/'ack-first-fault-marker.json',{'stage':'broker ACK committed, MO ledger/effect/checkpoint uncommitted','record_offset':rec.offset,'broker_committed_next':c.committed(tp),'event':e})
while True:time.sleep(.2)
