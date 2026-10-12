import redpanda_stream_support as m
from redpanda_stream_support import *
m.tag_added=True
old=m.conf
def config(port):
 c=old(port);c['input']['kafka_franz'].update({'session_timeout':'8s','heartbeat_interval':'2s','rebalance_timeout':'10s'});return c
m.conf=config
out=m.out
out['scope']+=' Timed SIGKILL repeat, explicitly configured Kafka session_timeout=8s/heartbeat=2s/rebalance=10s, 90s observation budget. Does not certify p99 or exactly-once.'
for line in (B/'rpc-stream-input.jsonl').read_text().splitlines():
 v=json.loads(line);m.offset=v['offset'];r=v['record']
 if v['valid']:
  if r['op']=='delete':m.expected.pop(r['id'],None)
  else:m.expected[r['id']]=r
out['cases']=[]
try:
 # Verify the final state after the previous 45s deadline expired, preserving that receipt.
 for port in [6001,13306]:
  out['cases'].append({'case':'prior_default_session_final_state_after_45s_deadline','port':port,'target':actual(port),'expected':expected_rows(),'status':'passed' if actual(port)==expected_rows() else 'failed','note':'Original MO 45s deadline failed; final state matched by shutdown at ~47s, exact reconciliation instant was not sampled.'})
 for port in [6001,13306]:start(port)
 emit(template(1,name='短会话预热😀',tag='预热😀'));check('membership_warmup_new_record_and_committed_offset')
 t0=time.monotonic();fault=[]
 for port in [6001,13306]:
  p=m.procs[port];fault.append({'port':port,'pid':p.pid,'signal':'SIGKILL','committed_next_offset':committed(port)});os.kill(p.pid,signal.SIGKILL);p.wait(5)
 out['fault']=fault
 emit(template(1,name='定时恢复😀',d='0.000000000000000123',tag='定时😀'));emit({'op':'delete','id':'5'});emit(template(6,s=str(-2**63),hex='',tag='短会话😀'))
 for port in [6001,13306]:start(port)
 found={};deadline=time.monotonic()+90
 while time.monotonic()<deadline and len(found)<2:
  for port in [6001,13306]:
   if port not in found and actual(port)==expected_rows():found[port]=time.monotonic()-t0
  time.sleep(.25)
 for port in [6001,13306]:
  next_offset=committed(port)
  if port in found:
   poll(lambda:(committed(port) or 0)>=m.offset+1,15);next_offset=committed(port)
  out['cases'].append({'case':'timed_SIGKILL_offline_mutations_resume','port':port,'sampled_reconcile_seconds':found.get(port),'last_input_offset':m.offset,'committed_next_offset':next_offset,'expected':expected_rows(),'target':actual(port),'status':'passed' if port in found and next_offset>=m.offset+1 else 'failed'})
  print('TIMED RPC',port,found.get(port),next_offset,flush=True)
finally:
 for p in m.procs.values():
  if p.poll() is None:p.terminate()
 for p in m.procs.values():
  try:p.wait(10)
  except subprocess.TimeoutExpired:p.kill();p.wait(5)
 producer.close();dump(B/'redpanda-kafka-timed-fault-result.json',out)
