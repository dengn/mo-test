"""Endpoint configuration and ownership-checked database cleanup for regressions."""
import argparse,json,os,re,time,uuid,sys
from importlib.metadata import version as distribution_version
from pathlib import Path
import pymysql

def connection_config():
    return dict(host=os.getenv('MO_HOST','127.0.0.1'),port=int(os.getenv('MO_PORT','6001')),user=os.getenv('MO_USER','root'),password=os.getenv('MO_PASSWORD','111'),charset='utf8mb4',autocommit=True,connect_timeout=5,read_timeout=20,write_timeout=20)

def query(config,sql,args=None):
    with pymysql.connect(**config) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql,args)
            return cursor.fetchall()

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)

def registry_path():return Path(os.environ['MO_REGISTRY'])

def register_database(name):
    path=registry_path();value=json.loads(path.read_text()) if path.exists() else dict(run_id=os.environ['MO_RUN_ID'],databases=[],cleaned=[])
    if value['run_id']!=os.environ['MO_RUN_ID']:raise RuntimeError('Registry belongs to a different run')
    value['databases'].append(name);write_json(path,value)

def cleanup(path,run_id):
    path=Path(path)
    if not re.fullmatch('[0-9a-f]{12}',run_id):raise ValueError('Invalid run id')
    if not path.exists():return
    value=json.loads(path.read_text())
    if value['run_id']!=run_id:raise RuntimeError('Registry belongs to a different run')
    for name in value['databases']:
        if name in value['cleaned']:continue
        if not re.fullmatch('ai_reg_'+run_id+'_[0-9a-f]{12}',name):raise RuntimeError('Refusing to drop a database outside this run')
        query(connection_config(),'DROP DATABASE IF EXISTS `'+name+'`')
        value['cleaned'].append(name);write_json(path,value)

class TestDatabase:
    __test__=False
    def __init__(self):
        self.name='ai_reg_'+os.environ['MO_RUN_ID']+'_'+uuid.uuid4().hex[:12]
        # Register before CREATE so a timeout after server-side creation can be cleaned.
        register_database(self.name)
        query(connection_config(),'CREATE DATABASE `'+self.name+'`')
        self.config=dict(connection_config(),database=self.name)
    def __repr__(self):return f'TestDatabase({self.name!r})'
    def query(self,sql,args=None):return query(self.config,sql,args)
    @property
    def sdk_config(self):return {k:v for k,v in self.config.items() if k in ['host','port','user','password','database']}
    def url(self,driver='pymysql'):
        from sqlalchemy.engine import URL
        return URL.create('mysql+'+driver,username=self.config['user'],password=self.config['password'],host=self.config['host'],port=self.config['port'],database=self.name).render_as_string(hide_password=False)
    def drop(self):
        query(connection_config(),'DROP DATABASE IF EXISTS `'+self.name+'`')
        path=registry_path();value=json.loads(path.read_text())
        if self.name not in value['cleaned']:value['cleaned'].append(self.name)
        write_json(path,value)

def wait_ready(seconds):
    deadline=time.monotonic()+seconds
    while True:
        try:
            assert query(connection_config(),'SELECT 1')==((1,),)
            version=query(connection_config(),'SELECT version()')[0][0]
            try:commit=query(connection_config(),'SELECT git_version()')[0][0]
            except pymysql.MySQLError:commit=None
            return dict(version=version,commit=commit)
        except (pymysql.MySQLError,OSError):
            if time.monotonic()>=deadline:raise
            time.sleep(.5)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--wait',type=int);parser.add_argument('--cleanup');parser.add_argument('--run-id');parser.add_argument('--environment');parser.add_argument('--packages',default='{}')
    args=parser.parse_args()
    if args.wait is not None:
        info=wait_ready(args.wait)
        expected=json.loads(args.packages);actual={name:distribution_version(name) for name in expected}
        if actual!=expected:raise RuntimeError('Direct dependency versions differ from projects.json: '+str(actual))
        info.update(python=sys.version.split()[0],packages=actual)
        if args.environment:write_json(args.environment,info)
        print(json.dumps(info))
    if args.cleanup:cleanup(args.cleanup,args.run_id)
