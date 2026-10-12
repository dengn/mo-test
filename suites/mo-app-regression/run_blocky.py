"""Official Blocky DNS runtime with native MatrixOne query-log migration and writes."""
import argparse,hashlib,io,json,os,secrets,signal,shutil,socket,struct,subprocess,tarfile,threading,time,uuid,urllib.request,xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parent
URL='https://github.com/0xERR0R/blocky/releases/download/v0.35.0/blocky_v0.35.0_Linux_x86_64.tar.gz'
ARCHIVE_SHA='97ae4257e4f2ea7ee4e0622fca152019eb92224d81b41b2549f064e4cef5584e'
BINARY_SHA='7e09c167b1276818fcae3699e0f4713a97c15cde7e00e41afe9a3fcfb9f14030'

def binary(provided, min_free_mib=2048):
 if provided:
  provided=provided.resolve()
  if hashlib.sha256(provided.read_bytes()).hexdigest()!=BINARY_SHA:raise RuntimeError("Official binary hash mismatch")
  return provided
 target=ROOT/'runtime/blocky-v0.35.0/blocky'
 if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==BINARY_SHA:return target
 target.parent.mkdir(parents=True,exist_ok=True)
 if provided:data=provided.read_bytes();assert hashlib.sha256(data).hexdigest()==BINARY_SHA
 else:
  with urllib.request.urlopen(URL,timeout=60) as r:b=r.read(20*1024**2)
  assert hashlib.sha256(b).hexdigest()==ARCHIVE_SHA
  with tarfile.open(fileobj=io.BytesIO(b),mode='r:gz') as t:
   m=next(m for m in t.getmembers() if m.isfile() and m.name.split('/')[-1]=='blocky');data=t.extractfile(m).read()
  assert hashlib.sha256(data).hexdigest()==BINARY_SHA
 target.write_bytes(data);target.chmod(0o700);return target

def question_end(packet):
 i=12;parts=[]
 while packet[i]:
  n=packet[i];parts.append(packet[i+1:i+1+n].decode('ascii'));i+=1+n
 return '.'.join(parts),i+5

def skip_name(packet,i):
 while packet[i]:
  if packet[i]&0xc0==0xc0:return i+2
  i+=1+packet[i]
 return i+1

def query(port,name):
 tx=secrets.randbelow(65536);q=struct.pack('!HHHHHH',tx,0x100,1,0,0,0)+b''.join(bytes([len(x)])+x.encode() for x in name.split('.'))+b'\0'+struct.pack('!HH',1,1)
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
  s.settimeout(5);s.sendto(q,('127.0.0.1',port));b=s.recv(8192)
 ident,flags,qd,an,ns,ar=struct.unpack('!6H',b[:12]);assert ident==tx and flags&0x8000 and not flags&0x200
 _,i=question_end(b);answers=[]
 for _ in range(an):
  i=skip_name(b,i);typ,cls,ttl,n=struct.unpack('!HHIH',b[i:i+10]);i+=10
  if typ==1 and cls==1 and n==4:answers.append(socket.inet_ntoa(b[i:i+n]))
  i+=n
 return {'name':name,'rcode':flags&15,'answers':answers}

