from runtime import *
from kafka import KafkaProducer,KafkaConsumer
from kafka.admin import KafkaAdminClient,NewTopic
import base64
N=20000;topic='stress5-jdbc-ab';out={'runtime_ref':REF,'scope':'sequential default / rewriteBatchedStatements / default repeat, same frozen 20k Debezium envelopes, fresh MO tables, four partitions/tasks, 500 batch profile. Includes connector startup and sampling; not randomized statistically repeated benchmark. Other load generators finished; CDC idle.','cases':[]}
c=KafkaConsumer('stress5pg.stress5.wide',bootstrap_servers='127.0.0.1:19092',auto_offset_reset='earliest',enable_auto_commit=False,group_id='stress5-ab-auditor',max_poll_records=2000);records={};deadline=time.monotonic()+45
while len(records)<N and time.monotonic()<deadline:
 for vals in c.poll(timeout_ms=500).values():
  for r in vals:
   if r.value is None:continue
   v=json.loads(r.value);a=v['payload'].get('after')
   if a and v['payload']['op']=='r':records.setdefault(r.key,(r.key,r.value,r.headers,a))
   if len(records)==N:break
  if len(records)==N:break
c.close();assert len(records)==N,len(records)
a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092');a.create_topics([NewTopic(topic,4,1)]);a.close();p=KafkaProducer(bootstrap_servers='127.0.0.1:19092',acks='all',compression_type='gzip');digest=hashlib.sha256()
for key,val,headers,_ in records.values():p.send(topic,key=key,value=val,headers=headers);digest.update(key);digest.update(val)
p.flush();p.close();out['frozen_input_sha256']=digest.hexdigest()
def dec(v,scale):
 if v is None:return None
 i=int.from_bytes(base64.b64decode(v),'big',signed=True)
 with decimal.localcontext() as context:context.prec=80;return decimal.Decimal(i).scaleb(-scale)
expected={}
for _,_,_,r in records.values():
 expected[(r['tenant'],r['id'])]=(r['tenant'],r['id'],r['rev'],r['s'],int(dec(r['u'],0)),dec(r['d'],18),base64.b64decode(r['payload']) if r['payload'] is not None else None,r['name'],datetime.datetime(1970,1,1)+datetime.timedelta(microseconds=r['ts']),json.loads(r['doc']) if isinstance(r['doc'],str) else r['doc'])
for label,rewrite in [('default_a',False),('rewrite',True),('default_b',False)]:
 target='wide_ab_'+label;sql('CREATE TABLE '+target+' LIKE cdc_wide');cfg=json.loads((B/'stress5-mo-config.json').read_text());cfg.update({'topics':topic,'collection.name.format':target});cfg['connection.url']+='&rewriteBatchedStatements='+str(rewrite).lower()+'&useServerPrepStmts=false';cn='stress5-ab-'+label;dump(B/(cn+'-config.json'),cfg);t=time.monotonic();api('PUT','/connectors/'+cn+'/config',cfg);samples=[];r={'profile':label,'rewriteBatchedStatements':rewrite,'input_rows':N,'target':target,'resources_before':resources()}
 try:
  end=t+240
  while time.monotonic()<end:
   count=sql('SELECT COUNT(*) FROM '+target)[0][0];samples.append({'elapsed_s':time.monotonic()-t,'rows':count})
   if count==N:break
   status=api('GET','/connectors/'+cn+'/status')
   if any(x['state']=='FAILED' for x in status['tasks']):raise RuntimeError(json.dumps(status))
   time.sleep(.5)
  elapsed=time.monotonic()-t;r.update({'sampled_end_to_end_seconds':elapsed,'sampled_rows_s':count/elapsed,'samples':samples});rows=sql('SELECT tenant,id,rev,s,u,d,payload,name,ts,doc FROM '+target+' ORDER BY tenant,id');bad=[]
  for row in rows:
   rr=list(row);rr[-1]=json.loads(rr[-1]) if rr[-1] is not None else None
   if tuple(rr)!=expected.get((rr[0],rr[1])):
    if len(bad)<5:bad.append({'key':rr[:2],'actual':rr,'expected':expected.get((rr[0],rr[1]))})
  r.update({'actual_rows':len(rows),'mismatch_samples':bad,'status':'passed' if len(rows)==N and not bad else 'failed'})
 except Exception as e:r.update({'status':'failed','error':str(e)})
 r['resources_after']=resources();out['cases'].append(r);dump(B/'jdbc-ab-result.json',out);print('JDBC AB',label,r['status'],r.get('sampled_rows_s'),flush=True);api('PUT','/connectors/'+cn+'/pause');poll(lambda:all(x['state']=='PAUSED' for x in api('GET','/connectors/'+cn+'/status')['tasks']),30)
