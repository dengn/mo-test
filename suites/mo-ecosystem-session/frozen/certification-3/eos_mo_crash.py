from runtime import *
from kafka import KafkaConsumer,TopicPartition
out={'runtime_ref':REF,'scope':'same explicit ledger/counter/checkpoint transaction adapter; target MO SIGKILL while event105 transaction is uncommitted; source remains active','status':'pending_target_fault'}
with db(13306) as d,d.cursor() as c:c.executemany('INSERT INTO eos_events VALUES(%s,%s,%s)',[(i,1,'MO故障窗口😀') for i in range(101,121)])
marker=B/'adapter-fault-marker.json'
if marker.exists():marker.unlink()
p=subprocess.Popen(['/workspace/toolchains/python/bin/python',str(B/'effect_adapter.py'),'--pause','before_commit','--event','105','--last-event','120'],stdout=(B/'adapter.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/'adapter.pid').write_text(str(p.pid))
poll(lambda:marker.exists(),100);out['paused_marker']=json.loads(marker.read_text());out['state_before_target_crash']={'ledger':sql(6001,'cert3','SELECT COUNT(*) FROM eos_ledger')[0][0],'counter':sql(6001,'cert3','SELECT n FROM eos_totals WHERE id=1')[0][0],'checkpoint':sql(6001,'cert3','SELECT * FROM eos_checkpoint')};dump(B/'exactly-once-MO-crash-result.json',out)
def target_crashed():
 progress=json.loads((B/'soak-progress.json').read_text());return next((f for f in progress['faults'] if f['name']=='mo'),False)
fault=poll(target_crashed,750);out['MO_fault']=fault;out['adapter_fault']=kill('adapter','effect_adapter.py');p.wait(timeout=15);poll(lambda:sql(6001,None,'SELECT 1'),180)
out['state_after_MO_recovery']={'ledger':sql(6001,'cert3','SELECT COUNT(*) FROM eos_ledger')[0][0],'counter':sql(6001,'cert3','SELECT n FROM eos_totals WHERE id=1')[0][0],'checkpoint':sql(6001,'cert3','SELECT * FROM eos_checkpoint')};dump(B/'exactly-once-MO-crash-result.json',out)
p=subprocess.Popen(['/workspace/toolchains/python/bin/python',str(B/'effect_adapter.py'),'--last-event','120'],stdout=(B/'adapter.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/'adapter.pid').write_text(str(p.pid));p.wait(timeout=180);assert p.returncode==0
out['final']={'ledger_count':sql(6001,'cert3','SELECT COUNT(*) FROM eos_ledger')[0][0],'business_counter':sql(6001,'cert3','SELECT n FROM eos_totals WHERE id=1')[0][0],'checkpoint':sql(6001,'cert3','SELECT * FROM eos_checkpoint'),'source_count_and_sum':sql(13306,'cert3','SELECT COUNT(*),SUM(delta) FROM eos_events')[0]};out['status']='passed_scoped_target_crash_atomic_effects' if out['state_after_MO_recovery']['ledger']==out['state_after_MO_recovery']['counter']==104 and out['final']['ledger_count']==out['final']['business_counter']==120 else 'failed';dump(B/'exactly-once-MO-crash-result.json',out);print(json.dumps(out,ensure_ascii=False,default=str),flush=True)
