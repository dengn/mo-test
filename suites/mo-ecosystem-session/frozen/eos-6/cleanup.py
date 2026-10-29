from runtime import *
import socket
out={'scope':'stop only round eos6 known owned PID files; retain all source/data/topics/receipts','events':[]}
def alive(pid):
 p=Path('/proc',str(pid),'stat');return p.exists() and p.read_text().split()[2]!='Z'
for name,marker in [('groupA_fault','group_worker.py'),('groupB','group_worker.py'),('groupA_rejoined','group_worker.py'),('zombieA','group_worker.py'),('zombieB','group_worker.py'),('ack-first-worker','ack_first_worker.py'),('proxy','commit_ack_proxy.py'),('kafka','kafka.Kafka'),('mo','/workspace/matrixone/mo-service')]:
 f=B/(name+'.pid')
 if not f.exists():continue
 pid=int(f.read_text());r={'process':name,'pid':pid}
 if alive(pid):
  command=Path('/proc',str(pid),'cmdline').read_bytes();assert marker.encode() in command,(name,command)
  if name.startswith('zombie'):os.kill(pid,signal.SIGCONT)
  os.kill(pid,signal.SIGTERM);end=time.monotonic()+40
  while alive(pid) and time.monotonic()<end:time.sleep(.2)
  if alive(pid):os.kill(pid,signal.SIGKILL);r['forced_after_40s']=True
  poll(lambda:not alive(pid),10)
 r['stopped']=not alive(pid);out['events'].append(r);dump(B/'cleanup-result.json',out);print('STOPPED',name,pid,flush=True)
cmd=['env','-u','DOCKER_HOST','-u','DOCKER_CONTEXT','-u','DOCKER_TLS','-u','DOCKER_TLS_VERIFY','-u','DOCKER_CERT_PATH','docker','--host=unix:///var/run/docker.sock']
p=subprocess.run(cmd+['stop','--timeout','10','mo-types-mysql','mo-minio-local'],capture_output=True,text=True,timeout=40);out['container_stop']={'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr};assert p.returncode==0,p.stderr
out['ports']={}
for port in [16001,6001,19092,13306,9000]:
 s=socket.socket();s.settimeout(.3);out['ports'][str(port)]='closed' if s.connect_ex(('127.0.0.1',port)) else 'open';s.close()
assert all(x=='closed' for x in out['ports'].values()),out['ports']
out['git_tracked_changes']=subprocess.run(['git','-C','/workspace/matrixone','diff','--name-only','HEAD'],capture_output=True,text=True,check=True).stdout;assert not out['git_tracked_changes']
out['finished_UTC']=datetime.datetime.now(datetime.timezone.utc).isoformat();dump(B/'cleanup-result.json',out);print(json.dumps(out,ensure_ascii=False),flush=True)
