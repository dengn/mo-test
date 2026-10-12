import os,time,json,datetime,subprocess,signal,hashlib,decimal
from pathlib import Path
import pymysql,requests,psycopg
B=Path(__file__).resolve().parent;OLD=B.parent/'runtime-expanded';REF='652c643666428f1c434e03369834f2a9bead7c27'
def dump(path,obj):
 path=Path(path);tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str));tmp.replace(path)
def db(port=6001,database='eco4',autocommit=True):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database=database,charset='utf8mb4',autocommit=autocommit,connect_timeout=5,read_timeout=30,write_timeout=30)
def sql(port,database,q,args=None):
 with db(port,database) as d,d.cursor() as c:c.execute(q,args);return c.fetchall() if c.description else c.rowcount
def pg(autocommit=True):return psycopg.connect('host=127.0.0.1 port=15432 dbname=postgres user=postgres password=compat4-local',autocommit=autocommit,connect_timeout=5)
def psql(q,args=None):
 with pg() as d,d.cursor() as c:c.execute(q,args);return c.fetchall() if c.description else c.rowcount
def api(method,path,data=None):
 r=requests.request(method,'http://127.0.0.1:18086'+path,json=data,timeout=15);r.raise_for_status();return r.json() if r.content else None
def poll(fn,timeout=90):
 end=time.monotonic()+timeout;last=None
 while time.monotonic()<end:
  try:
   last=fn()
   if last:return last
  except Exception as e:last=str(e)
  time.sleep(.5)
 raise TimeoutError(str(last))
def start(name):
 commands={'mo':['/workspace/matrixone/mo-service','-launch','/workspace/work/path-verification/runtime/mo-config/launch.toml'],'kafka':[str(OLD/'kafka_2.13-3.9.1/bin/kafka-server-start.sh'),str(OLD/'kraft.properties')],'connect':[str(OLD/'kafka_2.13-3.9.1/bin/connect-distributed.sh'),str(B/'connect.properties')]}
 env=dict(os.environ,JAVA_HOME='/usr/lib/jvm/java-21-openjdk-amd64',KAFKA_HEAP_OPTS='-Xms128m -Xmx512m')
 p=subprocess.Popen(commands[name],cwd='/workspace/matrixone' if name=='mo' else None,env=env,stdout=(B/(name+'.log')).open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/(name+'.pid')).write_text(str(p.pid));print('START',name,p.pid,flush=True);return p.pid
def kill(name,marker,sig=signal.SIGKILL):
 pid=int((B/(name+'.pid')).read_text());assert marker.encode() in Path('/proc',str(pid),'cmdline').read_bytes();os.kill(pid,sig);return {'name':name,'pid':pid,'signal':sig.name,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
