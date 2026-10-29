from protocol import *
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
scope='ack_first';topic='eos6-ack-first';init(scope);a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));a.create_topics([NewTopic(topic,1,1)]);a.close()
p=KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),acks='all',value_serializer=lambda v:json.dumps(v).encode())
for i in range(10):p.send(topic,{'event_id':i+1,'delta':1},partition=0).get(timeout=10)
p.close();proc=subprocess.Popen([sys.executable,str(B/'ack_first_worker.py')],stdout=(B/'ack-first-worker.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/'ack-first-worker.pid').write_text(str(proc.pid))
try:
 marker=poll(lambda:json.loads((B/'ack-first-fault-marker.json').read_text()) if (B/'ack-first-fault-marker.json').exists() else False,40);assert marker['broker_committed_next']==1;os.kill(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
 poll(lambda:not state(scope)['ledger'] and state(scope)['total']==0,10);before=state(scope)
 c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),group_id='eos6-ack-first-group',enable_auto_commit=False,auto_offset_reset='earliest',value_deserializer=json.loads);tp=TopicPartition(topic,0);c.assign([tp]);start_offset=c.committed(tp);c.seek(tp,start_offset);events=[]
 while len(events)<9:
  for rec in c.poll(timeout_ms=500).get(tp,[]):events.append({'offset':rec.offset,'event':rec.value})
 c.close()
 # Deliberately unsafe broker-authoritative recovery: align DB checkpoint without recovering missing effect.
 sql('UPDATE checkpoints SET last_offset=%s WHERE scope=%s',(start_offset-1,scope))
 for r in events:apply(scope,0,r['offset'],r['event'])
 after=state(scope);out={'runtime_ref':REF,'scope':'deliberately unsafe explicit Kafka ACK before MO commit; real worker SIGKILL; successor trusts broker checkpoint','fault_marker':marker,'database_after_kill_before_resume':before,'successor_start_offset':start_offset,'resumed_events':events,'expected_source_events':10,'final':after,'status':'observed_expected_EOS_failure' if after['total']==9 and len(after['ledger'])==9 and [r[0] for r in after['ledger']]==list(range(2,11)) else 'failed_unexpected'};dump(B/'ack-first-result.json',out);print(out['status'],flush=True)
finally:
 if proc.poll() is None:proc.kill();proc.wait(timeout=5)
