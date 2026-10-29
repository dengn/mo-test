"""Portable test connections. Does not launch/stop services or delete data dirs/buckets."""
import os,sys,time,json,datetime,hashlib,decimal,shutil,threading,statistics,subprocess,signal
from pathlib import Path
import pymysql

REF='652c643666428f1c434e03369834f2a9bead7c27'
DS=os.environ.get('MO_TEST_DATABASE','')
import re
if not re.fullmatch(r'mo_ecosystem_[a-z0-9_]{1,40}',DS):
 raise RuntimeError('Set MO_TEST_DATABASE=mo_ecosystem_<unique_run_id>; use only a dedicated synthetic test database')
B=Path(os.environ.get('MO_CASE_OUTPUT','work/ecosystem-replay')).resolve()
B.mkdir(parents=True,exist_ok=True)
def endpoint(role):
 prefix='MO' if role==6001 else 'MYSQL' if role==13306 else None
 if prefix is None:raise ValueError('Unknown logical endpoint role')
 password=os.environ.get(prefix+'_PASSWORD')
 if password is None:raise RuntimeError('Set '+prefix+'_PASSWORD explicitly (empty password may be intentional)')
 return {'host':os.environ.get(prefix+'_HOST','127.0.0.1'),
         'port':int(os.environ.get(prefix+'_PORT',str(role))),
         'user':os.environ.get(prefix+'_USER','root'),'password':password,'database':DS}
def connector_options(role):return endpoint(role)
def sqlalchemy_url(role):
 from sqlalchemy.engine import URL
 e=endpoint(role);e['username']=e.pop('user')
 return URL.create('mysql+pymysql',**e)
def jdbc_url(role):
 e=endpoint(role)
 return f"jdbc:mysql://{e['host']}:{e['port']}/{DS}?useSSL=false&characterEncoding=utf8&serverTimezone=UTC"
def odbc_connection_string(driver,e):
 # Braced values also handle semicolons and right braces in configured passwords.
 def val(x):
  x=str(x)
  return '{'+x.replace('}','}}')+'}' if any(c in x for c in ';{}') or x!=x.strip() else x
 return ';'.join(k+'='+val(v) for k,v in {'DRIVER':driver,'SERVER':e['host'],'PORT':e['port'],
    'UID':e['user'],'PWD':e['password'],'DATABASE':DS,'SSLMODE':'DISABLED','CHARSET':'utf8mb4'}.items())
def db(port=6001,database=DS,autocommit=True,**extra):
 e=endpoint(port);e['database']=database
 return pymysql.connect(**e,autocommit=autocommit,charset='utf8mb4',connect_timeout=5,
                        read_timeout=90,write_timeout=60,**extra)
def sql(q,args=None,port=6001,database=DS):
 with db(port,database) as d,d.cursor() as c:
  c.execute(q,args);return c.fetchall() if c.description else c.rowcount
def dump(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+'.tmp')
 tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str));tmp.replace(path)
def initialize():
 for role in [6001,13306]:
  try:sql('CREATE DATABASE `'+DS+'`',port=role,database=None)
  except pymysql.MySQLError as e:
   if not ('exists' in str(e).lower() or 'already exist' in str(e).lower()):raise
   # Existing database without the correct ownership marker is never adopted.
   check_owner(role);continue
  sql('CREATE TABLE _mo_ecosystem_owner (run_database VARCHAR(64) PRIMARY KEY)',port=role)
  sql('INSERT INTO _mo_ecosystem_owner VALUES(%s)',(DS,),port=role)
 verify_ownership()
def check_owner(role):
 rows=sql('SELECT run_database FROM _mo_ecosystem_owner',port=role)
 if rows!=((DS,),):raise RuntimeError('Database ownership marker mismatch')
def verify_ownership():
 for role in [6001,13306]:check_owner(role)
def guard():
 free=shutil.disk_usage(B).free;floor=int(os.environ.get('MO_CASE_MIN_FREE_MIB','600'))*1024**2
 if free<floor:raise RuntimeError(f'test resource guard: {free} free bytes < {floor}; not a MatrixOne failure')
 # All data/outputs share the distinct tmpfs; do not use the full root fs.
 usage=shutil.disk_usage(B)
 if usage.total-usage.free>4*1024**3:raise RuntimeError('test resource guard: temporary filesystem usage exceeds4GiB')
 m={x.split()[0]:int(x.split()[1]) for x in Path('/sys/fs/cgroup/memory.stat').read_text().splitlines()}
 limit=int(Path('/sys/fs/cgroup/memory.max').read_text())
 unavailable=sum(m.get(x,0) for x in ['anon','shmem','kernel','file_dirty','file_writeback','unevictable'])
 if limit-unavailable<3*1024**3:raise RuntimeError('test resource guard: less than3GiB estimated memory headroom after reclaimable file cache')
 return free
def percentile(v,p):
 if not v:return None
 s=sorted(v);return s[min(len(s)-1,int((len(s)-1)*p))]
def stats(v):return {'n':len(v),'p50_ms':percentile(v,.5),'p95_ms':percentile(v,.95),'p99_ms':percentile(v,.99),'max_ms':max(v) if v else None}
def resources():
 result={'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'disk_free':shutil.disk_usage(B).free,
         'scope':'current host cgroup and output filesystem; no historical PID reused'}
 for name in ['cpu.stat','memory.current','memory.events','io.stat']:
  p=Path('/sys/fs/cgroup')/name
  if p.exists():result[name]=p.read_text()
 return result
