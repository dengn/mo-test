from protocol import *
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
from kafka.errors import KafkaError
suffix='-repeat1' if '--repeat1' in sys.argv else '';topic='eos6-producer-fence'+suffix;a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));a.create_topics([NewTopic(topic,1,1)]);a.close()
def producer():return KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),transactional_id='eos6-shared-producer-identity'+suffix,enable_idempotence=True,acks='all',request_timeout_ms=10000,max_block_ms=15000,value_serializer=lambda v:json.dumps(v).encode())
old=producer();old.init_transactions();old.begin_transaction()
for i in range(5):old.send(topic,{'event_id':i+1,'delta':100,'producer':'stale'}).get(timeout=10)
new=producer();new.init_transactions();new.begin_transaction()
for i in range(5):new.send(topic,{'event_id':101+i,'delta':1,'producer':'current'}).get(timeout=10)
new.commit_transaction()
try:old.commit_transaction();raise AssertionError('old producer unexpectedly committed')
except KafkaError as e:fence={'type':type(e).__name__,'message':str(e)}
assert fence['type'] in ['ProducerFencedError','InvalidProducerEpochError'] or (fence['type']=='KafkaError' and '[Error 90]' in fence['message'] and 'ProducerFencedError' in fence['message']),fence
old.close(timeout=2);new.close(timeout=5)
c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),group_id=None,enable_auto_commit=False,isolation_level='read_committed',value_deserializer=json.loads);tp=TopicPartition(topic,0);c.assign([tp]);c.seek(tp,0);records=[];end=time.monotonic()+5
while time.monotonic()<end:
 for rec in c.poll(timeout_ms=300).get(tp,[]):records.append({'offset':rec.offset,'event':rec.value})
c.close();scope='producer_fence';init(scope);previous=-1
for rec in records:apply(scope,0,rec['offset'],rec['event'],expected_previous=previous);previous=rec['offset']
s=state(scope);expected=[(101+i,digest({'event_id':101+i,'delta':1,'producer':'current'}),1) for i in range(5)]
out={'runtime_ref':REF,'scope':'two real transactional Kafka producers share transactional.id; stale producer fenced by broker; read_committed -> explicit MO transactional adapter','topic':topic,'old_open_records':5,'new_committed_records':5,'old_commit_error':fence,'delivered':records,'final':s,'status':'passed_scoped_producer_fencing' if [r[:3] for r in s['ledger']]==expected and s['total']==5 else 'failed'};dump(B/'producer-fence-result.json',out);print(out['status'],flush=True)
