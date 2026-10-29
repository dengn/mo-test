from runtime import *
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));topic='cert3-transactional-view';a.create_topics([NewTopic(topic,1,1)])
p=KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),transactional_id='cert3-tx-producer',enable_idempotence=True,acks='all',max_block_ms=20000,value_serializer=lambda x:json.dumps(x).encode());p.init_transactions()
sql(6001,'cert3',f"CREATE EXTERNAL TABLE transactional_view(event_id VARCHAR(96),delta BIGINT) ENGINE=KAFKA WITH('brokers'='127.0.0.1:19092','topic'='{topic}','partition'='0','autocommit'='false','group'='cert3-transactional-view-group','format'='jsonl')")
out={'runtime_ref':REF,'scope':'native Kafka ENGINE read_committed visibility; producer transaction isolation, not end-to-end sink exactly once','steps':[]}
def observe(phase):
 d=db();c=d.cursor();c.execute('SELECT __mo_message_id,event_id,delta FROM transactional_view WHERE __mo_read_start_id=-1 AND __mo_read_size=100 AND __mo_read_timeout=2');rows=c.fetchall();c.execute('SELECT LAST_KAFKA_MESSAGE_ID()');last=c.fetchone()[0];c.close();d.close();out['steps'].append({'phase':phase,'rows':rows,'last_message_id':last});dump(B/'kafka-transactional-view-result.json',out);print(phase,rows,last,flush=True);return rows
p.begin_transaction()
for i in range(10):p.send(topic,{'event_id':f'aborted-{i}','delta':1}).get(timeout=10)
r0=observe('transaction_open');p.abort_transaction();r1=observe('transaction_aborted')
p.begin_transaction()
for i in range(10):p.send(topic,{'event_id':f'committed-{i}','delta':1}).get(timeout=10)
p.commit_transaction();r2=observe('transaction_committed')
out['status']='passed_committed_view' if not r0 and not r1 and len(r2)==10 and {r[1] for r in r2}=={f'committed-{i}' for i in range(10)} else 'failed';dump(B/'kafka-transactional-view-result.json',out);p.close();a.close();print(out['status'],flush=True)
