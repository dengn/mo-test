from runtime import *
out={'scope':'only PID files owned by certification-3, verifying command before signal; keep all datasets and receipts','actions':[]}
def alive(pid):
 try:return Path('/proc',str(pid),'stat').read_text().split()[2]!='Z'
 except FileNotFoundError:return False
for name,marker in [('adapter','effect_adapter.py'),('proxy','commit_ack_proxy.py'),('nifi','org.apache.nifi.NiFi'),('connect','org.apache.kafka.connect.cli.ConnectDistributed'),('eosconnect','org.apache.kafka.connect.cli.ConnectDistributed'),('kafka','kafka.Kafka'),('mo','/workspace/matrixone/mo-service')]:
 try:
  pid=int((B/(name+'.pid')).read_text())
  if not alive(pid):out['actions'].append({'name':name,'already_stopped':True});continue
  cmd=Path('/proc',str(pid),'cmdline').read_bytes()
  if marker.encode() not in cmd:out['actions'].append({'name':name,'pid_reused_skip':True});continue
  action=kill(name,marker,signal.SIGTERM);out['actions'].append(action);dump(B/'cleanup-result.json',out);print('STOP',name,pid,flush=True)
  end=time.monotonic()+45
  while alive(pid) and time.monotonic()<end:time.sleep(.5)
  if alive(pid):action['still_running_after_45s']=True;dump(B/'cleanup-result.json',out);raise RuntimeError('graceful shutdown incomplete: '+name+'; do not stop storage dependencies yet')
  action['verified_stopped']=True;dump(B/'cleanup-result.json',out)
 except FileNotFoundError:out['actions'].append({'name':name,'no_pid_file':True})
out['process_cleanup_complete']=True;dump(B/'cleanup-result.json',out);print('ALL OWNED PROCESSES STOPPED; safe to stop synthetic Docker MySQL/MinIO',flush=True)
