"""Superset native Alembic/roles, SQL Lab fixture, chart/dashboard and restart."""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import uuid

from native_common import Client, Processes, connection_config, finish, port, private_file, runtime_root
from superset_runtime import prepare

ROOT = Path(__file__).resolve().parent
HEAD = '4b2a8c9d3e1f'


def uri(cfg: dict, schema: str) -> str:
    quote = urllib.parse.quote
    host = cfg['host'] if ':' not in cfg['host'] else '['+cfg['host']+']'
    return 'mysql+pymysql://'+quote(cfg['user'],safe='')+':'+quote(cfg['password'],safe='')+'@'+host+':'+str(cfg['port'])+'/'+schema+'?charset=utf8mb4'


def main() -> int:
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-config', type=Path, default=os.getenv('MO_SUPERSET_RUNTIME_CONFIG') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT/'artifacts'/('superset-'+uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128: parser.error('Minimum disk admission floor is 128 MiB')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    schema='mo_reg_superset_'+uuid.uuid4().hex[:16]; analytics=schema+'_analytics'
    private=runtime_root()/schema;private.mkdir(mode=0o700)
    report={'app':'apache/superset','version':'6.1.0','schema':schema,'analytics_schema':analytics,'passed':False,'checks':[],
            'existing_databases_modified':False,'manual_users_or_migration_stamps':False,'native_runtime_attempted':False,
            'min_free_mib':args.min_free_mib,'limitations':['prepared SDK only; complete dependency cold installation unverified',
            'binary capacity/MySQL collation/downgrades/populated upgrades/full UI unverified',
            'single-value nullable ENUM used for exact datasource CHECK; other CHECK constraints unchanged',
            'native synchronous SQL Lab and simple cache; async Celery/full visualization/export/load unverified']}
    owned=Processes(private,report);stage='admission'
    def check(name: str, value: object) -> None:
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value: raise AssertionError(name)
    try:
        if not args.runtime_config or shutil.disk_usage(runtime_root()).free < args.min_free_mib*1024**2:
            raise RuntimeError('Prepared SDK config and required runtime headroom missing')
        stage='verified_SDK';python,core,identity=prepare(args.runtime_config,private);report['SDK_identity']=identity
        check('pinned_official_wheel_and_dependency_files',identity['dependency_packages_verified']==162 and identity['dependency_files_verified']==15043)
        check('pinned_private_core_source',identity['core_git_blobs_verified']==27)
        cfg=connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()');report['server_version'],report['runtime_git_version']=q.fetchone()
                check('actual_matrixone','MatrixOne' in report['server_version'])
                for name in [schema,analytics]:q.execute('CREATE DATABASE `'+name+'` CHARACTER SET utf8mb4')
        cfg['database']=schema
        def sql(query: str, params: tuple=()) -> tuple:
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query,params);return q.fetchall()
        credentials={'secret_key':secrets.token_urlsafe(48),'admin_password':'Mo1-'+secrets.token_hex(12),'other_password':'Mo1-'+secrets.token_hex(12)}
        private_file(private/'credentials.json',json.dumps(credentials))
        config=private/'superset_config.py'
        private_file(config,"import os\nfrom pathlib import Path\nimport superset_core\nassert Path(superset_core.__file__).resolve().is_relative_to(Path(os.environ['MO_NATIVE_CORE_DIR']).resolve())\nimport matrixone_adapter\nSECRET_KEY=os.environ['MO_NATIVE_SECRET_KEY']\nSQLALCHEMY_DATABASE_URI=os.environ['MO_NATIVE_METADATA_URI']\nDATA_DIR=os.environ['MO_NATIVE_DATA_DIR']\nWTF_CSRF_ENABLED=True\nENABLE_PROXY_FIX=False\nSQLALCHEMY_ENGINE_OPTIONS={'pool_size':4,'max_overflow':4,'pool_pre_ping':True}\n"+''.join(k+"={'CACHE_TYPE':'SimpleCache','CACHE_DEFAULT_TIMEOUT':300}\n" for k in ['CACHE_CONFIG','FILTER_STATE_CACHE_CONFIG','EXPLORE_FORM_DATA_CACHE_CONFIG','DATA_CACHE_CONFIG']))
        data=private/'data';data.mkdir(mode=0o700)
        env={**os.environ,'SUPERSET_CONFIG_PATH':str(config),'FLASK_APP':'superset','SUPERSET_HOME':str(private),
             'PYTHONPATH':str(private)+os.pathsep+str(core),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1',
             'PYTHONPYCACHEPREFIX':str(private/'pycache'),'MPLCONFIGDIR':str(private/'matplotlib'),
             'MO_NATIVE_CORE_DIR':str(core),'MO_NATIVE_SECRET_KEY':credentials['secret_key'],'MO_NATIVE_METADATA_URI':uri(cfg,schema),'MO_NATIVE_DATA_DIR':str(data)}
        cli=[str(python),'-c','from superset.cli.main import superset;superset()']
        def task(label: str, args: list[str], task_env: dict|None=None, timeout: int=600) -> None:
            p=owned.start(cli+args,private,{**env,**(task_env or {})},label)
            try: code=p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:owned.stop(p);raise
            check(label,code==0)
        stage='native_migrations';report['native_runtime_attempted']=True;task('native_db_upgrade',['db','upgrade'])
        upgrade_log=private/'native_db_upgrade-0.log'
        report['native_upgrade_log_events']=upgrade_log.read_text(errors='replace').count('Running upgrade')
        check('native_all_344_upgrade_events',report['native_upgrade_log_events']==344)
        check('native_Alembic_release_head',sql('SELECT version_num FROM alembic_version')==((HEAD,),))
        report['native_table_count']=len(sql('SHOW TABLES'))
        # Passwords are consumed through the native CLI's --password option inside Python,
        # keeping them out of the operating system command line and public records.
        password_cli=[str(python),'-c',"import os,sys;sys.argv+=['--password',os.environ['MO_NATIVE_USER_PASSWORD']];from superset.cli.main import superset;superset()"]
        def user_task(label: str, username: str, role: str, password: str) -> None:
            args=['fab','create-admin' if role=='Admin' else 'create-user','--username',username,'--firstname','Native','--lastname','Regression','--email',username+'@example.test']
            if role!='Admin':args+=['--role',role]
            p=owned.start(password_cli+args,private,{**env,'MO_NATIVE_USER_PASSWORD':password},label)
            check(label,p.wait(timeout=180)==0)
        stage='native_users';user_task('native_admin_create','moadmin','Admin',credentials['admin_password'])
        task('native_roles_init',['init']);user_task('native_Gamma_user_create','moother','Gamma',credentials['other_password'])
        users=sql('SELECT u.username,r.name,u.active,LENGTH(u.password) FROM ab_user u JOIN ab_user_role ur ON ur.user_id=u.id JOIN ab_role r ON r.id=ur.role_id ORDER BY u.username')
        check('native_user_roles_and_hashes',tuple(r[:3] for r in users)==(('moadmin','Admin',1),('moother','Gamma',1)) and all(r[3]>60 for r in users))
        base='http://127.0.0.1:'+str(port());anonymous=Client(base)
        def start() -> subprocess.Popen:
            p=owned.start([str(python),'-m','gunicorn','superset.app:create_app()','--bind',base[7:],'--workers','1','--threads','4','--timeout','120','--access-logfile','-'],private,env,'superset')
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                if p.poll() is not None:raise RuntimeError('Native Superset exited; private log retained')
                try:
                    if anonymous.request('GET','/health',timeout=3).status_code==200:return p
                except(OSError,urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native Superset startup')
        proc=start();admin=Client(base);other=Client(base)
        def api(client: Client, method: str, path: str, body: dict|None=None, denied: bool=False, denial_codes: set|None=None) -> dict|bool:
            response=client.request(method,path,json_data=body,timeout=120)
            if denied:return response.status_code in (denial_codes or {401,403,404})
            if response.status_code not in {200,201}:
                private_file(private/('failed-API-'+uuid.uuid4().hex+'.private'),response.content)
                raise AssertionError('native_API_'+method+'_'+path)
            return response.json()
        def login(client: Client, username: str, label: str) -> None:
            doc=api(client,'POST','/api/v1/security/login',{'username':username,'password':credentials[label+'_password'],'provider':'db','refresh':True})
            token=doc['access_token'];credentials[label+'_access_token']=token
            client.headers['Authorization']='Bearer '+token
            client.headers['X-CSRFToken']=api(client,'GET','/api/v1/security/csrf_token/')['result']
            (private/'credentials.json').write_text(json.dumps(credentials))
        login(admin,'moadmin','admin');login(other,'moother','other')
        check('native_password_JWT_and_CSRF',all(client.headers.get('X-CSRFToken') for client in [admin,other]))
        check('wrong_password_denied',api(Client(base),'POST','/api/v1/security/login',{'username':'moadmin','password':'incorrect-'+uuid.uuid4().hex,'provider':'db'},denied=True))
        stage='native_database_and_SQL_Lab'
        connection_body={'database_name':'原生MatrixOne数据 中文 😀𠮷','sqlalchemy_uri':uri(cfg,analytics),'expose_in_sqllab':True,'allow_run_async':False,'allow_dml':True}
        database=api(admin,'POST','/api/v1/database/',connection_body)['id']
        check('native_database_metadata',sql('SELECT database_name FROM dbs WHERE id=%s',(database,))==((connection_body['database_name'],),))
        before=sql('SELECT COUNT(*) FROM dbs')
        check('ordinary_user_database_create_denied_zero_write',api(other,'POST','/api/v1/database/',connection_body,denied=True) and sql('SELECT COUNT(*) FROM dbs')==before)
        def sqllab(statement: str, denied: bool=False) -> dict|bool:
            return api(admin,'POST','/api/v1/sqllab/execute/',{'database_id':database,'sql':statement,'schema':analytics,'runAsync':False,'expand_data':True},denied=denied)
        sqllab('CREATE TABLE sales_fixture (id INT PRIMARY KEY, region VARCHAR(64), amount_cents INT)')
        values=','.join("("+str(i)+",'区域 中文 😀𠮷-"+str(i%10)+"',"+str(i)+")" for i in range(1,1001))
        sqllab('INSERT INTO sales_fixture VALUES '+values)
        check('native_SQL_Lab_all_fixture_values',sql('SELECT id,region,amount_cents FROM `'+analytics+'`.sales_fixture ORDER BY id')==tuple((i,'区域 中文 😀𠮷-'+str(i%10),i) for i in range(1,1001)))
        total=sqllab('SELECT COUNT(*) AS n,SUM(amount_cents) AS total_cents FROM sales_fixture')['data'][0]
        check('native_SQL_Lab_aggregate',Decimal(str(total['n']))==1000 and Decimal(str(total['total_cents']))==500500)
        dataset=api(admin,'POST','/api/v1/dataset/',{'database':database,'schema':analytics,'table_name':'sales_fixture'})['id']
        check('native_dataset_database_relation',sql('SELECT table_name,database_id FROM `tables` WHERE id=%s',(dataset,))==(('sales_fixture',database),))
        stage='native_chart_and_dashboard'
        title='私有仪表板 中文 😀𠮷';dashboard=api(admin,'POST','/api/v1/dashboard/',{'dashboard_title':title,'published':False})['id']
        chart_name='原生销售图表 中文 😀𠮷'
        chart=api(admin,'POST','/api/v1/chart/',{'slice_name':chart_name,'viz_type':'table','datasource_id':dataset,'datasource_type':'table','params':json.dumps({'datasource':str(dataset)+'__table','viz_type':'table','all_columns':['region','amount_cents'],'row_limit':1000}),'dashboards':[dashboard]})['id']
        check('SQL_chart_dataset_dashboard_links',sql('SELECT s.slice_name,s.datasource_id,s.datasource_type,d.dashboard_title FROM slices s JOIN dashboard_slices ds ON ds.slice_id=s.id JOIN dashboards d ON d.id=ds.dashboard_id WHERE s.id=%s',(chart,))==((chart_name,dataset,'table',title),))
        def chart_data() -> None:
            doc=api(admin,'POST','/api/v1/chart/data',{'datasource':{'id':dataset,'type':'table'},'queries':[{'columns':[],'metrics':[{'expressionType':'SQL','sqlExpression':'SUM(amount_cents)','label':'total_cents'}],'row_limit':1000,'is_timeseries':False}],'result_format':'json','result_type':'full','force':True})
            check('native_chart_aggregate_exact',Decimal(str(doc['result'][0]['data'][0]['total_cents']))==500500)
        chart_data()
        check('anonymous_dashboard_denied',api(anonymous,'GET','/api/v1/dashboard/'+str(dashboard),denied=True))
        check('ordinary_private_dashboard_denied',api(other,'GET','/api/v1/dashboard/'+str(dashboard),denied=True))
        before=sql('SELECT dashboard_title FROM dashboards WHERE id=%s',(dashboard,))
        check('ordinary_dashboard_update_denied_zero_write',api(other,'PUT','/api/v1/dashboard/'+str(dashboard),{'dashboard_title':'invalid cross-user update'},denied=True) and sql('SELECT dashboard_title FROM dashboards WHERE id=%s',(dashboard,))==before)
        invalid=Client(base);invalid.headers={**admin.headers,'X-CSRFToken':'deliberately-invalid-token'}
        before=sql('SELECT COUNT(*) FROM dashboards')
        check('invalid_CSRF_denied_zero_write',api(invalid,'POST','/api/v1/dashboard/',{'dashboard_title':'invalid CSRF'},denied=True,denial_codes={400,403}) and sql('SELECT COUNT(*) FROM dashboards')==before)
        title='更新仪表板 中文 😀𠮷';api(admin,'PUT','/api/v1/dashboard/'+str(dashboard),{'dashboard_title':title})
        def readback(prefix: str) -> None:
            d=api(admin,'GET','/api/v1/dashboard/'+str(dashboard))['result'];c=api(admin,'GET','/api/v1/chart/'+str(chart))['result']
            check(prefix+'_native_dashboard_exact',d['dashboard_title']==title)
            check(prefix+'_native_chart_links',c['slice_name']==chart_name and c['datasource_id']==dataset and any(d['id']==dashboard for d in c['dashboards']))
        readback('before_restart')
        # Exercise the enforced ENUM through the real SQL Lab, not a Python DML probe.
        response=admin.request('POST','/api/v1/sqllab/execute/',json_data={'database_id':database,'sql':'UPDATE `'+schema+'`.slices SET datasource_type=\'invalid\' WHERE id='+str(chart),'schema':analytics,'runAsync':False,'expand_data':True},timeout=120)
        check('native_invalid_datasource_ENUM_denied',response.status_code in {400,422,500} and 'convert to MySQL enum failed' in response.text and 'item invalid is not in enum [table]' in response.text and sql('SELECT datasource_type FROM slices WHERE id=%s',(chart,))==(('table',),))
        stage='native_restart';previous=proc.pid;owned.stop(proc);proc=start();check('real_Gunicorn_process_restart',proc.pid!=previous)
        readback('after_restart');chart_data()
        check('after_restart_Alembic_and_analytics_exact',sql('SELECT version_num FROM alembic_version')==((HEAD,),) and sql('SELECT COUNT(*),SUM(amount_cents) FROM `'+analytics+'`.sales_fixture')==((1000,Decimal('500500')),))
        check('after_restart_other_user_denied',api(other,'GET','/api/v1/dashboard/'+str(dashboard),denied=True))
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),));report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    finish(out,report,'superset-native');return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
