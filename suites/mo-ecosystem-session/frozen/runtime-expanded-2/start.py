import os,subprocess,time,json,socket
from pathlib import Path
B=Path(__file__).parent; OLD=B.parent/'runtime-expanded'; B.mkdir(exist_ok=True)
def start(name,args,cwd=None,env=None):
 f=(B/(name+'.log')).open('ab')
 p=subprocess.Popen(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 (B/(name+'.pid')).write_text(str(p.pid));print(name,p.pid,flush=True);return p
def wait_port(port,timeout=120):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:
   with socket.create_connection(('127.0.0.1',port),timeout=1):return
  except OSError:time.sleep(1)
 raise RuntimeError('port unavailable '+str(port))
wait_port(9000);wait_port(13306)
start('mo',['/workspace/matrixone/mo-service','-launch','/workspace/work/path-verification/runtime/mo-config/launch.toml'],cwd='/workspace/matrixone')
start('kafka',[str(OLD/'kafka_2.13-3.9.1/bin/kafka-server-start.sh'),str(OLD/'kraft.properties')],env=dict(os.environ,KAFKA_HEAP_OPTS='-Xms128m -Xmx512m'))
start('nifi',[str(OLD/'nifi-2.4.0/bin/nifi.sh'),'run'],cwd=OLD/'nifi-2.4.0',env=dict(os.environ,JAVA_HOME='/usr/lib/jvm/java-21-openjdk-amd64'))
wait_port(19092)
start('connect',[str(OLD/'kafka_2.13-3.9.1/bin/connect-distributed.sh'),str(OLD/'connect.properties')],env=dict(os.environ,KAFKA_HEAP_OPTS='-Xms128m -Xmx512m'))
for port in [6001,18083,10088]:wait_port(port)
print('all ports ready',flush=True)
