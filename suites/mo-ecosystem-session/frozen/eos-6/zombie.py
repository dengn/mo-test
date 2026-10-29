from protocol import *
from kafka import KafkaProducer,KafkaConsumer,TopicPartition
from kafka.admin import KafkaAdminClient,NewTopic
topic='eos6-zombie';N=120;init('zombie');a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0));a.create_topics([NewTopic(topic,1,1)]);a.close()
p=KafkaProducer(bootstrap_servers='127.0.0.1:19092',api_version=(3,0,0),acks='all',value_serializer=lambda v:json.dumps(v).encode())
for i in range(N):p.send(topic,{'event_id':i+1,'delta':1,'payload':'旧消费者😀'},partition=0).get(timeout=10)
p.close();workers=[];out={'runtime_ref':REF,'scope':'real OS SIGSTOP of consumer including Kafka heartbeat thread -> broker session expiry -> successor claim -> SIGCONT old in-flight captured epoch; explicit transactional fencing adapter','input_events':N}
def spawn(name,zombie=False):
 proc=subprocess.Popen([sys.executable,str(B/'group_worker.py'),name,'--scenario=zombie']+(['--zombie'] if zombie else []),stdout=(B/(name+'.log')).open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/(name+'.pid')).write_text(str(proc.pid));workers.append(proc);return proc
try:
 old=spawn('zombieA',True);marker=poll(lambda:json.loads((B/'zombie-fault-marker.json').read_text()) if (B/'zombie-fault-marker.json').exists() else False,60);os.kill(old.pid,signal.SIGSTOP);out['SIGSTOP_UTC']=datetime.datetime.now(datetime.timezone.utc).isoformat();out['old_inflight_marker']=marker
 new=spawn('zombieB');poll(lambda:(B/'zombieB-worker.json').exists() and json.loads((B/'zombieB-worker.json').read_text())['records']>=10,90);out['before_old_resume']=state('zombie');assert out['before_old_resume']['checkpoints'][0][2]>marker['captured_epoch']
 (B/'zombie-resume').touch();os.kill(old.pid,signal.SIGCONT);out['SIGCONT_UTC']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 poll(lambda:(B/'zombieA-worker.json').exists() and json.loads((B/'zombieA-worker.json').read_text())['fenced']>=1,30)
 poll(lambda:state('zombie')['checkpoints'][0][1]==N-1,90);(B/'zombie-stop').touch()
 for proc in workers:proc.wait(timeout=30)
 out['final']=state('zombie');out['workers']=[json.loads((B/(n+'-worker.json')).read_text()) for n in ['zombieA','zombieB']]
 c=KafkaConsumer(bootstrap_servers='127.0.0.1:19092',group_id='eos6-zombie-group',enable_auto_commit=False,api_version=(3,0,0));out['broker_committed_next']=c.committed(TopicPartition(topic,0));c.close()
 out['status']='passed_scoped_stale_owner_fencing' if out['final']['total']==N and len(out['final']['ledger'])==N and out['broker_committed_next']==N and out['workers'][0]['fenced']>=1 and not any(w['errors'] for w in out['workers']) else 'failed';dump(B/'zombie-result.json',out);print(out['status'],flush=True)
finally:
 (B/'zombie-stop').touch();(B/'zombie-resume').touch()
 for proc in workers:
  if proc.poll() is None:
   os.kill(proc.pid,signal.SIGCONT);proc.terminate()
   try:proc.wait(timeout=15)
   except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
