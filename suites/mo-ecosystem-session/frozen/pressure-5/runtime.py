import os,sys,time,json,datetime,subprocess,signal,hashlib,decimal,shutil,threading,statistics
from pathlib import Path
import pymysql,psycopg,requests
B=Path(__file__).resolve().parent;OLD=B.parent/'runtime-expanded';REF='652c643666428f1c434e03369834f2a9bead7c27';DS='stress5'
def dump(path,obj):
 path=Path(path);tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str));tmp.replace(path)
def db(port=6001,database=DS,autocommit=True):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database=database,autocommit=autocommit,charset='utf8mb4',connect_timeout=5,read_timeout=90,write_timeout=60)
def sql(q,args=None,port=6001,database=DS):
 with db(port,database) as d,d.cursor() as c:c.execute(q,args);return c.fetchall() if c.description else c.rowcount
def pg(autocommit=True):return psycopg.connect('host=127.0.0.1 port=15432 dbname=postgres user=postgres password=compat4-local',autocommit=autocommit,connect_timeout=5)
def psql(q,args=None):
 with pg() as d,d.cursor() as c:c.execute(q,args);return c.fetchall() if c.description else c.rowcount
def poll(fn,timeout=90):
 end=time.monotonic()+timeout;last=None
 while time.monotonic()<end:
  try:
   last=fn()
   if last:return last
  except Exception as e:last=str(e)
  time.sleep(.25)
 raise TimeoutError(str(last))
def percentile(v,p):
 if not v:return None
 s=sorted(v);return s[min(len(s)-1,int((len(s)-1)*p))]
def stats(v):return {'n':len(v),'p50_ms':percentile(v,.5),'p95_ms':percentile(v,.95),'p99_ms':percentile(v,.99),'max_ms':max(v) if v else None}
def api(method,path,data=None):
 r=requests.request(method,'http://127.0.0.1:18087'+path,json=data,timeout=15);r.raise_for_status();return r.json() if r.content else None
def start(name):
 cmd={'mo':['/workspace/matrixone/mo-service','-launch',str(B/'mo-config/launch.toml')],'kafka':[str(OLD/'kafka_2.13-3.9.1/bin/kafka-server-start.sh'),str(OLD/'kraft.properties')],'connect':[str(OLD/'kafka_2.13-3.9.1/bin/connect-distributed.sh'),str(B/'connect.properties')]}[name]
 env=dict(os.environ,JAVA_HOME='/usr/lib/jvm/java-21-openjdk-amd64',KAFKA_HEAP_OPTS='-Xms128m -Xmx512m')
 p=subprocess.Popen(cmd,cwd='/workspace/matrixone' if name=='mo' else None,env=env,stdout=(B/(name+'.log')).open('ab'),stderr=subprocess.STDOUT,start_new_session=True);(B/(name+'.pid')).write_text(str(p.pid));print('START',name,p.pid,flush=True);return p.pid
def kill(name,marker,sig=signal.SIGKILL):
 pid=int((B/(name+'.pid')).read_text());assert marker.encode() in Path('/proc',str(pid),'cmdline').read_bytes();os.kill(pid,sig);return {'name':name,'pid':pid,'signal':sig.name,'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def guard():
 free=shutil.disk_usage('/workspace').free
 if free<600*1024**2:raise RuntimeError(f'test resource guard: free disk only {free} bytes; not a MatrixOne error')
 return free
def safe_read(path):
 try:return path.read_text()
 except PermissionError:return 'unavailable: /proc access denied; no I/O counter asserted'
def resources():
 pids={n:int((B/(n+'.pid')).read_text()) for n in ['mo','kafka','connect'] if (B/(n+'.pid')).exists()};out={'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic':time.monotonic(),'disk_free':shutil.disk_usage('/workspace').free,'processes':{}}
 for n,p in pids.items():
  try:
   st=Path('/proc',str(p),'stat').read_text().split();status=Path('/proc',str(p),'status').read_text();out['processes'][n]={'pid':p,'user_ticks':int(st[13]),'system_ticks':int(st[14]),'rss_kib':next((int(l.split()[1]) for l in status.splitlines() if l.startswith('VmRSS:')),0),'io':safe_read(Path('/proc',str(p),'io'))}
  except FileNotFoundError:out['processes'][n]={'pid':p,'missing':True}
 for f in ['cpu.stat','memory.current','memory.events','io.stat']:
  p=Path('/sys/fs/cgroup')/f
  if p.exists():out[f]=p.read_text()
 return out
