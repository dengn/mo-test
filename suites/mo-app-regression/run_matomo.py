"""Pinned Matomo original web installer, native tokens, visitor/action joins and restart."""
import argparse
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
from native_common import Client, Processes, connection_config, digest, finish, port, private_file, runtime_root
from native_release import tar_release

ROOT=Path(__file__).resolve().parent
PHP_SHA='9f738981bbcce1906329b751e57411171d5db0629ee00da0a41514f4a3d2f280'
URL='https://github.com/matomo-org/matomo/releases/download/5.14.1/matomo-5.14.1.tar.gz'
ARCHIVE_SHA='6e2938c9a482fa715a02cacacc490f2e7d6fb1f4068e45de41181089c129080e'


def main():
    import pymysql
    from bs4 import BeautifulSoup
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,default=os.getenv('MO_PHP_BINARY') or None)
    parser.add_argument('--release-archive',type=Path,default=os.getenv('MO_MATOMO_RELEASE_ARCHIVE') or None)
    parser.add_argument('--min-free-mib',type=int,default=2048)
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts'/('matomo-'+uuid.uuid4().hex[:12]))
    args=parser.parse_args()
    if args.min_free_mib<128:parser.error('Minimum disk admission floor is 128 MiB')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    schema='mo_reg_matomo_'+uuid.uuid4().hex[:16];private=runtime_root()/schema;private.mkdir(parents=True,mode=0o700)
    report={'app':'matomo-org/matomo','version':'5.14.1','commit':'edb949cf54455cb8cbbd7f8c5a36fda8d32f532a','schema':schema,
            'passed':False,'checks':[],'native_runtime_attempted':False,'official_archive_sha256':ARCHIVE_SHA,'existing_databases_modified':False,
            'manual_users_or_migration_stamps':False,'min_free_mib':args.min_free_mib,
            'source_edits':['explicit server-version alias','native Unicode charset and metadata case','split actual column/index DDL','match exact missing-table diagnostic',
                            'transactional native sequence allocation','bounded explicit-order ROW_NUMBER ranking'],
            'limitations':['archived reports/ranking rollup/plugins/import/populated upgrades/wider collation unverified']}
    owned=Processes(private,report);stage='admission'
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free<args.min_free_mib*1024**2+100*1024**2:raise RuntimeError('Pinned PHP SDK and fresh release headroom required')
        php=args.binary.resolve();check('pinned_FrankenPHP',digest(php)==PHP_SHA)
        app,count=tar_release(args.release_archive,private,URL,ARCHIVE_SHA,'matomo/',11887,ROOT/'fixtures/matomo',max_archive_bytes=32*1024**2,
                              excluded_package_entries=('How to install Matomo.html',))
        report['verified_release_files']=count;check('fresh_official_release_without_old_config',not(app/'config/config.ini.php').exists())
        cfg=connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()');report['server_version'],report['runtime_git_version']=q.fetchone()
                check('actual_matrixone','MatrixOne' in report['server_version']);q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database']=schema
        def sql(query,params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query,params);return q.fetchall()
        credentials={k:secrets.token_urlsafe(32) for k in ['admin_password','owner_password','other_password']}
        if os.getenv('MO_MATOMO_ADMIN_PASSWORD'):credentials['admin_password']=os.environ['MO_MATOMO_ADMIN_PASSWORD']
        private_file(private/'credentials.json',json.dumps(credentials))
        web_port=port();base='http://127.0.0.1:'+str(web_port);installer=Session(base);admin=Session(base);owner=Session(base);other=Session(base);anonymous=Session(base)
        ini=private/'php-ini';ini.mkdir(mode=0o700);sessions=private/'sessions';sessions.mkdir(mode=0o700)
        private_file(ini/'local.ini','session.save_path='+json.dumps(str(sessions))+'\n')
        caddy=private/'Caddyfile';private_file(caddy,'{\n admin off\n auto_https off\n frankenphp {\n  num_threads 4\n }\n}\n'+base+' {\n root * '+str(app)+'\n @blocked path /config/* /core/* /vendor/* /tmp/* /tests/*\n respond @blocked 403\n php_server\n}\n')
        env={**os.environ,'MATRIXONE_ADAPTER':'1','PHP_INI_SCAN_DIR':str(ini),'GOMAXPROCS':'2','GOMEMLIMIT':'512MiB','XDG_CONFIG_HOME':str(private/'config'),'XDG_DATA_HOME':str(private/'data')}
        def start():
            proc=owned.start([str(php),'run','--config',str(caddy)],app,env,'matomo');report['native_runtime_attempted']=True;deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('Native Matomo startup failed; private log retained')
                try:
                    if anonymous.request('GET','/',timeout=3).status_code==200:return proc
                except(OSError,urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native Matomo readiness')
        proc=start();stage='native_web_installation'
        def soup(response):return BeautifulSoup(response.text,'html.parser')
        def step(action,values=None):
            params={'module':'Installation','action':action}
            if action=='trackingCode':params.update(site_idSite=1,site_name='MatrixOne analytics 中文 😀𠮷')
            path='/index.php?'+urllib.parse.urlencode(params);response=installer.request('GET',path,timeout=120)
            if values is not None:
                page=soup(response);data={n['name']:n.get('value','') for n in page.select('input[type=hidden][name]')};data.update(values)
                if action=='databaseSetup':data['adapter']=next(n['value'] for n in page.select('select[name=adapter] option') if 'PDO' in n.get_text())
                response=installer.request('POST',path,data=data,timeout=120)
            if response.status_code!=200:
                private_file(private/('failed-install-'+action+'.html'),response.content);raise AssertionError('native_install_'+action)
            private_file(private/('install-'+action+'.html'),response.content)
            final=urllib.parse.parse_qs(urllib.parse.urlsplit(response.path).query)
            report.setdefault('native_installer_steps',[]).append({'step':action,'http_status':response.status_code,
                'final_module':final.get('module',[''])[0],'final_action':final.get('action',[''])[0]})
            return response
        step('welcome');step('systemCheck')
        step('databaseSetup',{'host':cfg['host']+':'+str(cfg['port']),'username':cfg['user'],'password':cfg['password'],'dbname':schema,'tables_prefix':'matomo_','schema':'Mysql','submit':'Next'})
        step('tablesCreation');tables={r[0] for r in sql('SHOW TABLES')}
        check('native_core_tables_created',len(tables)>=28 and {'matomo_user','matomo_site','matomo_log_visit','matomo_log_action','matomo_log_link_visit_action'}<=tables)
        step('setupSuperUser',{'login':'mo-admin','password':credentials['admin_password'],'password_bis':credentials['admin_password'],'email':'admin@example.test','submit':'Next'})
        check('native_superuser_step_completed',report['native_installer_steps'][-1]['final_action']=='firstWebsiteSetup')
        step('firstWebsiteSetup',{'siteName':'MatrixOne analytics 中文 😀𠮷','url':'https://example.test','timezone':'UTC','ecommerce':'0','submit':'Next'})
        step('trackingCode');step('finished',{'anonymise_ip':'1','submit':'Continue to Matomo'})
        (app/'config/config.ini.php').chmod(0o600)
        check('native_plugins_finish_34_tables',len(sql('SHOW TABLES'))==34)
        check('native_superuser_bcrypt',sql("SELECT login,superuser_access,LENGTH(password) FROM matomo_user WHERE login='mo-admin'")==(('mo-admin',1,60),))
        check('native_website_Unicode_exact',sql('SELECT name,main_url,timezone FROM matomo_site WHERE idsite=1')==(('MatrixOne analytics 中文 😀𠮷','https://example.test','UTC'),))
        def api(method,params=None,token=None,client=None,denied=False,allow_error_200=False):
            data={'module':'API','method':method,'format':'JSON',**(params or {})}
            if token:data['token_auth']=token
            response=(client or Client(base)).request('POST','/index.php',data=data,timeout=90);result=response.json()
            is_error=isinstance(result,dict) and result.get('result')=='error'
            if denied:
                report.setdefault('native_denials',[]).append({'method':method,'http_status':response.status_code,'native_error':is_error})
                return is_error and response.status_code in ({200,400,401,403} if allow_error_200 else {400,401,403})
            if response.status_code!=200 or is_error:
                private_file(private/('failed-API-'+str(len(report['checks']))+'.json'),response.content);raise AssertionError('native_API_'+method)
            return result['value'] if isinstance(result,dict) and set(result)=={'value'} else result
        stage='native_accounts'
        token=api('UsersManager.createAppSpecificTokenAuth',{'userLogin':'mo-admin','passwordConfirmation':credentials['admin_password'],'description':'Owned regression admin token','expireHours':1})
        if not isinstance(token,str) or len(token)<32:raise AssertionError('native_admin_token_shape')
        credentials['admin_token']=token
        for label in ['owner','other']:
            api('UsersManager.addUser',{'userLogin':'mo-'+label,'password':credentials[label+'_password'],'email':label+'@example.test'},token=token)
            user_token=api('UsersManager.createAppSpecificTokenAuth',{'userLogin':'mo-'+label,'passwordConfirmation':credentials[label+'_password'],'description':'Owned regression '+label,'expireHours':1})
            credentials[label+'_token']=user_token
            check('native_user_'+label,sql('SELECT login,superuser_access,LENGTH(password) FROM matomo_user WHERE login=%s',('mo-'+label,))==(('mo-'+label,0,60),))
        (private/'credentials.json').write_text(json.dumps(credentials))
        api('UsersManager.setUserAccess',{'userLogin':'mo-owner','access':'view','idSites':'1'},token=token)
        check('native_site_view_permission',sql("SELECT login,access,idsite FROM matomo_access WHERE login='mo-owner'")==(('mo-owner','view',1),))
        token_count=sql('SELECT COUNT(*) FROM matomo_user_token_auth')
        check('wrong_password_native_token_denied',api('UsersManager.createAppSpecificTokenAuth',{'userLogin':'mo-owner','passwordConfirmation':'incorrect-'+uuid.uuid4().hex,'description':'invalid'},denied=True,allow_error_200=True)
              and sql('SELECT COUNT(*) FROM matomo_user_token_auth')==token_count)
        report_params={'idSite':1,'period':'day','date':'today','filter_limit':100}
        check('anonymous_live_report_denied',api('Live.getLastVisitsDetails',report_params,denied=True))
        check('other_user_live_report_denied',api('Live.getLastVisitsDetails',report_params,token=credentials['other_token'],denied=True))
        response=admin.request('GET','/index.php?module=Login');page=soup(response);field=page.select_one('input[name=form_login]');form=field.find_parent('form')
        data={n['name']:n.get('value','') for n in form.select('input[type=hidden][name]')};check('native_login_nonce_retained',bool(data.get('form_nonce')))
        data.update(form_login='mo-admin',form_password=credentials['admin_password']);response=admin.request('POST','/index.php?module=Login',data=data)
        check('native_UI_password_cookie_login',response.status_code==200 and soup(response).select_one('input[name=form_login]') is None)
        stage='native_tracking';expected={}
        for i in range(3):
            visitor=secrets.token_hex(8);action='访问动作 中文 😀𠮷 '+str(i);url='https://example.test/owned/'+visitor
            # Default tracking matches IP/browser/language. Distinct browser languages keep these visitors independent.
            response=Client(base).request('GET','/matomo.php?'+urllib.parse.urlencode({'idsite':1,'rec':1,'url':url,'action_name':action,'_id':visitor,
                'lang':['en-us','zh-cn','fr-fr'][i],'new_visit':1,'apiv':1,'rand':uuid.uuid4().hex}),headers={'User-Agent':'Mozilla/5.0 MORegression/1'},timeout=90)
            check('native_tracker_ack_'+str(i),response.status_code==200)
            rows=sql('SELECT v.idvisit,HEX(v.idvisitor),v.idsite,v.visit_total_actions,a.name,u.name,u.url_prefix FROM matomo_log_visit v JOIN matomo_log_link_visit_action l ON l.idvisit=v.idvisit JOIN matomo_log_action a ON a.idaction=l.idaction_name JOIN matomo_log_action u ON u.idaction=l.idaction_url WHERE a.name=%s',(action,))
            check('native_visitor_action_SQL_exact_'+str(i),len(rows)==1 and rows[0][1].lower()==visitor and rows[0][2:]==(1,1,action,url[len('https://'):],2))
            expected[rows[0][0]]=(visitor,action,url)
        def readback(label):
            rows=api('Live.getLastVisitsDetails',report_params,token=credentials['owner_token']);actual={int(r['idVisit']):r for r in rows}
            check(label+'_native_live_visitors_exact',set(actual)==set(expected) and all(actual[k]['visitorId']==v[0] and any(a.get('pageTitle')==v[1] and a.get('url')==v[2] for a in actual[k]['actionDetails']) for k,v in expected.items()))
            check(label+'_SQL_action_identity_and_relation',len(sql('SELECT * FROM matomo_log_visit'))==3 and len(sql('SELECT * FROM matomo_log_link_visit_action'))==3)
        readback('before_restart');stage='native_restart';before=sql('SELECT idvisit,HEX(idvisitor),visit_total_actions FROM matomo_log_visit ORDER BY idvisit');old_pid=proc.pid;owned.stop(proc);proc=start();check('real_PHP_process_restart',old_pid!=proc.pid)
        readback('after_restart');check('after_restart_SQL_original_values',before==sql('SELECT idvisit,HEX(idvisitor),visit_total_actions FROM matomo_log_visit ORDER BY idvisit'))
        check('after_restart_other_user_denied',api('Live.getLastVisitsDetails',report_params,token=credentials['other_token'],denied=True))
        response=admin.request('GET','/index.php?module=CoreHome&action=index&idSite=1&period=day&date=today')
        check('after_restart_original_cookie_UI',response.status_code==200 and soup(response).select_one('input[name=form_login]') is None)
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),));report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    return finish(out,report,'matomo-native')


if __name__=='__main__':raise SystemExit(main())
