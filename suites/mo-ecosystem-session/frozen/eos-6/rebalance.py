from protocol import *
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
topic='eos6-real-rebalance';N=250;init('rebalance',4)
a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));a.create_topics([NewTopic(topic,4,1)]);a.close()
p=KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),acks='all',value_serializer=lambda v:json.dumps(v,ensure_ascii=False).encode())
for part in range(4):
 for i in range(N):p.send(topic,{'event_id':i+1,'delta':i%7-3,'payload':'重分配😀'+str(i)},partition=part).get(timeout=10)
p.close();workers=[];out={'runtime_ref':REF,'scope':'real Kafka subscribe/group assignment/revocation, MO ledger+counter+contiguous checkpoint+epoch test adapter; two consumers; not native JDBC or automatic process HA','topic':topic,'messages':N*4,'unique_stable_events':N,'expected_sum':sum(i%7-3 for i in range(N))}
def spawn(name,fault=False):
 cmd=[sys.executable,str(B/'group_worker.py'),name]+(['--fault'] if fault else []);proc=subprocess.Popen(cmd,stdout=(B/(name+'.log')).open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/(name+'.pid')).write_text(str(proc.pid));workers.append(proc);return proc
def healthy():
 for proc in workers:
  if proc.poll() not in [None,-signal.SIGKILL]:raise RuntimeError('worker exited '+str(proc.returncode))
 return True
try:
 old=spawn('groupA_fault',True);marker=poll(lambda:json.loads((B/'group-fault-marker.json').read_text()) if (B/'group-fault-marker.json').exists() else False,90)
 assert marker['broker_committed_next']==marker['record_offset'],marker
 out['fault_marker']=marker;out['SIGKILL_UTC']=datetime.datetime.now(datetime.timezone.utc).isoformat();os.kill(old.pid,signal.SIGKILL);old.wait(timeout=10)
 start_t=time.monotonic();b=spawn('groupB');poll(lambda:healthy() and (B/'groupB-worker.json').exists() and json.loads((B/'groupB-worker.json').read_text())['records']>=30,100)
 a2=spawn('groupA_rejoined');poll(lambda:healthy() and (B/'groupA_rejoined-worker.json').exists() and any(len(x['claims'])==2 for x in json.loads((B/'groupA_rejoined-worker.json').read_text())['assignments']),100)
 def complete():
  healthy();cp=state('rebalance')['checkpoints'];return len(cp)==4 and all(x[1]==N-1 for x in cp)
 poll(complete,180);out['fault_to_complete_s']=time.monotonic()-start_t;(B/'group-stop').touch()
 for proc in workers:
  if proc.poll() is None:proc.wait(timeout=30)
 out['final']=state('rebalance');out['workers']=[json.loads((B/(n+'-worker.json')).read_text()) for n in ['groupA_fault','groupB','groupA_rejoined']]
 c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',group_id='eos6-real-group',enable_auto_commit=False,api_version=(3,0,0));out['broker_committed_next']={str(i):c.committed(TopicPartition(topic,i)) for i in range(4)};c.close()
 expected=[(i+1,digest({'event_id':i+1,'delta':i%7-3,'payload':'重分配😀'+str(i)}),i%7-3) for i in range(N)]
 ledger=[r[:3] for r in out['final']['ledger']];out['ledger_full_fields_match']=ledger==expected
 out['status']='passed_scoped_effects_rebalance' if ledger==expected and out['final']['total']==out['expected_sum'] and all(x==N for x in out['broker_committed_next'].values()) and not any(w['errors'] for w in out['workers']) else 'failed'
 dump(B/'rebalance-result.json',out);print(out['status'],out['fault_to_complete_s'],flush=True)
finally:
 (B/'group-stop').touch()
 for proc in workers:
  if proc.poll() is None:
   proc.terminate()
   try:proc.wait(timeout=15)
   except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