def main():
 import pymysql
 p=argparse.ArgumentParser();p.add_argument('--binary',type=Path);p.add_argument('--min-free-mib',type=int,default=2048);p.add_argument('--queries',type=int,default=64);p.add_argument('--workers',type=int,default=4);p.add_argument('--out',type=Path,default=ROOT/'artifacts'/('blocky-'+uuid.uuid4().hex[:12]));a=p.parse_args()
 if not 1<=a.queries<=8192 or not 1<=a.workers<=64:p.error('Bounds: 1..8192 queries and 1..64 workers')
 if 'MO_PASSWORD' not in os.environ:p.error('MO_PASSWORD is required')
 if a.min_free_mib<128 or (a.min_free_mib<2048 and (not a.binary or a.queries>64)):p.error('Below 2 GiB requires a local pinned binary and basic workload')
 if shutil.disk_usage(ROOT).free<a.min_free_mib*1024**2:p.error('Insufficient configured disk headroom')
 a.out.mkdir(parents=True,exist_ok=False);schema='mo_reg_blocky_'+uuid.uuid4().hex[:16];private=ROOT/'runtime'/schema;private.mkdir(mode=0o700,parents=True)
 cfg=dict(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),user=os.getenv('MO_USER','root'),password=os.environ['MO_PASSWORD'],charset='utf8mb4',autocommit=True,connect_timeout=10,read_timeout=30)
 report={'app':'0xERR0R/blocky','version':'v0.35.0','commit':'45a242ffce62c3e203f9a2c8a87fbb8ba106c7ab','binary_sha256':BINARY_SHA,'schema':schema,'native_runtime_attempted':False,'native_GORM_migration':True,'source_edits':False,'min_free_mib':a.min_free_mib,'checks':[],'started_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())};proc=None;log=None;up=None;finish=threading.Event()
 def check(name,value,**metrics):
  report['checks'].append({'name':name,'passed':bool(value),**metrics})
  if not value:raise AssertionError(name)
 def stop():
  nonlocal proc
  if proc and proc.poll() is None:
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
  proc=None
 try:
  app=binary(a.binary,a.min_free_mib)
  with pymysql.connect(**cfg) as c:
   with c.cursor() as q:q.execute('SELECT VERSION()');report['server_version']=q.fetchone()[0];check('actual_matrixone','MatrixOne' in report['server_version']);q.execute('CREATE DATABASE `'+schema+'`')
  up=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);up.bind(('127.0.0.1',0));up.settimeout(.2);up_port=up.getsockname()[1]
  def upstream():
   while not finish.is_set():
    try:b,addr=up.recvfrom(8192)
    except socket.timeout:continue
    except OSError:return
    name,end=question_end(b);nx='.nx.' in name;answer=b'' if nx else b'\xc0\x0c'+struct.pack('!HHIH',1,1,60,4)+socket.inet_aton('192.0.2.10');flags=0x8183 if nx else 0x8180
    up.sendto(b[:2]+struct.pack('!HHHHH',flags,1,0 if nx else 1,0,0)+b[12:end]+answer,addr)
  thread=threading.Thread(target=upstream,daemon=True);thread.start()
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  host=cfg['host'];host='['+host+']' if ':' in host else host
  target=f"{cfg['user']}:{cfg['password']}@tcp({host}:{cfg['port']})/{schema}?charset=utf8mb4&parseTime=True&loc=UTC"
  conf={'upstreams':{'init':{'strategy':'fast'},'groups':{'default':['127.0.0.1:'+str(up_port)]}},'ports':{'dns':['127.0.0.1:'+str(port)],'http':[]},'queryLog':{'type':'mysql','target':target,'flushInterval':'200ms','logRetentionDays':0,'creationAttempts':1},'clientLookup':{'clients':{'回归客户端 😀':['127.0.0.1']}},'blocking':{'denylists':{'test':['*.denied.example.com\n']},'clientGroupsBlock':{'default':['test']}},'log':{'level':'warn'}}
  confpath=private/'private-config.yml';confpath.write_text(json.dumps(conf,ensure_ascii=False));confpath.chmod(0o600)
  log=os.fdopen(os.open(private/'native.log',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb')
  def start():
   nonlocal proc
   env={**os.environ,'GOMAXPROCS':'2','GOMEMLIMIT':'512MiB'};proc=subprocess.Popen([str(app),'--config',str(confpath),'serve'],cwd=private,env=env,stdout=log,stderr=log,start_new_session=True);report['native_runtime_attempted']=True
   deadline=time.monotonic()+45
   while time.monotonic()<deadline:
    if proc.poll() is not None:raise RuntimeError('Native app startup exited; private log retained')
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.3):return
    except OSError:time.sleep(.15)
   raise TimeoutError('DNS listener startup')
  start();check('native_migration_and_DNS_listener',True)
  run=uuid.uuid4().hex[:12];names=[f'q{i}-{run}.'+(['ok','nx','denied'][i%3])+'.example.com' for i in range(a.queries)];report['query_cohort']=run
  started=time.monotonic()
  with ThreadPoolExecutor(max_workers=a.workers) as pool:responses=list(pool.map(lambda n:query(port,n),names))
  elapsed=time.monotonic()-started
  check('exact_DNS_answers_and_blocking',all(r['rcode']==(3 if i%3==1 else 0) and r['answers']==([] if i%3==1 else ['0.0.0.0'] if i%3==2 else ['192.0.2.10']) for i,r in enumerate(responses)),queries=len(responses),workers=a.workers,seconds=round(elapsed,4),queries_per_second=round(len(responses)/elapsed,2))
  expected=set(names)
  def audit(phase):
   deadline=time.monotonic()+30
   while time.monotonic()<deadline:
    with pymysql.connect(**cfg,database=schema) as c:
     with c.cursor() as q:q.execute('SELECT id,question_name,question_type,response_code,response_type,answer,client_ip,client_name FROM log_entries');rows=q.fetchall()
    relevant=[r for r in rows if r[1] in expected]
    report['last_SQL_audit']={'phase':phase,'expected':len(expected),'observed':len(relevant),'unique_names':len({r[1] for r in relevant}),'missing':len(expected-{r[1] for r in relevant})}
    if len(relevant)==len(expected):
     check(phase+'_one_row_per_native_query',len({r[0] for r in relevant})==len(expected) and len({r[1] for r in relevant})==len(expected))
     for r in relevant:
      idx=names.index(r[1]);assert r[2]=='A' and r[3]==('NXDOMAIN' if idx%3==1 else 'NOERROR') and r[4]==('BLOCKED' if idx%3==2 else 'RESOLVED') and r[5]==('' if idx%3==1 else 'A (0.0.0.0)' if idx%3==2 else 'A (192.0.2.10)') and r[6]=='127.0.0.1' and r[7]=='回归客户端 😀','exact SQL query-log values'
     return rows
    time.sleep(.2)
   raise TimeoutError('Native logs did not persist completely')
  rows=audit('initial');check('SQL_exact_DNS_values_and_Unicode_client',True,persisted=len(rows))
  before={r[0]:r for r in rows};pid=proc.pid;stop();start();check('real_process_restart',proc.pid!=pid);after=audit('restart');check('restart_exact_querylog_durability',{r[0]:r for r in after}==before)
  newname='restart-'+run+'.ok.example.com';r=query(port,newname);check('restart_native_DNS_query',r['answers']==['192.0.2.10'])
  deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   with pymysql.connect(**cfg,database=schema) as c:
    with c.cursor() as q:q.execute('SELECT question_type,response_code,answer FROM log_entries WHERE question_name=%s',(newname,));new=q.fetchall()
   if new:break
   time.sleep(.2)
  check('restart_native_database_writer',new==(('A','NOERROR','A (192.0.2.10)'),));report['passed']=True
 except Exception as e:
  report['passed']=False;report['error_type']=type(e).__name__
  if isinstance(e,AssertionError):report['failed_check']=str(e)
 finally:
  stop();finish.set()
  if up:up.close()
  if log:log.close()
 report['finished_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());(a.out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 checks=report['checks'][:]
 if not report['passed'] and all(x['passed'] for x in checks):checks.append({'name':'native_execution','passed':False})
 suite=ET.Element('testsuite',name='blocky-native',tests=str(len(checks)),failures=str(sum(not c['passed'] for c in checks)))
 for c in checks:
  tc=ET.SubElement(suite,'testcase',name=c['name'],classname='blocky.native')
  if not c['passed']:ET.SubElement(tc,'failure',message=c['name'])
 ET.ElementTree(suite).write(a.out/'junit.xml',encoding='utf-8',xml_declaration=True);print(json.dumps({'passed':report['passed'],'schema':schema,'queries':a.queries,'workers':a.workers,'error_type':report.get('error_type'),'failed_check':report.get('failed_check')}));return int(not report['passed'])
if __name__=='__main__':raise SystemExit(main())
