"""Official Grafana native migrations, ordinary-user dashboards/org isolation and restart."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import time
import urllib.error
import uuid

from native_common import Client, Processes, connection_config, finish, port, private_file, runtime_root
from prepare_grafana_sdk import prepare, verify_release

ROOT=Path(__file__).resolve().parent
COMMIT='90ffed056f0884267356c12a0eeb72a022af53f1'


def main():
    import pymysql
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-dir',type=Path,default=os.getenv('MO_GRAFANA_RELEASE_DIR') or None)
    parser.add_argument('--min-free-mib',type=int,default=2048)
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts'/('grafana-'+uuid.uuid4().hex[:12]))
    args=parser.parse_args()
    if args.min_free_mib<128:parser.error('Minimum disk admission floor is 128 MiB')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    schema='mo_reg_grafana_'+uuid.uuid4().hex[:16];private=runtime_root()/schema;private.mkdir(parents=True,mode=0o700)
    report={'app':'grafana/grafana','version':'13.2.3','commit':COMMIT,'schema':schema,'passed':False,'checks':[],
            'native_runtime_attempted':False,'existing_databases_modified':False,'manual_users_or_migration_stamps':False,
            'source_edits':False,'SQL_adapter':'NVARCHAR MODIFY fixed width only; real MatrixOne auth/results',
            'native_disable_legacy_table_rename':True,'min_free_mib':args.min_free_mib,
            'limitations':['unified alerting initialization emits errors and is not certified','plugins/LDAP/OAuth/populated upgrades/full observability queries unverified']}
    owned=Processes(private,report);stage='admission'
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        if shutil.disk_usage(runtime_root()).free<args.min_free_mib*1024**2:raise RuntimeError('Dedicated runtime disk headroom required')
        release=args.release_dir.resolve() if args.release_dir else private/'sdk'
        if not args.release_dir:prepare(release)
        manifest=verify_release(release);report['verified_release_files']=len(manifest['files']);report['official_archive_sha256']=manifest['original_archive_sha256']
        check('full_pinned_official_release',manifest['commit']==COMMIT)
        cfg=connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()');report['server_version'],report['runtime_git_version']=q.fetchone()
                check('actual_matrixone','MatrixOne' in report['server_version']);q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database']=schema
        def sql(query,params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query,params);return q.fetchall()
        credentials={k:secrets.token_urlsafe(32) for k in ['bootstrap_password','owner_password','other_password','secret_key']}
        private_file(private/'credentials.json',json.dumps(credentials))
        gateway_port=port();web_port=port();base='http://127.0.0.1:'+str(web_port)
        env={**os.environ,'GOMAXPROCS':'2','GOMEMLIMIT':'1GiB'}
        gateway=owned.start([sys.executable,str(ROOT/'adapters/grafana_mysql_adapter.py'),'--port',str(gateway_port),
            '--upstream-host',cfg['host'],'--upstream-port',str(cfg['port']),'--audit',str(private/'adapter-audit.jsonl')],private,env,'grafana-relay')
        deadline=time.monotonic()+15
        while True:
            if gateway.poll() is not None:raise RuntimeError('Native DDL relay startup failed')
            try:
                with socket.create_connection(('127.0.0.1',gateway_port),timeout=1):break
            except OSError:
                if time.monotonic()>deadline:raise TimeoutError('Owned SQL relay')
                time.sleep(.1)
        # GF environment variables preserve arbitrary passwords without INI interpolation.
        env.update(GF_PATHS_DATA=str(private/'data'),GF_PATHS_LOGS=str(private/'logs'),GF_PATHS_PLUGINS=str(private/'plugins'),
            GF_PATHS_PROVISIONING=str(private/'provisioning'),GF_SERVER_HTTP_ADDR='127.0.0.1',GF_SERVER_HTTP_PORT=str(web_port),GF_SERVER_ROOT_URL=base+'/',
            GF_DATABASE_TYPE='mysql',GF_DATABASE_HOST='127.0.0.1:'+str(gateway_port),GF_DATABASE_NAME=schema,GF_DATABASE_USER=cfg['user'],GF_DATABASE_PASSWORD=cfg['password'],
            GF_DATABASE_MAX_OPEN_CONN='16',GF_DATABASE_SSL_MODE='false',GF_SECURITY_ADMIN_USER='mo-bootstrap',GF_SECURITY_ADMIN_PASSWORD=credentials['bootstrap_password'],
            GF_SECURITY_SECRET_KEY=credentials['secret_key'],GF_ANALYTICS_REPORTING_ENABLED='false',GF_ANALYTICS_CHECK_FOR_UPDATES='false',
            GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES='false',GF_PLUGINS_PREINSTALL_DISABLED='true',GF_LOG_MODE='console',GF_LOG_LEVEL='warn',
            GF_UNIFIED_STORAGE_DISABLE_LEGACY_TABLE_RENAME='true')
        for folder in ['data','logs','plugins','provisioning']:(private/folder).mkdir(mode=0o700)
        config=private/'grafana.ini';private_file(config,'[log]\nmode = console\n')
        bootstrap,owner,other,anonymous=Client(base),Client(base),Client(base),Client(base)
        def auth(client,username,password):client.headers['Authorization']='Basic '+base64.b64encode((username+':'+password).encode()).decode()
        auth(bootstrap,'mo-bootstrap',credentials['bootstrap_password']);auth(owner,'mo-owner',credentials['owner_password']);auth(other,'mo-other',credentials['other_password'])
        def start():
            proc=owned.start([str(release/'bin/grafana'),'server','--homepath',str(release),'--config',str(config)],private,env,'grafana');report['native_runtime_attempted']=True;deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('Native Grafana startup failed; private log retained')
                try:
                    response=anonymous.request('GET','/api/health',timeout=3)
                    if response.status_code==200 and response.json().get('database')=='ok':return proc,response.json()
                except(OSError,ValueError,urllib.error.URLError):pass
                time.sleep(.25)
            raise TimeoutError('Native Grafana readiness')
        stage='native_migrations';proc,health=start()
        check('native_official_version_and_commit',health['version']=='13.2.3' and len(health['commit'])>=7 and COMMIT.startswith(health['commit']))
        rows=sql('SELECT COUNT(*),SUM(success),SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) FROM migration_log');report['native_migration_count']=rows[0][0]
        check('native_migrations_zero_failures',rows[0][0]>=853 and rows[0][0]==rows[0][1] and rows[0][2]==0)
        check('native_bootstrap_admin',sql("SELECT login,is_admin FROM user")==(('mo-bootstrap',1),))
        def request(client,method,path,data=None,status=200):
            response=client.request(method,path,json_data=data,timeout=90)
            if response.status_code!=status:
                report['failed_HTTP_status']=response.status_code;report['failed_native_endpoint']=path
                private_file(private/('failed-response-'+str(len(report['checks']))+'.json'),response.content)
                raise AssertionError('native_HTTP_'+method+'_'+path)
            return response.json()
        stage='native_users'
        user_ids={}
        for label,client in [('owner',owner),('other',other)]:
            result=request(bootstrap,'POST','/api/admin/users',{'name':label+' 中文 😀𠮷','login':'mo-'+label,'email':label+'@example.test','password':credentials[label+'_password']})
            user_ids[label]=int(result['id']);check('native_ordinary_user_'+label,sql('SELECT login,is_admin FROM user WHERE id=%s',(result['id'],))==(('mo-'+label,0),))
        org=request(bootstrap,'POST','/api/orgs',{'name':'隔离组织 中文 😀𠮷'})['orgId']
        request(bootstrap,'POST','/api/orgs/'+str(org)+'/users',{'loginOrEmail':'mo-owner','role':'Admin'})
        request(owner,'POST','/api/user/using/'+str(org));check('native_owner_active_org',request(owner,'GET','/api/user')['orgId']==org)
        owner.headers.pop('Authorization');response=owner.request('POST','/login',json_data={'user':'mo-owner','password':credentials['owner_password']})
        check('native_password_session_cookie',response.status_code==200 and request(owner,'GET','/api/user')['id']==user_ids['owner'])
        response=anonymous.request('POST','/login',json_data={'user':'mo-owner','password':'incorrect-'+uuid.uuid4().hex})
        check('wrong_password_login_denied',response.status_code==401)
        response=owner.request('POST','/api/admin/users',json_data={'login':'invalid-admin-create','password':'unused-fixture'})
        check('ordinary_user_server_admin_denied',response.status_code==403 and sql("SELECT COUNT(*) FROM user WHERE login='invalid-admin-create'")==((0,),))
        uid='mo-reg-'+uuid.uuid4().hex[:12];title='原生仪表板 中文 😀𠮷';content='MatrixOne text 中文 😀𠮷'
        panels=[{'id':1,'type':'text','title':'原生面板','gridPos':{'h':4,'w':12,'x':0,'y':0},'options':{'mode':'markdown','content':content,'fixture':{'nullable':None,'flag':False,'decimal':'2345.67','bigint':'9223372036854775806','binary_base64':'AP9BAA=='}}}]
        dashboard={'uid':uid,'title':title,'schemaVersion':41,'tags':['matrixone','中文'],'panels':panels,'version':0}
        stage='native_dashboard'
        result=request(owner,'POST','/api/dashboards/db',{'dashboard':dashboard,'overwrite':False})
        check('native_dashboard_create',result['status']=='success' and result['uid']==uid)
        def stored():
            rows=sql("SELECT namespace,value FROM resource WHERE `group`='dashboard.grafana.app' AND resource='dashboards' AND name=%s",(uid,))
            if len(rows)!=1:raise AssertionError('single_authoritative_dashboard_row')
            return rows[0][0],json.loads(rows[0][1])
        namespace,value=stored();report['native_dashboard_namespace']=namespace
        check('SQL_unified_resource_values_exact',value['spec']['title']==title and value['spec']['panels']==panels
              and namespace==('default' if org==1 else 'org-'+str(org)) and value['metadata']['namespace']==namespace
              and sql('SELECT org_id FROM user WHERE id=%s',(user_ids['owner'],))==((org,),))
        response=anonymous.request('GET','/api/dashboards/uid/'+uid);check('anonymous_dashboard_denied',response.status_code==401)
        response=other.request('GET','/api/dashboards/uid/'+uid);check('other_org_dashboard_read_denied',response.status_code==404)
        before=stored();response=other.request('DELETE','/api/dashboards/uid/'+uid)
        check('other_org_dashboard_delete_denied_no_change',response.status_code==404 and stored()==before)
        body={'dashboard':{**dashboard,'title':'invalid-CSRF-title'},'overwrite':True}
        response=owner.request('POST','/api/dashboards/db',json_data=body,headers={'Origin':'https://example.test'})
        check('native_invalid_origin_CSRF_denied_no_change',response.status_code==403 and stored()==before)
        actual=request(owner,'GET','/api/dashboards/uid/'+uid)['dashboard'];actual['panels'][0]['options']['content']='更新面板 中文 😀𠮷'
        result=request(owner,'POST','/api/dashboards/db',{'dashboard':actual,'overwrite':True})
        check('native_dashboard_update_version',result['status']=='success' and int(result['version'])>1);panels=actual['panels']
        def readback(label):
            dashboard=request(owner,'GET','/api/dashboards/uid/'+uid)['dashboard']
            check(label+'_native_panel_JSON_exact',dashboard['title']==title and dashboard['panels']==panels)
            namespace,value=stored();check(label+'_SQL_panel_JSON_and_org_exact',value['spec']['panels']==panels and namespace==report['native_dashboard_namespace'])
        readback('before_restart');stage='native_restart';before=stored();old_pid=proc.pid;owned.stop(proc);proc,health=start();check('real_Grafana_process_restart',old_pid!=proc.pid)
        readback('after_restart');check('after_restart_SQL_original_resource_unchanged',stored()==before)
        response=other.request('GET','/api/dashboards/uid/'+uid);check('after_restart_other_org_denied',response.status_code==404)
        request(owner,'DELETE','/api/dashboards/uid/'+uid)
        check('native_delete_HTTP_and_SQL_zero_live_row',owner.request('GET','/api/dashboards/uid/'+uid).status_code==404 and sql("SELECT COUNT(*) FROM resource WHERE name=%s AND resource='dashboards'",(uid,))==((0,),))
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),));report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    return finish(out,report,'grafana-native')


if __name__=='__main__':raise SystemExit(main())
