import json,time,os,subprocess,signal
from pathlib import Path
import pymysql,requests
B=Path(__file__).parent; OLD=B.parent/'runtime-expanded'; REF='652c643666428f1c434e03369834f2a9bead7c27'
def db(port=13306,database=None):
 return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database=database,autocommit=True,charset='utf8mb4',connect_timeout=5,read_timeout=15,write_timeout=15)
def sql(port,database,stmt,args=None):
 with db(port,database) as d,d.cursor() as c:
  c.execute(stmt,args);return c.fetchall() if c.description else c.rowcount
def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str))
def api(method,path,data=None,base='http://127.0.0.1:18083'):
 r=requests.request(method,base+path,json=data,timeout=20);r.raise_for_status();return r.json() if r.content else None
def kill_owned(name,marker,sig=signal.SIGKILL):
 pid=int((B/(name+'.pid')).read_text());cmd=Path('/proc',str(pid),'cmdline').read_bytes().replace(b'\0',b' ').decode()
 assert marker in cmd,(pid,cmd);os.kill(pid,sig)
 print('SIGNAL',name,pid,sig.name,flush=True)
 return {'service':name,'pid':pid,'signal':sig.name,'identity_marker':marker}
def start(name):
 args={'connect':[str(OLD/'kafka_2.13-3.9.1/bin/connect-distributed.sh'),str(OLD/'connect.properties')],'kafka':[str(OLD/'kafka_2.13-3.9.1/bin/kafka-server-start.sh'),str(OLD/'kraft.properties')],'nifi':[str(OLD/'nifi-2.4.0/bin/nifi.sh'),'run'],'mo':['/workspace/matrixone/mo-service','-launch','/workspace/work/path-verification/runtime/mo-config/launch.toml']}[name]
 env=dict(os.environ,KAFKA_HEAP_OPTS='-Xms128m -Xmx512m',JAVA_HOME='/usr/lib/jvm/java-21-openjdk-amd64')
 cwd=OLD/'nifi-2.4.0' if name=='nifi' else '/workspace/matrixone' if name=='mo' else None
 p=subprocess.Popen(args,env=env,cwd=cwd,stdout=(B/(name+'.log')).open('ab'),stderr=subprocess.STDOUT,start_new_session=True)
 (B/(name+'.pid')).write_text(str(p.pid));return p.pid
def poll(fn,timeout=60):
 end=time.monotonic()+timeout;last=None
 while time.monotonic()<end:
  try:
   last=fn()
   if last:return last
  except Exception as e:last=str(e)
  time.sleep(1)
 raise TimeoutError(str(last))
