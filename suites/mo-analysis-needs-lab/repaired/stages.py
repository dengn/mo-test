"""Real MO mutations, independently rebuilt snapshot truth, checkpoint audits."""
import json
from collections import defaultdict
import pandas as pd
from data import connect,read,compare,ROOT,values
class Stages:
 def __init__(self,data,out):
  self.data=data;self.out=out;self.state={};self.accepted={};self.maximum=-100000;self.processed=set();self.journal=[]
  self.c=connect()
  with self.c.cursor() as q:
   for t in ['inc_state','inc_daily','stream_accepted']:q.execute(f'DROP TABLE IF EXISTS {t}')
   q.execute('CREATE TABLE inc_state(event_id INT PRIMARY KEY,uid INT,day INT,v DOUBLE)')
   q.execute('CREATE TABLE inc_daily(uid INT,day INT,total DOUBLE,n INT,PRIMARY KEY(uid,day))')
   q.execute('CREATE TABLE stream_accepted(policy INT,event_id INT,uid INT,event_min INT,batch INT,v DOUBLE,kind INT,PRIMARY KEY(policy,event_id))')
 def advance(self,cp):
  assert cp not in self.processed
  delta=defaultdict(lambda:[0.,0]);changes=self.data['changes'];batch=changes[changes.checkpoint==cp].sort_values('seq')
  self.c.begin()
  with self.c.cursor() as q:
   for r in batch.itertuples():
    old=self.state.pop(r.event_id,None)
    if old is not None:delta[(old[0],old[1])][0]-=old[2];delta[(old[0],old[1])][1]-=1
    q.execute('DELETE FROM inc_state WHERE event_id=%s',(int(r.event_id),))
    if r.op:
     item=(int(r.uid),int(r.day),float(r.v));self.state[r.event_id]=item;delta[item[:2]][0]+=item[2];delta[item[:2]][1]+=1
     q.execute('INSERT INTO inc_state VALUES(%s,%s,%s,%s)',(int(r.event_id),*item))
   for (u,day),(v,n) in delta.items():
    q.execute('INSERT IGNORE INTO inc_daily VALUES(%s,%s,0,0)',(u,day));q.execute('UPDATE inc_daily SET total=total+%s,n=n+%s WHERE uid=%s AND day=%s',(v,n,u,day))
  self.c.commit()
  # Independent full reconstruction from immutable change history, not state/deltas above.
  hist=changes[changes.checkpoint<=cp].sort_values('seq').drop_duplicates('event_id',keep='last');inc=hist[hist.op==1]['event_id uid day v'.split()].sort_values('event_id').reset_index(drop=True)
  actual=read(self.c,'SELECT * FROM inc_state ORDER BY event_id');compare(inc,actual,1e-12)
  daily=inc.groupby(['uid','day']).v.agg(total='sum',n='count').reset_index().sort_values(['uid','day']).reset_index(drop=True)
  actual=read(self.c,'SELECT * FROM inc_daily WHERE n>0 ORDER BY uid,day');compare(daily,actual,1e-12)
  # Verify rollback really leaves materialized aggregates unchanged.
  self.c.begin()
  with self.c.cursor() as q:q.execute('UPDATE inc_daily SET total=total+1 WHERE uid=1')
  self.c.rollback();compare(daily,read(self.c,'SELECT * FROM inc_daily WHERE n>0 ORDER BY uid,day'),1e-12)
  deliveries=self.data['deliveries'];events=deliveries[deliveries.batch==cp].sort_values('delivery_id');previous=self.maximum
  for policy,lateness in enumerate([0,5,10,20,30]):
   before=len(self.accepted)
   with self.c.cursor() as q:
    sql=f'INSERT IGNORE INTO stream_accepted SELECT {policy},event_id,uid,event_min,batch,v,kind FROM deliveries WHERE batch={cp} AND event_min>={previous-lateness} ORDER BY delivery_id'
    q.execute(sql);inserted=q.rowcount;q.execute(sql);replayed=q.rowcount
   assert replayed==0,('Non-idempotent dedup replay',cp,policy,replayed)
   for r in events.itertuples():
    key=(policy,r.event_id)
    if r.event_min>=previous-lateness and key not in self.accepted:self.accepted[key]=(policy,r.event_id,r.uid,r.event_min,r.batch,float(r.v),r.kind)
   assert len(self.accepted)-before==inserted
  self.maximum=max(previous,int(events.event_min.max()))
  accepted=pd.DataFrame(list(self.accepted.values()),columns='policy event_id uid event_min batch v kind'.split()).sort_values(['policy','event_id']).reset_index(drop=True)
  compare(accepted,read(self.c,'SELECT * FROM stream_accepted ORDER BY policy,event_id'),1e-12)
  rec=dict(checkpoint=cp,changes=len(batch),affected_groups=len(delta),state_rows=len(inc),daily_rows=len(daily),deliveries=len(events),accepted_rows=len(accepted),previous_watermark=previous,current_watermark=self.maximum,rollback_verified=True,duplicate_replay_verified=True)
  self.journal.append(rec);self.processed.add(cp);(self.out/'checkpoint-journal.json').write_text(json.dumps(self.journal,indent=2));print('CHECKPOINT',rec,flush=True)
  return inc,accepted
 def close(self):self.c.close()
