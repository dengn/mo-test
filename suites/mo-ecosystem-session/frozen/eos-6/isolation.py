from protocol import *
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
topic='eos6-source-transactions';a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));a.create_topics([NewTopic(topic,1,1)]);a.close()
p=KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),transactional_id='eos6-source-producer',enable_idempotence=True,acks='all',value_serializer=lambda v:json.dumps(v).encode());p.init_transactions()
p.begin_transaction()
for i in range(6):p.send(topic,{'event_id':i+1,'delta':11,'phase':'abort'}).get(timeout=10)
p.abort_transaction();p.begin_transaction()
for i in range(10):p.send(topic,{'event_id':100+i,'delta':2,'phase':'commit'}).get(timeout=10)
p.commit_transaction();p.begin_transaction()
for i in range(3):p.send(topic,{'event_id':200+i,'delta':100,'phase':'open'}).get(timeout=10)
def read(mode):
 c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),group_id=None,enable_auto_commit=False,isolation_level=mode,value_deserializer=json.loads);tp=TopicPartition(topic,0);c.assign([tp]);c.seek(tp,0);rows=[];deadline=time.monotonic()+5
 while time.monotonic()<deadline:
  batch=c.poll(timeout_ms=300)
  for records in batch.values():rows.extend({'offset':r.offset,'event':r.value} for r in records)
 pos=c.position(tp);end=c.end_offsets([tp])[tp];c.close();return {'records':rows,'position_next':pos,'end_next':end}
uncommitted=read('read_uncommitted');committed=read('read_committed');out={'runtime_ref':REF,'scope':'transactional Kafka producer -> explicit MO ledger/counter/checkpoint adapter; open and aborted records must not cause effects; control-record offsets are not delivered business events','read_uncommitted':uncommitted,'read_committed':committed,'cases':[]}
for mode,data in [('unsafe_uncommitted',uncommitted),('safe_committed',committed)]:
 init(mode);previous=-1
 for r in data['records']:apply(mode,0,r['offset'],r['event'],expected_previous=previous);previous=r['offset']
 s=state(mode);target=sum(x['event']['delta'] for x in data['records']);correct=s['total']==target
 if mode=='unsafe_uncommitted':correct=correct and s['total']==386 and len(s['ledger'])==19
 else:correct=correct and s['total']==20 and len(s['ledger'])==10 and {r[0] for r in s['ledger']}==set(range(100,110))
 out['cases'].append({'case':mode,'status':'observed_expected_EOS_failure' if correct and mode=='unsafe_uncommitted' else ('passed_scoped' if correct else 'failed_unexpected'),'state':s})
init('strict_numeric_gap_guard');first=committed['records'][0]
try:apply('strict_numeric_gap_guard',0,first['offset'],first['event']);raise AssertionError('numeric offset gap missing')
except OffsetGap as e:out['numeric_guard_counterexample']={'first_delivered_offset':first['offset'],'error':str(e),'state':state('strict_numeric_gap_guard'),'reason':'Kafka aborted/control offsets cannot be required as business-event continuity'}
p.abort_transaction();p.close();out['producer_open_transaction_final_action']='abort';out['status']='completed_with_expected_counterexample' if all(c['status']!='failed_unexpected' for c in out['cases']) else 'failed';dump(B/'isolation-result.json',out);print(out['status'],flush=True)
