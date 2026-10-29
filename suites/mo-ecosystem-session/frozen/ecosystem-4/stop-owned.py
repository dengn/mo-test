from runtime import *
out={'scope':'only this round owned PID files; preserve all synthetic data, containers, topics and failure receipts','events':[]}
def alive(pid):
 p=Path('/proc',str(pid),'stat')
 return p.exists() and p.read_text().split()[2]!='Z'
for name,marker in [('connect','org.apache.kafka.connect.cli.ConnectDistributed'),('kafka','kafka.Kafka'),('mo','/workspace/matrixone/mo-service')]:
 pid=int((B/(name+'.pid')).read_text());r={'process':name,'pid':pid}
 if alive(pid):
  command=Path('/proc',str(pid),'cmdline').read_bytes();assert marker.encode() in command,(name,command)
  os.kill(pid,signal.SIGTERM);end=time.monotonic()+45
  while alive(pid) and time.monotonic()<end:time.sleep(.2)
  if alive(pid):os.kill(pid,signal.SIGKILL);r['forced_after_45s']=True
  poll(lambda:not alive(pid),10)
 r['stopped']=not alive(pid);out['events'].append(r);dump(B/'cleanup-result.json',out);print('STOPPED',name,pid,flush=True)
print('MO stopped; now stop only owned synthetic containers',flush=True)
cmd=['env','-u','DOCKER_HOST','-u','DOCKER_CONTEXT','-u','DOCKER_TLS','-u','DOCKER_TLS_VERIFY','-u','DOCKER_CERT_PATH','docker','--host=unix:///var/run/docker.sock']
p=subprocess.run(cmd+['stop','--timeout','10','mo-eco4-postgres','mo-types-mysql','mo-minio-local'],capture_output=True,text=True,timeout=45);out['container_stop']={'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr};assert p.returncode==0,p.stderr
p=subprocess.run(cmd+['inspect','--format','{{.Name}} {{.State.Status}}','mo-eco4-postgres','mo-types-mysql','mo-minio-local'],capture_output=True,text=True,timeout=10);out['container_final']=p.stdout
out['finished_UTC']=datetime.datetime.now(datetime.timezone.utc).isoformat();dump(B/'cleanup-result.json',out);print(json.dumps(out,ensure_ascii=False),flush=True)
