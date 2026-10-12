"""Pinned native Plik server: password auth, file CRUD, real SQL relations, and restart."""
import argparse,base64,hashlib,http.cookiejar,io,json,os,secrets,shutil,signal,socket,subprocess,tarfile,time,urllib.error,urllib.parse,urllib.request,uuid,xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parent
URL='https://github.com/root-gg/plik/releases/download/1.4.2/plik-server-1.4.2-linux-amd64.tar.gz'
ARCHIVE_SHA='328cd739f198f5ca40e5010e61ed6f8a70d5a18d7418b8b543bab1710c92dc61'
BINARY_SHA='e54035ccc6a864cc27f84dc1ba4ce986c0aa86cd3e9194687a8e86e819def060'
def binary(provided, min_free_mib=2048):
 if provided:
  provided=provided.resolve()
  if hashlib.sha256(provided.read_bytes()).hexdigest()!=BINARY_SHA:raise RuntimeError("Official binary hash mismatch")
  return provided
 target=ROOT/'runtime/plik-1.4.2/plikd'
 if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==BINARY_SHA:return target
 target.parent.mkdir(parents=True,exist_ok=True)
 if provided:data=provided.read_bytes()
 else:
  with urllib.request.urlopen(URL,timeout=90) as r:b=r.read(100*1024**2)
  assert hashlib.sha256(b).hexdigest()==ARCHIVE_SHA
  with tarfile.open(fileobj=io.BytesIO(b),mode='r:gz') as t:
   m=next(m for m in t.getmembers() if m.isfile() and m.name.endswith('/server/plikd'));data=t.extractfile(m).read()
 assert hashlib.sha256(data).hexdigest()==BINARY_SHA
 if shutil.disk_usage(ROOT).free<min_free_mib*1024**2+len(data):raise RuntimeError('Keep 2 GiB free after installing app')
 target.write_bytes(data);target.chmod(0o700);return target

