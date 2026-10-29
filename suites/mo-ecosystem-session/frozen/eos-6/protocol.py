from runtime import *
class StaleEpoch(Exception):pass
class OffsetGap(Exception):pass
class PayloadConflict(Exception):pass
RETRY={1062,1213,1205,20619,20628,20631,20701,20702}
def init(scope,parts=1,port=6001):
 sql('INSERT INTO totals VALUES(%s,0)',(scope,),port=port)
 for part in range(parts):sql('INSERT INTO checkpoints VALUES(%s,%s,-1,0)',(scope,part),port=port)
def claim(scope,part,port=6001):
 with db(port,autocommit=False) as d,d.cursor() as c:
  c.execute('SELECT last_offset,epoch FROM checkpoints WHERE scope=%s AND partition_id=%s FOR UPDATE',(scope,part));last,epoch=c.fetchone();c.execute('UPDATE checkpoints SET epoch=epoch+1 WHERE scope=%s AND partition_id=%s',(scope,part));d.commit();return last,epoch+1
def digest(event):return hashlib.sha256(json.dumps(event,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def apply(scope,part,offset,event,epoch=None,port=6001,after_ledger_error=False,quarantine_conflict=False,expected_previous=None):
 retries=[]
 for attempt in range(60):
  try:
   with db(port,autocommit=False) as d,d.cursor() as c:
    c.execute('SELECT last_offset,epoch FROM checkpoints WHERE scope=%s AND partition_id=%s FOR UPDATE',(scope,part));last,current=c.fetchone()
    if epoch is not None and epoch!=current:raise StaleEpoch((epoch,current))
    if offset<=last:d.rollback();return {'result':'checkpoint_replay','retries':retries}
    # Numeric gaps are legitimate with Kafka transaction control records/compaction.
    # expected_previous comes from the ordered delivered-record chain, never MAX(completed offsets).
    required_previous=offset-1 if expected_previous is None else expected_previous
    if last!=required_previous:raise OffsetGap((last,offset,required_previous))
    c.execute('SELECT digest,delta FROM ledger WHERE scope=%s AND event_id=%s',(scope,event['event_id']));seen=c.fetchone();h=digest(event)
    result='dedup' if seen else 'effect'
    if seen and (seen[0]!=h or seen[1]!=event['delta']):
     if not quarantine_conflict:raise PayloadConflict(event['event_id'])
     c.execute('INSERT INTO quarantine VALUES(%s,%s,%s,%s,%s)',(scope,part,offset,event['event_id'],'same stable event_id with different canonical payload'));result='quarantine'
    if not seen:
     c.execute('INSERT INTO ledger VALUES(%s,%s,%s,%s,%s,%s)',(scope,event['event_id'],h,event['delta'],part,offset))
     if after_ledger_error:raise RuntimeError('injected error after ledger INSERT before effect UPDATE')
     c.execute('UPDATE totals SET n=n+%s WHERE scope=%s',(event['delta'],scope))
    c.execute('UPDATE checkpoints SET last_offset=%s WHERE scope=%s AND partition_id=%s',(offset,scope,part));d.commit()
   return {'result':result,'retries':retries}
  except pymysql.MySQLError as e:
   if e.args[0] not in RETRY:raise
   retries.append(e.args[0])
   if attempt==59:raise
   time.sleep(min(.002*(attempt+1),.1))
def state(scope,port=6001):
 return {'ledger':sql('SELECT event_id,digest,delta,first_partition,first_offset FROM ledger WHERE scope=%s ORDER BY event_id',(scope,),port=port),'total':sql('SELECT n FROM totals WHERE scope=%s',(scope,),port=port)[0][0],'checkpoints':sql('SELECT partition_id,last_offset,epoch FROM checkpoints WHERE scope=%s ORDER BY partition_id',(scope,),port=port),'quarantine':sql('SELECT partition_id,record_offset,event_id,reason FROM quarantine WHERE scope=%s ORDER BY partition_id,record_offset',(scope,),port=port)}
