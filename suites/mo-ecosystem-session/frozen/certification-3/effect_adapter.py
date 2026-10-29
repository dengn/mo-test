from runtime import *
from kafka import KafkaConsumer,TopicPartition,OffsetAndMetadata
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--pause',default='none');parser.add_argument('--event',type=int,default=-1);parser.add_argument('--last-event',type=int,default=100);args=parser.parse_args();topic='cert3cdc.cert3.eos_events';consumer=KafkaConsumer(topic,bootstrap_servers=['127.0.0.1:19092'],group_id='cert3-effect-adapter',enable_auto_commit=False,auto_offset_reset='earliest',api_version=(3,0,0),consumer_timeout_ms=120000)
d=db(6001,'cert3',False);seen=0;dedup=0
def pause(phase,msg,event):
 if args.pause==phase and event==args.event:
  dump(B/'adapter-fault-marker.json',{'phase':phase,'event_id':event,'topic':msg.topic,'partition':msg.partition,'offset':msg.offset,'pid':os.getpid(),'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()})
  while True:time.sleep(.2)
for msg in consumer:
 raw=json.loads(msg.value) if msg.value else None
 if not raw:continue
 payload=raw.get('payload',raw);row=payload.get('after')
 if not row:continue
 event=int(row['event_id']);delta=int(row['delta']);tp=TopicPartition(msg.topic,msg.partition)
 try:
  with d.cursor() as c:
   c.execute('SELECT delta FROM eos_ledger WHERE event_id=%s',(event,));old=c.fetchone()
   if old:
    assert old[0]==delta,'duplicate event identity with conflicting content';dedup+=1
   else:
    c.execute('INSERT INTO eos_ledger VALUES(%s,%s,%s,%s,%s)',(event,msg.topic,msg.partition,msg.offset,delta));c.execute('UPDATE eos_totals SET n=n+%s WHERE id=1',(delta,))
   c.execute('INSERT INTO eos_checkpoint VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE last_offset=GREATEST(last_offset,VALUES(last_offset))',(msg.topic,msg.partition,msg.offset))
  pause('before_commit',msg,event);d.commit();pause('after_commit',msg,event)
  consumer.commit({tp:OffsetAndMetadata(msg.offset+1,'',-1)});seen+=1
  if event==args.last_event:
   dump(B/'adapter-complete.json',{'processed_this_process':seen,'deduplicated_this_process':dedup,'last_event_id':event,'last_topic_offset':msg.offset,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()});break
 except Exception:
  d.rollback();raise
consumer.close();d.close()