def main():
 import pymysql
 p=argparse.ArgumentParser();p.add_argument('--binary',type=Path);p.add_argument('--min-free-mib',type=int,default=2048);p.add_argument('--files',type=int,default=16);p.add_argument('--workers',type=int,default=4);p.add_argument('--out',type=Path,default=ROOT/'artifacts'/('plik-'+uuid.uuid4().hex[:12]));a=p.parse_args()
 if not 1<=a.files<=1024 or not 1<=a.workers<=64:p.error('Bounds: 1..1024 files, 1..64 workers')
 if 'MO_PASSWORD' not in os.environ:p.error('MO_PASSWORD is required')
 if a.min_free_mib<128 or (a.min_free_mib<2048 and (not a.binary or a.files>16)):p.error('Below 2 GiB requires a local pinned binary and basic workload')
 if shutil.disk_usage(ROOT).free<a.min_free_mib*1024**2:p.error('Insufficient configured disk headroom')
 a.out.mkdir(parents=True,exist_ok=False);schema='mo_reg_plik_'+uuid.uuid4().hex[:16];private=ROOT/'runtime'/schema;private.mkdir(mode=0o700,parents=True)
 cfg=dict(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),user=os.getenv('MO_USER','root'),password=os.environ['MO_PASSWORD'],charset='utf8mb4',autocommit=True,connect_timeout=10,read_timeout=30)
 report={'app':'root-gg/plik','version':'1.4.2','commit':'ed7f43fbe1bd0a8a3d3365fd83c17c75e9ee4bcc','binary_sha256':BINARY_SHA,'schema':schema,'native_runtime_attempted':False,'native_GORM_gormigrate_initialization':True,'source_edits':False,'native_password_auth_and_CSRF_retained':True,'min_free_mib':a.min_free_mib,'checks':[],'passed':False};proc=None;log=None;stage='download';owner='reg_owner';owner_pass=secrets.token_urlsafe(24);other='reg_outsider';other_pass=secrets.token_urlsafe(24)
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 base='http://127.0.0.1:'+str(port)
 def check(name,value,**metrics):
  report['checks'].append({'name':name,'passed':bool(value),**metrics})
  if not value:raise AssertionError(name)
 def client():
  jar=http.cookiejar.CookieJar();return urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar)),jar
 admin,admin_jar=client();outsider,other_jar=client();anon,_=client()
 def request(method,path,data=None,opener=None,jar=None,raw=None,headers=None,expect=200,binary_response=False,bad_csrf=False):
  h=dict(headers or {})
  if data is not None:raw=json.dumps(data,ensure_ascii=False).encode();h['Content-Type']='application/json'
  if jar and method not in {'GET','HEAD'}:
   xsrf=next((c.value for c in jar if c.name=='plik-xsrf'),None)
   if xsrf:h['X-XSRFToken']='invalid-test-xsrf' if bad_csrf else xsrf
  req=urllib.request.Request(base+path,data=raw,headers=h,method=method)
  try:
   with (opener or anon).open(req,timeout=15) as r:status=r.status;b=r.read(2*1024**2)
  except urllib.error.HTTPError as e:status=e.code;b=e.read(10000)
  if status!=expect:
   report['HTTP_failure']={'stage':stage,'method':method,'path':path,'status':status,'expected':expect};raise AssertionError('native HTTP status')
  if binary_response:return b
  try:return json.loads(b) if b else None
  except ValueError:return b.decode('utf8')
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
  host=cfg['host'];host='['+host+']' if ':' in host else host;dsn=f"{cfg['user']}:{cfg['password']}@tcp({host}:{cfg['port']})/{schema}?charset=utf8mb4&parseTime=true&loc=UTC"
  conf=f'''ListenAddress = "127.0.0.1"
ListenPort = {port}
Debug = false
DebugRequests = false
LogLevel = "WARNING"
NoWebInterface = true
FeatureAuthentication = "forced"
FeatureLocalLogin = "enabled"
FeatureApiTokens = "enabled"
MaxFilePerUpload = 2048
MaxFileSizeStr = "2MB"
[DataBackendConfig]
Directory = {json.dumps(str(private/'files'))}
[MetadataBackendConfig]
Driver = "mysql"
ConnectionString = {json.dumps(dsn)}
Debug = false
MaxOpenConns = 16
MaxIdleConns = 4
'''
  config=private/'private-config.toml';config.write_text(conf);config.chmod(0o600);env={k:v for k,v in os.environ.items() if not k.startswith('PLIKD_')};env.update(PLIKD_DEFAULT_ADMIN_LOGIN=owner,PLIKD_DEFAULT_ADMIN_PASSWORD=owner_pass,GOMAXPROCS='2',GOMEMLIMIT='512MiB')
  log=os.fdopen(os.open(private/'native.log',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb')
  def start():
   nonlocal proc
   proc=subprocess.Popen([str(app),'--config',str(config)],cwd=private,env=env,stdout=log,stderr=log,start_new_session=True);report['native_runtime_attempted']=True;deadline=time.monotonic()+45
   while time.monotonic()<deadline:
    if proc.poll() is not None:raise RuntimeError('Native startup exited; private logs retained')
    try:request('GET','/health');return
    except (OSError,AssertionError):time.sleep(.2)
   raise TimeoutError('Native app startup')
  stage='native_initialization';start();check('native_migration_admin_and_health',True)
  stage='native_login';request('POST','/auth/local/login',{'login':owner,'password':'incorrect-test-password'},expect=403);request('POST','/auth/local/login',{'login':owner,'password':owner_pass},opener=admin);me=request('GET','/me',opener=admin);check('native_password_login',me['id']=='local:'+owner and me['admin'])
  stage='native_denials';request('GET','/me',expect=401);request('POST','/upload',{'comments':'must not persist'},expect=400);request('POST','/upload',{'comments':'invalid CSRF must not persist'},opener=admin,jar=admin_jar,bad_csrf=True,expect=403)
  with pymysql.connect(**cfg,database=schema) as c:
   with c.cursor() as q:q.execute('SELECT COUNT(*) FROM uploads');check('anonymous_and_invalid_CSRF_denied_no_writes',q.fetchone()[0]==0)
  # Native invalid-CSRF handling clears authentication cookies. Log in again
  # before the next authorized operation, as a real client must do.
  request('POST','/auth/local/login',{'login':owner,'password':owner_pass},opener=admin)
  stage='native_outsider';user=request('POST','/user',{'provider':'local','login':other,'password':other_pass,'name':'其他用户 😀','admin':False},opener=admin,jar=admin_jar);request('POST','/auth/local/login',{'login':other,'password':other_pass},opener=outsider);request('GET','/stats',opener=outsider,expect=403);check('native_nonadmin_user_and_admin_denial',user['id']=='local:'+other and not user['admin'])
  prefix='native-files-'+uuid.uuid4().hex;stage='native_create_upload';upload=request('POST','/upload',{'comments':prefix+' 中文 😀𠮷','ttl':3600,'removable':False},opener=admin,jar=admin_jar);uid=upload['id'];check('native_upload',bool(uid))
  stage='native_files'
  def add(i):
   data=bytes(range(256))+('中文 😀𠮷 '+str(i)).encode();filename=f'文件-{i}-😀𠮷.bin';boundary='mo-'+secrets.token_hex(12);body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+data+f'\r\n--{boundary}--\r\n'.encode();f=request('POST','/file/'+uid,opener=admin,jar=admin_jar,raw=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary});return {'id':f['id'],'name':filename,'data':data,'md5':hashlib.md5(data).hexdigest(),'response':f}
  then=time.monotonic()
  with ThreadPoolExecutor(max_workers=a.workers) as pool:written=list(pool.map(add,range(a.files)))
  check('concurrent_native_file_uploads',len({x['id'] for x in written})==a.files,files=a.files,workers=a.workers,seconds=round(time.monotonic()-then,4))
  def path(x):return '/file/'+uid+'/'+x['id']+'/'+urllib.parse.quote(x['name'])
  for x in written:
   f=x['response'];assert f['fileName']==x['name'] and f['fileSize']==len(x['data']) and f['fileMd5']==x['md5'] and f['status']=='uploaded'
   assert request('GET',path(x),binary_response=True)==x['data']
  check('exact_native_binary_and_Unicode_downloads',True)
  request('DELETE','/upload/'+uid,opener=outsider,jar=other_jar,expect=403);request('DELETE','/upload/'+uid,expect=403);check('cross_user_and_anonymous_delete_denied',True)
  stage='native_SQL_audit'
  def audit(check_name):
   with pymysql.connect(**cfg,database=schema) as c:
    with c.cursor() as q:
     q.execute('SELECT f.id,f.upload_id,f.name,f.status,f.md5,f.size,u.comments,u.user FROM files f JOIN uploads u ON u.id=f.upload_id WHERE u.id=%s',(uid,));rows=q.fetchall();byid={x[0]:x for x in rows};check(check_name,len(rows)==len(byid)==a.files and all(byid[x['id']][1:]==(uid,x['name'],'uploaded',x['md5'],len(x['data']),prefix+' 中文 😀𠮷','local:'+owner) for x in written));q.execute('SELECT COUNT(*) FROM migrations');report['native_migration_records']=q.fetchone()[0]
   return rows
  before=audit('SQL_exact_file_values_and_upload_owner');stage='native_restart';old=proc.pid;stop();start();check('real_process_restart',proc.pid!=old);check('restart_native_session',request('GET','/me',opener=admin)['id']=='local:'+owner);after=audit('restart_SQL_exact_file_values_and_upload_owner');check('restart_SQL_durability',sorted(before)==sorted(after))
  for x in written:assert request('GET',path(x),binary_response=True)==x['data']
  check('restart_exact_downloads',True)
  stage='native_delete';victim=written[0];request('DELETE',path(victim),opener=admin,jar=admin_jar);request('GET',path(victim),expect=404);check('native_delete_no_longer_downloadable',True)
  with pymysql.connect(**cfg,database=schema) as c:
   with c.cursor() as q:q.execute('SELECT status FROM files WHERE id=%s',(victim['id'],));v=q.fetchone();check('native_delete_database_status',v and v[0] in ('removed','deleted'))
  report['passed']=True
 except Exception as e:
  report.update(error_type=type(e).__name__,failed_stage=stage)
  if isinstance(e,AssertionError):report['failed_check']=str(e)
 finally:
  stop()
  if log:log.close()
 report['time_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());(a.out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));checks=report['checks'][:]
 if not report['passed'] and all(x['passed'] for x in checks):checks.append({'name':'native_execution','passed':False})
 suite=ET.Element('testsuite',name='plik-native',tests=str(len(checks)),failures=str(sum(not x['passed'] for x in checks)))
 for c in checks:
  tc=ET.SubElement(suite,'testcase',name=c['name'],classname='plik.native')
  if not c['passed']:ET.SubElement(tc,'failure',message=c['name'])
 ET.ElementTree(suite).write(a.out/'junit.xml',encoding='utf8',xml_declaration=True);print(json.dumps({'passed':report['passed'],'schema':schema,'stage':report.get('failed_stage'),'error_type':report.get('error_type'),'failed_check':report.get('failed_check'),'HTTP_failure':report.get('HTTP_failure')}));return int(not report['passed'])
if __name__=='__main__':raise SystemExit(main())
