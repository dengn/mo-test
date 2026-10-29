from runtime import *
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
out={'runtime_ref':REF,'scope':'MO native ENGINE=KAFKA explicit SQL transactions; separate fresh topics and groups; commit/rollback/later-statement-failure controls; relates #27587','cases':[]}
admin=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));producer=KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),acks='all',value_serializer=lambda x:json.dumps(x).encode())
for repeat in range(1,4):
 for mode in ['commit','rollback','later_error_commit','disconnect']:
  suffix=f'{mode}_{repeat}';topic='cert3sql-'+suffix;group='cert3sql-group-'+suffix;external='sql_src_'+suffix;sink='sql_sink_'+suffix;unrelated='sql_err_'+suffix
  admin.create_topics([NewTopic(topic,num_partitions=1,replication_factor=1)]);event='event-'+suffix;producer.send(topic,{'event_id':event,'delta':1}).get(timeout=10)
  case={'mode':mode,'repeat':repeat,'topic':topic,'group':group,'event_id':event}
  try:
   sql(6001,'cert3',f"CREATE EXTERNAL TABLE {external}(event_id VARCHAR(96),delta BIGINT) ENGINE=KAFKA WITH('brokers'='127.0.0.1:19092','topic'='{topic}','partition'='0','autocommit'='true','group'='{group}','format'='jsonl')")
   sql(6001,'cert3','CREATE TABLE '+sink+'(kafka_offset BIGINT PRIMARY KEY,event_id VARCHAR(96))');sql(6001,'cert3','CREATE TABLE '+unrelated+'(id INT PRIMARY KEY)');sql(6001,'cert3','INSERT INTO '+unrelated+' VALUES(1)')
   d=db();c=d.cursor();c.execute('BEGIN');c.execute('INSERT INTO '+sink+' SELECT __mo_message_id,event_id FROM '+external+' WHERE __mo_read_size=1 AND __mo_read_timeout=5');case['insert_affected']=c.rowcount
   if mode=='later_error_commit':
    try:c.execute('INSERT INTO '+unrelated+' VALUES(1)')
    except Exception as e:case['expected_later_error']=str(e)
   if mode=='disconnect':c.close();d.close();case['last_message_id']='connection closed'
   else:
    c.execute('ROLLBACK' if mode=='rollback' else 'COMMIT');c.execute('SELECT LAST_KAFKA_MESSAGE_ID()');case['last_message_id']=c.fetchone()[0];c.close();d.close()
   time.sleep(.5);case['sink_rows']=sql(6001,'cert3','SELECT * FROM '+sink)
   consumer=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',group_id=group,enable_auto_commit=False,api_version=(3,0,0));case['broker_committed_offset']=consumer.committed(TopicPartition(topic,0));consumer.close()
   if mode in ['commit','later_error_commit']:case['status']='passed' if case['sink_rows']==((0,event),) and case['last_message_id']==0 and case['broker_committed_offset']==1 else 'failed_data_progress_pairing'
   else:case['status']='passed' if not case['sink_rows'] and case['broker_committed_offset'] in [None,0] else 'failed_rollback_atomicity'
  except Exception as e:case['status']='blocked_or_failed';case['error']=str(e)
  out['cases'].append(case);dump(B/'kafka-native-sql-transactions-result.json',out);print(json.dumps(case,ensure_ascii=False,default=str),flush=True)
producer.close();admin.close();print('NATIVE KAFKA SQL CHECK COMPLETE',flush=True)
