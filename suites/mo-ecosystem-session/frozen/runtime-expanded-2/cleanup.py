from common import *
import socket
out={'services':{},'scope':'only this audit owned fixtures/processes; preserve configs/data/receipts and one intentionally rejected NiFi event'}
def alive(pid):
 try:
  s=Path('/proc',str(pid),'status').read_text();return not next(x for x in s.splitlines() if x.startswith('State:')).split()[1]=='Z'
 except FileNotFoundError:return False
def stop(name,marker):
 pid=int((B/(name+'.pid')).read_text())
 if alive(pid):kill_owned(name,marker,signal.SIGTERM)
 out['services'][name]={'pid':pid,'requested':'SIGTERM'};dump(B/'service-cleanup.json',out)
def finish(name,timeout=60):
 pid=out['services'][name]['pid'];end=time.monotonic()+timeout
 while alive(pid) and time.monotonic()<end:time.sleep(.5)
 out['services'][name]['terminated']=not alive(pid);dump(B/'service-cleanup.json',out);print('STOPPED',name,not alive(pid),flush=True)
 if alive(pid):raise RuntimeError('owned service has not completed graceful shutdown '+name)
stop('nifi','org.apache.nifi.NiFi');stop('connect','org.apache.kafka.connect.cli.ConnectDistributed')
finish('nifi');finish('connect')
stop('kafka','kafka.Kafka');finish('kafka')
# MO observability/object-store flush must finish before MinIO stops.
stop('mo','/workspace/matrixone/mo-service');finish('mo',90)
subprocess.run(['docker','exec','mo-types-mysql','mysqladmin','--socket=/tmp/mo-rt2-control.sock','-uroot','shutdown'],check=True,timeout=30)
subprocess.run(['docker','stop','mo-types-mysql','mo-minio-local'],check=True,timeout=60)
out['owned_containers_running']=[n for n in subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines() if n in ['mo-types-mysql','mo-minio-local']]
out['closed_ports']={}
for port in [6001,10088,18083,19092,13306,9000]:
 try:
  with socket.create_connection(('127.0.0.1',port),timeout=1):out['closed_ports'][str(port)]=False
 except OSError:out['closed_ports'][str(port)]=True
dump(B/'service-cleanup.json',out)
summary=json.loads((B/'expanded-round2-summary.json').read_text());summary['cleanup']=out;dump(B/'expanded-round2-summary.json',summary)
print('CLEANUP COMPLETE',flush=True)
