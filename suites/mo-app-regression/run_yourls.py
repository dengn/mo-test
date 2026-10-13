"""Pinned YOURLS native installer, API/cookie auth, redirects/clicks/nonce and restart."""
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
from native_release import php_literal, tar_release

ROOT = Path(__file__).resolve().parent
PHP_SHA = '9f738981bbcce1906329b751e57411171d5db0629ee00da0a41514f4a3d2f280'
URL = 'https://codeload.github.com/YOURLS/YOURLS/tar.gz/refs/tags/1.10.6'
ARCHIVE_SHA = '95549b8463c67a88eaa93f5dd8079599bc895f5ca047001ce385d1afdda26563'


def main():
    import pymysql
    from bs4 import BeautifulSoup
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,default=os.getenv('MO_PHP_BINARY') or None)
    parser.add_argument('--release-archive',type=Path,default=os.getenv('MO_YOURLS_RELEASE_ARCHIVE') or None)
    parser.add_argument('--min-free-mib',type=int,default=2048)
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts'/('yourls-'+uuid.uuid4().hex[:12]))
    args=parser.parse_args()
    if args.min_free_mib<128:parser.error('Minimum disk admission floor is 128 MiB')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    schema='mo_reg_yourls_'+uuid.uuid4().hex[:16];private=runtime_root()/schema;private.mkdir(parents=True,mode=0o700)
    report={'app':'YOURLS/YOURLS','version':'1.10.6','commit':'8220c8dd191e5f212bf5d77048e62975b2e2de4d','schema':schema,
            'passed':False,'checks':[],'native_runtime_attempted':False,'official_archive_sha256':ARCHIVE_SHA,
            'existing_databases_modified':False,'manual_migration_stamps':False,'native_config_users_retained':True,
            'source_edits':['MatrixOne click log VARCHAR BINARY becomes VARBINARY only'], 'min_free_mib':args.min_free_mib,
            'limitations':['plugins/import/export/populated upgrades/global manager accounts and wider collation unverified']}
    owned=Processes(private,report);stage='admission'
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free<args.min_free_mib*1024**2+50*1024**2:raise RuntimeError('Pinned PHP SDK and fresh release headroom required')
        php=args.binary.resolve();check('pinned_FrankenPHP',digest(php)==PHP_SHA)
        app,count=tar_release(args.release_archive,private,URL,ARCHIVE_SHA,'YOURLS-1.10.6/',639,ROOT/'fixtures/yourls')
        report['verified_release_files']=count;check('fresh_official_release_without_old_config',not(app/'user/config.php').exists())
        cfg=connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()');report['server_version'],report['runtime_git_version']=q.fetchone()
                check('actual_matrixone','MatrixOne' in report['server_version']);q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database']=schema
        def sql(query,params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query,params);return q.fetchall()
        credentials={'owner_password':secrets.token_urlsafe(24),'cookie_key':secrets.token_hex(32)}
        private_file(private/'credentials.json',json.dumps(credentials));username='mo-owner';password=credentials['owner_password']
        web_port=port();base='http://127.0.0.1:'+str(web_port);owner=Session(base);anonymous=Session(base);wrong=Session(base);redirect=Client(base)
        host=cfg['host'];host='['+host+']' if ':' in host else host
        settings={'YOURLS_DB_USER':cfg['user'],'YOURLS_DB_PASS':cfg['password'],'YOURLS_DB_NAME':schema,'YOURLS_DB_HOST':host+':'+str(cfg['port']),
                  'YOURLS_DB_PREFIX':'yourls_','YOURLS_SITE':base,'YOURLS_COOKIEKEY':credentials['cookie_key'],'YOURLS_PRIVATE':True,'YOURLS_UNIQUE_URLS':True}
        config='<?php\n'+''.join('define('+php_literal(k)+','+php_literal(v)+');\n' for k,v in settings.items())
        config+='$yourls_user_passwords = ['+php_literal(username)+'=>'+php_literal(password)+'];\n'
        private_file(app/'user/config.php',config)
        caddy=private/'Caddyfile';private_file(caddy,'{\n admin off\n auto_https off\n frankenphp {\n  num_threads 4\n }\n}\n'+base+' {\n root * '+str(app)+'\n @blocked path /user/* /includes/* /tests/*\n respond @blocked 403\n try_files {path} {path}/ /yourls-loader.php\n php_server\n}\n')
        env={**os.environ,'MATRIXONE_ADAPTER':'1','GOMAXPROCS':'2','GOMEMLIMIT':'512MiB','XDG_CONFIG_HOME':str(private/'config'),'XDG_DATA_HOME':str(private/'data')}
        def start():
            proc=owned.start([str(php),'run','--config',str(caddy)],app,env,'yourls');report['native_runtime_attempted']=True;deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('Native YOURLS startup failed; private log retained')
                try:
                    if anonymous.request('GET','/admin/install.php',timeout=3).status_code==200:return proc
                except(OSError,urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native YOURLS startup')
        stage='native_installation';proc=start();response=anonymous.request('POST','/admin/install.php',data={'install':'Install YOURLS'},timeout=60)
        page=BeautifulSoup(response.text,'html.parser')
        check('native_web_installer_three_tables',response.status_code==200 and not page.select('ul.error') and {r[0] for r in sql('SHOW TABLES')}=={'yourls_url','yourls_options','yourls_log'})
        check('native_installer_schema_507',sql("SELECT option_value FROM yourls_options WHERE option_name='db_version'")==(('507',),))
        def api(action,params=None,client=None,auth=True,wrong_password=False,denied=False,expected_status='200'):
            data={'format':'json','action':action,**(params or {})}
            if auth:data.update(username=username,password='incorrect-'+uuid.uuid4().hex if wrong_password else password)
            response=(client or owner).request('POST','/yourls-api.php',data=data,timeout=90)
            if denied:return response.status_code in {401,403}
            result=response.json()
            if response.status_code not in {200,int(expected_status)} or str(result.get('statusCode'))!=expected_status:raise AssertionError('native_API_'+action)
            return result
        stage='native_authentication'
        check('anonymous_management_API_denied',api('expand',{'shorturl':'missing'},client=anonymous,auth=False,denied=True))
        check('wrong_password_API_denied',api('expand',{'shorturl':'missing'},client=wrong,wrong_password=True,denied=True))
        def soup(response):return BeautifulSoup(response.text,'html.parser')
        response=owner.request('GET','/admin/');field=soup(response).select_one('input[name=username]');form=field.find_parent('form')
        data={n['name']:n.get('value','') for n in form.select('input[type=hidden][name]')}
        check('native_login_nonce_retained',bool(data.get('nonce')))
        data.update(username=username,password=password);response=owner.request('POST','/admin/',data=data)
        check('native_UI_cookie_password_login',response.status_code==200 and soup(response).select_one('input[name=username]') is None)
        check('private_config_not_served',anonymous.request('GET','/user/config.php').status_code==403)
        stage='native_links';keyword='mo'+uuid.uuid4().hex[:10];long_url='https://example.test/fixture/'+keyword;title='短链标题 中文 😀𠮷'
        result=api('shorturl',{'url':long_url,'keyword':keyword,'title':title})
        check('native_short_link_created',result['url']['keyword']==keyword)
        check('native_link_UTF8_URL_exact',sql('SELECT keyword,url,title FROM yourls_url WHERE keyword=%s',(keyword,))==((keyword,long_url,title),))
        before=sql('SELECT COUNT(*) FROM yourls_url WHERE keyword=%s',(keyword,));result=api('shorturl',{'url':long_url,'keyword':keyword,'title':title},expected_status='409')
        check('native_duplicate_URL_rejected_no_extra_row',result.get('code')=='error:url' and result['url']['keyword']==keyword and sql('SELECT COUNT(*) FROM yourls_url WHERE keyword=%s',(keyword,))==before)
        response=redirect.request('GET','/'+keyword,headers={'User-Agent':'MO regression UTF8 fixture','Referer':'https://example.test/owned-referrer'})
        check('native_public_redirect_exact_no_external_fetch',response.status_code in {301,302} and response.headers.get('Location')==long_url)
        check('native_click_count_exact',sql('SELECT clicks FROM yourls_url WHERE keyword=%s',(keyword,))==((1,),))
        check('native_binary_keyword_click_log_relation',sql('SELECT l.shorturl,l.referrer,l.user_agent,u.keyword FROM yourls_log l JOIN yourls_url u ON CAST(l.shorturl AS CHAR)=u.keyword WHERE u.keyword=%s',(keyword,))==((keyword.encode(),'https://example.test/owned-referrer','MO regression UTF8 fixture',keyword),))
        response=owner.request('GET','/admin/');page=soup(response)
        def link_params(page,kind):
            for a in page.select('a[id^="'+kind+'-button-"]'):
                values={k:v[0] for k,v in urllib.parse.parse_qs(urllib.parse.urlsplit(a['href']).query).items()}
                if values.get('keyword')==keyword:return values
            raise AssertionError('native_'+kind+'_nonce_link')
        edit=link_params(page,'edit');edit['action']='edit_display'
        response=owner.request('POST','/admin/admin-ajax.php',data=edit);form=BeautifulSoup(response.json()['html'],'html.parser')
        nonce=form.select_one('input[id="nonce_'+edit['id']+'"]')['value'];updated='更新短链 中文 😀𠮷';new_url=long_url+'/edited'
        response=owner.request('POST','/admin/admin-ajax.php',data={'action':'edit_save','id':edit['id'],'nonce':nonce,'keyword':keyword,'newkeyword':keyword,'url':new_url,'title':updated})
        result=response.json();check('native_edit_nonce_and_values',result.get('status')=='success' and sql('SELECT url,title FROM yourls_url WHERE keyword=%s',(keyword,))==((new_url,updated),))
        response=owner.request('POST','/admin/admin-ajax.php',data={'action':'add','nonce':'invalid-token','keyword':'invalidcsrf','url':'https://example.test/invalid','rowid':'invalid'})
        check('invalid_nonce_native_rejection_zero_write',response.status_code in {200,403} and 'omg error' in response.text and sql("SELECT COUNT(*) FROM yourls_url WHERE keyword='invalidcsrf'")==((0,),))
        def readback(label):
            result=api('expand',{'shorturl':keyword});check(label+'_native_URL_title_exact',result['longurl']==new_url and result['title']==updated)
            result=api('url-stats',{'shorturl':keyword});check(label+'_native_stats_clicks_exact',int(result['link']['clicks'])==1)
            response=owner.request('GET','/admin/');page=soup(response)
            check(label+'_original_cookie_UI_values',response.status_code==200 and page.select_one('input[name=username]') is None and updated in page.get_text())
        readback('before_restart');stage='native_restart';before=sql('SELECT keyword,url,title,clicks FROM yourls_url WHERE keyword=%s',(keyword,));old_pid=proc.pid;owned.stop(proc);proc=start()
        check('real_PHP_process_restart',proc.pid!=old_pid);readback('after_restart')
        check('after_restart_SQL_values_and_schema',before==sql('SELECT keyword,url,title,clicks FROM yourls_url WHERE keyword=%s',(keyword,)) and sql("SELECT option_value FROM yourls_options WHERE option_name='db_version'")==(('507',),))
        page=soup(owner.request('GET','/admin/'));delete=link_params(page,'delete');response=owner.request('POST','/admin/admin-ajax.php',data=delete)
        check('native_nonce_delete_exact',response.json().get('success')==1 and sql('SELECT COUNT(*) FROM yourls_url WHERE keyword=%s',(keyword,))==((0,),))
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),));report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    return finish(out,report,'yourls-native')


if __name__=='__main__':raise SystemExit(main())
