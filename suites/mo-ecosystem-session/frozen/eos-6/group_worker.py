from protocol import *
from kafka import KafkaConsumer,TopicPartition,OffsetAndMetadata
from kafka.consumer.subscription_state import ConsumerRebalanceListener
import collections
name=sys.argv[1];fault='--fault' in sys.argv;zombie='--zombie' in sys.argv;scenario='zombie' if '--scenario=zombie' in sys.argv else 'group';topic='eos6-zombie' if scenario=='zombie' else 'eos6-real-rebalance';scope='zombie' if scenario=='zombie' else 'rebalance';group='eos6-zombie-group' if scenario=='zombie' else 'eos6-real-group'
trace={'worker':name,'assignments':[],'revocations':[],'records':0,'effects':0,'dedup':0,'checkpoint_replay':0,'fenced':0,'fencing_rejections':[],'commit_failures':[],'transaction_retries':collections.Counter(),'errors':[]};epochs={};last_activity=time.monotonic();paused_once=False
def save():dump(B/(name+'-worker.json'),trace)
class Listener(ConsumerRebalanceListener):
 def on_partitions_revoked(self,parts):
  trace['revocations'].append({'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'partitions':[p.partition for p in parts]});epochs.clear();save()
 def on_partitions_assigned(self,parts):
  claims=[]
  for tp in parts:
   last,epoch=claim(scope,tp.partition);epochs[tp.partition]=epoch;c.seek(tp,last+1);claims.append({'partition':tp.partition,'MO_last_offset':last,'epoch':epoch,'broker_committed_next':c.committed(tp)})
  trace['assignments'].append({'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'claims':claims});save()
c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),group_id=group,enable_auto_commit=False,auto_offset_reset='earliest',value_deserializer=json.loads,max_poll_records=8,session_timeout_ms=8000,heartbeat_interval_ms=2000,max_poll_interval_ms=30000)
c.subscribe([topic],listener=Listener());save()
try:
 while not (B/(scenario+'-stop')).exists():
  batch=c.poll(timeout_ms=500,max_records=8)
  for tp,records in batch.items():
   for rec in records:
    epoch=epochs.get(tp.partition)
    if epoch is None:continue
    if zombie and not paused_once:
     paused_once=True;dump(B/'zombie-fault-marker.json',{'worker':name,'partition':tp.partition,'record_offset':rec.offset,'event':rec.value,'captured_epoch':epoch,'database':state(scope)})
     while not (B/'zombie-resume').exists():time.sleep(.2)
    try:r=apply(scope,tp.partition,rec.offset,rec.value,epoch=epoch)
    except StaleEpoch as e:trace['fenced']+=1;trace['fencing_rejections'].append({'partition':tp.partition,'record_offset':rec.offset,'captured_epoch':epoch,'error':str(e)});save();continue
    trace['records']+=1;trace['effects']+=r['result']=='effect';trace['dedup']+=r['result']=='dedup';trace['checkpoint_replay']+=r['result']=='checkpoint_replay';trace['transaction_retries'].update(map(str,r['retries']))
    if fault and trace['records']==25:
     dump(B/'group-fault-marker.json',{'worker':name,'partition':tp.partition,'record_offset':rec.offset,'event':rec.value,'DB_committed_before_Kafka_ACK':True,'broker_committed_next':c.committed(tp),'database':state(scope)})
     save()
     while True:time.sleep(.2)
    try:c.commit({tp:OffsetAndMetadata(rec.offset+1,'',-1)})
    except Exception as e:
     trace['commit_failures'].append({'partition':tp.partition,'offset':rec.offset,'type':type(e).__name__,'message':str(e)})
     if type(e).__name__ not in ['CommitFailedError','RebalanceInProgressError','IllegalGenerationError','UnknownMemberIdError']:raise
    save();time.sleep(.01)
except Exception as e:trace['errors'].append({'type':type(e).__name__,'message':str(e)});save();raise
finally:c.close();save()
