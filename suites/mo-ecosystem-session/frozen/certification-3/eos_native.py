from runtime import *
from kafka import KafkaConsumer,TopicPartition
out={'runtime_ref':REF,'scope':'native Debezium JDBC append sink; real worker SIGKILL after DB commit before broker group offset commit; source worker remains running','cases':[]}
poll(lambda:api('GET','/connector-plugins',port=18085),90)
source=json.loads((B/'source-config.json').read_text());source.update({'name':'cert3-required-eos-probe','exactly.once.support':'required'})
validation=api('PUT','/connector-plugins/io.debezium.connector.mysql.MySqlConnector/config/validate',source,18085)
out['source_eos_preflight']={'worker_exactly_once_source_support':'enabled','error_count':validation['error_count'],'errors':[{ 'name':c['definition']['name'],'errors':c.get('value',{}).get('errors')} for c in validation['configs'] if c.get('value',{}).get('errors')]};dump(B/'source-eos-enabled-worker-validation.json',validation)
cfg=json.loads((B/'sink-config.json').read_text());cfg.update({'topics':'cert3cdc.cert3.eos_events','insert.mode':'insert','primary.key.mode':'none','primary.key.fields':'','delete.enabled':'false','schema.evolution':'none','collection.name.format':'eos_native_append'})
api('PUT','/connectors/cert3-eos-native/config',cfg,18085);dump(B/'native-eos-sink-config.json',cfg)
poll(lambda:bool(api('GET','/connectors/cert3-eos-native/status',port=18085)['tasks']) and all(t['state']=='RUNNING' for t in api('GET','/connectors/cert3-eos-native/status',port=18085)['tasks']),60)
with db(13306) as d,d.cursor() as c:c.executemany('INSERT INTO eos_events VALUES(%s,%s,%s)',[(i,1,'exactly-once事件😀') for i in range(1,101)])
poll(lambda:sql(6001,'cert3','SELECT COUNT(*) FROM eos_native_append')[0][0]>=100,80)
consumer=KafkaConsumer(bootstrap_servers=['127.0.0.1:19092'],group_id='connect-cert3-eos-native',enable_auto_commit=False,api_version=(3,0,0));tp=TopicPartition('cert3cdc.cert3.eos_events',0)
end_before=consumer.end_offsets([tp])[tp];committed=consumer.committed(tp);counts=sql(6001,'cert3','SELECT COUNT(*),COUNT(DISTINCT event_id) FROM eos_native_append')[0]
out['before_crash']={'target_total_rows':counts[0],'target_distinct_event_ids':counts[1],'topic_end_offset':end_before,'committed_group_offset':committed,'rest_offsets':api('GET','/connectors/cert3-eos-native/offsets',port=18085)};dump(B/'exactly-once-native-result.json',out)
if committed is not None and committed>=end_before:raise RuntimeError('missed fault window: offset already committed; cannot infer duplicate delivery')
out['fault']=kill('eosconnect','org.apache.kafka.connect.cli.ConnectDistributed');dump(B/'exactly-once-native-result.json',out);consumer.close();time.sleep(1);start('eosconnect')
poll(lambda:api('GET','/connectors/cert3-eos-native/status',port=18085),90)
poll(lambda:sql(6001,'cert3','SELECT COUNT(*) FROM eos_native_append')[0][0]>counts[0],90)
time.sleep(3)
consumer=KafkaConsumer(bootstrap_servers=['127.0.0.1:19092'],group_id=None,enable_auto_commit=False,api_version=(3,0,0));end_after=consumer.end_offsets([tp])[tp];consumer.close()
total,distinct=sql(6001,'cert3','SELECT COUNT(*),COUNT(DISTINCT event_id) FROM eos_native_append')[0]
out['after_restart']={'target_total_rows':total,'target_distinct_event_ids':distinct,'source_total_and_distinct':sql(13306,'cert3','SELECT COUNT(*),COUNT(DISTINCT event_id) FROM eos_events'),'topic_end_offset':end_after,'duplicate_event_ids':sql(6001,'cert3','SELECT event_id,COUNT(*) FROM eos_native_append GROUP BY event_id HAVING COUNT(*)>1 ORDER BY event_id'),'task_status':api('GET','/connectors/cert3-eos-native/status',port=18085)}
out['status']='native_end_to_end_exactly_once_failed_by_replay' if total>distinct and end_before==end_after else 'inconclusive';dump(B/'exactly-once-native-result.json',out);print(json.dumps({'status':out['status'],'before':out['before_crash'],'after_total':total,'after_distinct':distinct,'topic_before':end_before,'topic_after':end_after,'source_preflight':out['source_eos_preflight']},ensure_ascii=False),flush=True)
