from runtime import *
from kafka import KafkaProducer,KafkaConsumer,TopicPartition,OffsetAndMetadata
from kafka.admin import KafkaAdminClient,NewTopic
import concurrent.futures,random,collections
topic='cert3-effects-parallel';a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));a.create_topics([NewTopic(topic,4,1)])
sql(6001,'cert3','CREATE TABLE eos_parallel_ledger(event_id BIGINT PRIMARY KEY,delta BIGINT,first_partition INT,first_offset BIGINT)');sql(6001,'cert3','CREATE TABLE eos_parallel_totals(id INT PRIMARY KEY,n BIGINT)');sql(6001,'cert3','INSERT INTO eos_parallel_totals VALUES(1,0)');sql(6001,'cert3','CREATE TABLE eos_parallel_checkpoint(partition_id INT PRIMARY KEY,last_offset BIGINT)')
p=KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),acks='all',value_serializer=lambda x:json.dumps(x).encode())
for part in range(4):
 events=list(range(1,201));random.Random(part+77).shuffle(events)
 for id in events:p.send(topic,{'event_id':id,'delta':1},partition=part).get(timeout=10)
p.close();a.close();start_t=time.monotonic()
def worker(part):
 c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),group_id='cert3-effects-parallel-'+str(part),enable_auto_commit=False,consumer_timeout_ms=10000,value_deserializer=json.loads)
 tp=TopicPartition(topic,part);c.assign([tp]);c.seek(tp,0);count=0;first=0;dedup=0;retry=collections.Counter();errors=[]
 try:
  for record in c:
   id=record.value['event_id'];delta=record.value['delta']
   for attempt in range(40):
    try:
     with db(autocommit=False) as d,d.cursor() as q:
      q.execute('SELECT delta FROM eos_parallel_ledger WHERE event_id=%s',(id,));r=q.fetchone();inserted=not bool(r)
      if r:assert r[0]==delta
      else:
       q.execute('INSERT INTO eos_parallel_ledger VALUES(%s,%s,%s,%s)',(id,delta,part,record.offset));q.execute('UPDATE eos_parallel_totals SET n=n+%s WHERE id=1',(delta,))
      q.execute('INSERT INTO eos_parallel_checkpoint VALUES(%s,%s) ON DUPLICATE KEY UPDATE last_offset=GREATEST(last_offset,VALUES(last_offset))',(part,record.offset));d.commit()
     first+=int(inserted);dedup+=int(not inserted);break
    except pymysql.MySQLError as e:
     code=e.args[0];retry[str(code)]+=1
     if code not in [1062,1213,20601,20618,20619,20622,20628,20631,20701] and not any(s in str(e).lower() for s in ['conflict','deadlock','txn need retry']):raise
     if attempt==39:raise
     time.sleep(min(.005*(attempt+1),.2))
   c.commit({tp:OffsetAndMetadata(record.offset+1,'',-1)});count+=1
   if count==200:break
 except Exception as e:errors.append(str(e))
 finally:c.close()
 return {'partition':part,'consumed':count,'first_effects':first,'dedup_replays':dedup,'transaction_retries_by_error_code':dict(retry),'errors':errors}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:results=list(ex.map(worker,range(4)))
ledger=sql(6001,'cert3','SELECT COUNT(*),COUNT(DISTINCT event_id),SUM(delta) FROM eos_parallel_ledger')[0];counter=sql(6001,'cert3','SELECT n FROM eos_parallel_totals WHERE id=1')[0][0];checkpoint=sql(6001,'cert3','SELECT * FROM eos_parallel_checkpoint ORDER BY partition_id')
out={'runtime_ref':REF,'scope':'four explicitly assigned consumers on four partitions; each partition contains the same 200 stable event IDs in independent shuffled orders; no rebalance/HA/crash injected in this additional concurrency control','source_messages':800,'unique_event_ids':200,'workers':results,'ledger_count_distinct_sum':ledger,'business_counter':counter,'MO_checkpoint':checkpoint,'duration_s':time.monotonic()-start_t,'status':'passed_scoped_parallel_dedup' if ledger[:2]==(200,200) and int(ledger[2])==200 and counter==200 and checkpoint==tuple((i,199) for i in range(4)) and all(r['consumed']==200 and not r['errors'] for r in results) else 'failed'}
dump(B/'exactly-once-parallel-result.json',out);print(json.dumps(out,ensure_ascii=False,default=str,indent=2),flush=True)
