"""Pinned Kanboard native 139 migrations, private boards/tasks/comments and restart."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import shutil
import time
import urllib.error
import urllib.parse
import uuid

from run_baikal import Session
from native_common import Processes, connection_config, digest, finish, port, private_file, runtime_root
from native_release import php_literal, tar_release

ROOT = Path(__file__).resolve().parent
PHP_SHA = '9f738981bbcce1906329b751e57411171d5db0629ee00da0a41514f4a3d2f280'
URL = 'https://codeload.github.com/kanboard/kanboard/tar.gz/refs/tags/v1.2.54'
ARCHIVE_SHA = '6548946b406bc8640dfe20a884dd9cdf708d8d6c25eeacdabd374a36d5e98237'


def main():
    import pymysql
    from bs4 import BeautifulSoup
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,default=os.getenv('MO_PHP_BINARY') or None)
    parser.add_argument('--release-archive',type=Path,default=os.getenv('MO_KANBOARD_RELEASE_ARCHIVE') or None)
    parser.add_argument('--min-free-mib',type=int,default=2048)
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts'/('kanboard-'+uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:parser.error('Minimum disk admission floor is 128 MiB')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    schema='mo_reg_kanboard_'+uuid.uuid4().hex[:16];private=runtime_root()/schema;private.mkdir(parents=True,mode=0o700)
    report={'app':'kanboard/kanboard','version':'v1.2.54','commit':'9ce6a5edc5b646ef15780cb445bc6d2c39d9898f',
            'schema':schema,'passed':False,'checks':[],'native_runtime_attempted':False,'official_archive_sha256':ARCHIVE_SHA,
            'existing_databases_modified':False,'manual_users_or_migration_stamps':False,'min_free_mib':args.min_free_mib,
            'source_edits':['reserved identifiers outside SQL literals/comments','resolve native renamed FK/index','real DDL commits at MySQL migration boundaries','PHP8.5 PDO constant'],
            'limitations':['populated upgrades/attachments/automation/plugins/LDAP/full project roles unverified']}
    owned=Processes(private,report);stage='admission'
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free < args.min_free_mib*1024**2+50*1024**2:raise RuntimeError('Pinned PHP SDK and fresh release headroom required')
        php=args.binary.resolve();check('pinned_FrankenPHP',digest(php)==PHP_SHA)
        app,count=tar_release(args.release_archive,private,URL,ARCHIVE_SHA,'kanboard-1.2.54/',2101,ROOT/'fixtures/kanboard')
        report['verified_release_files']=count;check('fresh_official_release_without_old_config',not(app/'config.php').exists())
        cfg=connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()');report['server_version'],report['runtime_git_version']=q.fetchone()
                check('actual_matrixone','MatrixOne' in report['server_version']);q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database']=schema
        def sql(query,params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query,params);return q.fetchall()
        settings={'DB_DRIVER':'mysql','DB_HOSTNAME':cfg['host'],'DB_PORT':cfg['port'],'DB_NAME':schema,'DB_USERNAME':cfg['user'],'DB_PASSWORD':cfg['password'],'LOG_DRIVER':'file'}
        private_file(app/'config.php','<?php\n'+''.join('define('+php_literal(k)+','+php_literal(v)+');\n' for k,v in settings.items()))
        credentials={k:secrets.token_urlsafe(24) for k in ['bootstrap_password','owner_password','other_password']}
        private_file(private/'credentials.json',json.dumps(credentials))
        web_port=port();base='http://127.0.0.1:'+str(web_port);owner=Session(base);anonymous=Session(base);other=Session(base)
        ini=private/'php-ini';ini.mkdir(mode=0o700);sessions=private/'sessions';sessions.mkdir(mode=0o700)
        private_file(ini/'local.ini','session.save_path='+json.dumps(str(sessions))+'\n')
        caddy=private/'Caddyfile'
        private_file(caddy,'{\n admin off\n auto_https off\n frankenphp {\n  num_threads 4\n }\n}\n'+base+' {\n root * '+str(app)+'\n @blocked path /config.php /data/* /libs/* /app/* /tests/* /plugins/*\n respond @blocked 403\n php_server\n}\n')
        env={**os.environ,'MATRIXONE_ADAPTER':'1','PHP_INI_SCAN_DIR':str(ini),'GOMAXPROCS':'2','GOMEMLIMIT':'512MiB','XDG_CONFIG_HOME':str(private/'config'),'XDG_DATA_HOME':str(private/'data')}
        def start():
            proc=owned.start([str(php),'run','--config',str(caddy)],app,env,'kanboard');report['native_runtime_attempted']=True;deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('Native Kanboard startup failed; private log retained')
                try:
                    if anonymous.request('GET','/',timeout=45).status_code==200:return proc
                except(OSError,urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native Kanboard startup')
        stage='native_migrations';proc=start()
        check('native_139_migrations',sql('SELECT version FROM schema_version')==((139,),))
        check('native_default_admin_hash',sql("SELECT username,LENGTH(password) FROM users")==(('admin',60),))
        def rpc(method,params=None,auth=None,client=None,denied=False):
            client=client or owner;headers={}
            if auth is not None:headers['Authorization']='Basic '+base64.b64encode((auth[0]+':'+auth[1]).encode()).decode()
            response=client.request('POST','/jsonrpc.php',json_data={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}},headers=headers,timeout=90)
            data=response.json()
            if denied:return response.status_code in {401,403} or 'error' in data
            if response.status_code!=200 or 'error' in data:raise AssertionError('native_RPC_'+method)
            return data['result']
        stage='native_users'
        bootstrap=('mo-bootstrap',credentials['bootstrap_password']);own_auth=('mo-owner',credentials['owner_password']);other_auth=('mo-other',credentials['other_password'])
        bootstrap_id=rpc('createUser',{'username':bootstrap[0],'password':bootstrap[1],'role':'app-admin'},auth=('admin','admin'))
        check('native_bootstrap_admin_created',isinstance(bootstrap_id,int) and bootstrap_id>1)
        check('native_initial_default_admin_removed',rpc('removeUser',{'user_id':1},auth=bootstrap) is True and sql("SELECT COUNT(*) FROM users WHERE username='admin'")==((0,),))
        owner_id=rpc('createUser',{'username':own_auth[0],'password':own_auth[1],'name':'所有者 中文 😀𠮷','role':'app-user'},auth=bootstrap)
        other_id=rpc('createUser',{'username':other_auth[0],'password':other_auth[1],'name':'隔离用户 中文 😀𠮷','role':'app-user'},auth=bootstrap)
        check('native_two_ordinary_users',owner_id!=other_id and sql('SELECT COUNT(*) FROM users WHERE role=%s AND LENGTH(password)=60',('app-user',))==((2,),))
        check('native_owner_password_RPC',int(rpc('getMe',auth=own_auth)['id'])==owner_id)
        check('wrong_password_RPC_denied',rpc('getMe',auth=(own_auth[0],'incorrect-'+uuid.uuid4().hex),denied=True))
        def soup(response):return BeautifulSoup(response.text,'html.parser')
        def hidden(form):return {n['name']:n.get('value','') for n in form.select('input[type=hidden][name]')}
        response=owner.request('GET','/');field=soup(response).select_one('input[name=username]');form=field.find_parent('form');data=hidden(form)
        check('native_login_CSRF_retained',bool(data.get('csrf_token')))
        data.update(username=own_auth[0],password=own_auth[1]);response=owner.request('POST','/'+form['action'].lstrip('/'),data=data)
        check('native_UI_cookie_password_login',response.status_code==200 and soup(response).select_one('input[name=username]') is None)
        project_name='私有看板 中文 😀𠮷';project=rpc('createMyPrivateProject',{'name':project_name,'description':'原生项目'},auth=own_auth)
        check('native_private_project_owner',sql('SELECT name,is_private,owner_id FROM projects WHERE id=%s',(project,))==((project_name,1,owner_id),))
        check('other_user_project_denied',rpc('getProjectById',{'project_id':project},auth=other_auth,client=other,denied=True))
        stage='native_tasks'
        expected={}
        def create(i):
            title='原生任务 中文 😀𠮷 '+str(i);client=Session(base)
            identity=rpc('createTask',{'title':title,'description':title,'project_id':project,'owner_id':owner_id,'creator_id':owner_id},auth=own_auth,client=client)
            if not isinstance(identity,int) or identity<=0:raise AssertionError('native_task_created')
            return identity,title
        with ThreadPoolExecutor(max_workers=2) as pool:expected=dict(pool.map(create,range(8)))
        check('native_eight_concurrent_tasks_exact',dict(sql('SELECT id,title FROM tasks'))==expected and all(r[0]==r[1] and r[2]==project and r[3]==owner_id and r[4]==owner_id for r in sql('SELECT title,description,project_id,owner_id,creator_id FROM tasks')))
        task=next(iter(expected));title='更新任务 中文 😀𠮷'
        check('native_task_update',rpc('updateTask',{'id':task,'title':title,'description':title},auth=own_auth) is True);expected[task]=title
        comment_text='关联评论 中文 😀𠮷';comment=rpc('createComment',{'task_id':task,'user_id':owner_id,'content':comment_text},auth=own_auth)
        check('native_comment_and_relation_exact',sql('SELECT c.comment,c.task_id,c.user_id,t.project_id FROM comments c JOIN tasks t ON c.task_id=t.id WHERE c.id=%s',(comment,))==((comment_text,task,owner_id,project),))
        check('other_user_task_read_denied',rpc('getTask',{'task_id':task},auth=other_auth,client=other,denied=True))
        check('other_user_task_update_denied',rpc('updateTask',{'id':task,'title':'invalid cross user'},auth=other_auth,client=other,denied=True) and sql('SELECT title FROM tasks WHERE id=%s',(task,))==((title,),))
        check('anonymous_task_RPC_denied',rpc('getTask',{'task_id':task},client=anonymous,denied=True))
        response=owner.request('GET','/?'+urllib.parse.urlencode({'controller':'TaskCreationController','action':'show','project_id':project}))
        form=soup(response).select_one('input[name=title]').find_parent('form');data=hidden(form);check('native_task_form_CSRF_retained',bool(data.get('csrf_token')))
        data.update(title='invalid-CSRF-task',csrf_token='deliberately-invalid-token');before=sql('SELECT COUNT(*) FROM tasks')
        response=owner.request('POST','/'+form['action'].lstrip('/'),data=data)
        report['invalid_CSRF_HTTP_status']=response.status_code
        check('invalid_CSRF_native_rejection_zero_write',response.status_code==200 and 'The title is required' in soup(response).get_text() and sql('SELECT COUNT(*) FROM tasks')==before)
        def readback(label):
            actual={int(t['id']):t['title'] for t in rpc('getAllTasks',{'project_id':project,'status_id':1},auth=own_auth)}
            check(label+'_native_tasks_exact',actual==expected)
            data=rpc('getComment',{'comment_id':comment},auth=own_auth)
            check(label+'_native_comment_exact',data['comment']==comment_text and int(data['task_id'])==task and int(data['user_id'])==owner_id)
            response=owner.request('GET','/?'+urllib.parse.urlencode({'controller':'TaskViewController','action':'show','task_id':task}))
            check(label+'_original_cookie_UI_task',response.status_code==200 and title in soup(response).get_text())
        readback('before_restart');stage='native_restart';old_pid=proc.pid;owned.stop(proc);proc=start();check('real_PHP_process_restart',proc.pid!=old_pid)
        readback('after_restart');check('after_restart_SQL_values_and_schema',dict(sql('SELECT id,title FROM tasks'))==expected and sql('SELECT version FROM schema_version')==((139,),))
        check('after_restart_other_user_denied',rpc('getTask',{'task_id':task},auth=other_auth,client=other,denied=True))
        check('native_task_delete',rpc('removeTask',{'task_id':task},auth=own_auth) is True and sql('SELECT COUNT(*) FROM tasks WHERE id=%s',(task,))==((0,),))
        check('native_comment_cascade_delete',sql('SELECT COUNT(*) FROM comments WHERE id=%s',(comment,))==((0,),))
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),));report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    return finish(out,report,'kanboard-native')


if __name__=='__main__':raise SystemExit(main())
