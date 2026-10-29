from redpanda_stream_support import *
# Run with --resume to preserve existing topic/table fixtures; do not replay initialization.
tag_added=True
# Functions are defined in support module and refer to its globals.
import redpanda_stream_support as m
m.tag_added=True
out=m.out
out['scope']+=' Corrected v2 array mapping uses a single literal. Initial bad mapping and DLQ remain in original receipt; good records are explicitly replayed, no silent offset reset.'
for line in (B/'rpc-stream-input.jsonl').read_text().splitlines():
 v=json.loads(line);m.offset=v['offset'];r=v['record']
 if v['valid']:
  if r['op']=='delete':m.expected.pop(r['id'],None)
  else:m.expected[r['id']]=r
try:
 for port in [6001,13306]:start(port)
 # Correct config then replay the two known good records rejected by bad Bloblang v2.
 emit(dict(m.expected['1']));emit(dict(m.expected['4']));check('explicit_replay_after_correcting_test_configuration')
 fault=[]
 for port in [6001,13306]:
  p=m.procs[port];fault.append({'port':port,'pid':p.pid,'signal':'SIGKILL','committed_next_offset':committed(port)});os.kill(p.pid,signal.SIGKILL);p.wait(5)
 out['fault']=fault
 emit(template(1,name='修正后宕机恢复😀',d='0.000000000000000123',tag='断点😀'));emit({'op':'delete','id':'4'});emit(template(5,s=str(-2**63),hex='',tag='新增😀'))
 for port in [6001,13306]:start(port)
 check('SIGKILL_then_offline_update_delete_insert_same_group_offset_resume')
finally:
 for p in m.procs.values():
  if p.poll() is None:p.terminate()
 for p in m.procs.values():
  try:p.wait(10)
  except subprocess.TimeoutExpired:p.kill();p.wait(5)
 producer.close();dump(B/'redpanda-kafka-recovery-result.json',out)
