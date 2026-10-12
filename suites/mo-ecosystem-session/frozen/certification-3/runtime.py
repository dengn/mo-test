import os,time,json,subprocess,signal,datetime
from pathlib import Path
import pymysql,requests
B=Path(__file__).parent;OLD=B.parent/'runtime-expanded';B.mkdir(exist_ok=True);REF='652c643666428f1c434e03369834f2a9bead7c27'
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str))
def db(port=6001,database='cert3',autocommit=True):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database=database,autocommit=autocommit,charset='utf8mb4',connect_timeout=4,read_timeout=20,write_timeout=20)
def sql(p,n,q,args=None):
 with db(p,n) as d,d.cursor() as c:
  c.execute(q,args);return c.fetchall() if c.description else c.rowcount
def api(m,p,data=None,port=18084):
 r=requests.request(m,f'http://127.0.0.1:{port}'+p,json=data,timeout=15);r.raise_for_status();return r.json() if r.content else None
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
 args={'mo':['/workspace/matrixone/mo-service','-launch','/workspace/work/path-verification/runtime/mo-config/launch.toml'],'kafka':[str(OLD/'kafka_2.13-3.9.1/bin/kafka-server-start.sh'),str(OLD/'kraft.properties')],'nifi':[str(OLD/'nifi-2.4.0/bin/nifi.sh'),'run'],'connect':[str(OLD/'kafka_2.13-3.9.1/bin/connect-distributed.sh'),str(B/'connect.properties')],'eosconnect':[str(OLD/'kafka_2.13-3.9.1/bin/connect-distributed.sh'),str(B/'eos-connect.properties')]}[name]
 cwd=OLD/'nifi-2.4.0' if name=='nifi' else '/workspace/matrixone' if name=='mo' else None
 env=dict(os.environ,JAVA_HOME='/usr/lib/jvm/java-21-openjdk-amd64',KAFKA_HEAP_OPTS='-Xms128m -Xmx512m')
 p=subprocess.Popen(args,cwd=cwd,env=env,stdout=(B/(name+'.log')).open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/(name+'.pid')).write_text(str(p.pid));print('START',name,p.pid,flush=True);return p.pid
def kill(name,marker,sig=signal.SIGKILL):
 pid=int((B/(name+'.pid')).read_text());cmd=Path('/proc',str(pid),'cmdline').read_bytes();assert marker.encode() in cmd;os.kill(pid,sig);return {'name':name,'pid':pid,'signal':sig.name,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def percentile(values,p):
 a=sorted(values);return a[min(len(a)-1,int((len(a)-1)*p))] if a else None
