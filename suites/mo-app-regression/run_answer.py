"""Official Apache Answer native AUTO_INSTALL/users/questions/answers/tags and restart."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from native_common import Client, Processes, connection_config, digest, finish, port, private_file, runtime_root

ROOT = Path(__file__).resolve().parent
COMMIT = '6744295fa888e0621fc9f9a8ace04f1a4daf8554'
BINARY_SHA = 'c485f6f7190624681ad3a08c99aa0241f2dd630b04ed1c1d29bb4d8b47545824'


def native_binary(provided, private):
    release = json.loads((ROOT/'fixtures/answer/release.json').read_text())
    if provided:
        binary = provided.resolve()
    else:
        archive = private/'official.tar.gz'
        with urllib.request.urlopen(release['asset_url'],timeout=90) as response:
            private_file(archive,response.read(64*1024**2+1))
        if digest(archive)!=release['asset_sha256']:raise RuntimeError('Official Answer archive digest mismatch')
        with tarfile.open(archive) as tar:
            candidates=[m for m in tar if m.isfile() and m.name.endswith('/answer') and m.size==release['binary_bytes']]
            if len(candidates)!=1:raise RuntimeError('Official binary layout mismatch')
            with tar.extractfile(candidates[0]) as source:
                binary=private/'answer';private_file(binary,source.read(release['binary_bytes']+1));binary.chmod(0o700)
    if digest(binary)!=BINARY_SHA:raise RuntimeError('Pinned official Answer binary required')
    return binary,release


def main():
    import pymysql
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,default=os.getenv('MO_ANSWER_BINARY') or None)
    parser.add_argument('--min-free-mib',type=int,default=2048)
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts'/('answer-'+uuid.uuid4().hex[:12]))
    args=parser.parse_args()
    if args.min_free_mib<128:parser.error('Minimum disk admission floor is 128 MiB')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    schema='mo_reg_answer_'+uuid.uuid4().hex[:16];private=runtime_root()/schema;private.mkdir(parents=True,mode=0o700)
    report={'app':'apache/answer','version':'2.0.3','commit':COMMIT,'schema':schema,'passed':False,'checks':[],
            'native_runtime_attempted':False,'existing_databases_modified':False,'manual_users_or_migration_stamps':False,
            'source_edits':False,'native_SQLite_cache_retained':True,'min_free_mib':args.min_free_mib,
            'limitations':['fresh current-schema initializer, populated upgrades unverified','community suggested editing/SMTP/federation/AI/MCP/plugins/full UI unverified']}
    owned=Processes(private,report);stage='admission'
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        if shutil.disk_usage(runtime_root()).free<args.min_free_mib*1024**2+96*1024**2:raise RuntimeError('Native SDK and runtime disk reserve required')
        binary,release=native_binary(args.binary,private);report['binary_sha256']=BINARY_SHA;check('pinned_official_binary',True)
        cfg=connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()');report['server_version'],report['runtime_git_version']=q.fetchone()
                check('actual_matrixone','MatrixOne' in report['server_version']);q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database']=schema
        def sql(query,params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query,params);return q.fetchall()
        credentials={k:'Mo1-'+secrets.token_hex(12) for k in ['admin_password','owner_password','other_password']}
        private_file(private/'credentials.json',json.dumps(credentials));data=private/'data';data.mkdir(mode=0o700)
        web_port=port();base='http://127.0.0.1:'+str(web_port);host=cfg['host'];host='['+host+']' if ':' in host else host
        env={**os.environ,'AUTO_INSTALL':'true','DB_TYPE':'mysql','DB_USERNAME':cfg['user'],'DB_PASSWORD':cfg['password'],'DB_HOST':host+':'+str(cfg['port']),
             'DB_NAME':schema,'LANGUAGE':'en_US','SITE_NAME':'MO 问答 中文 😀','SITE_URL':base,'CONTACT_EMAIL':'contact@example.test',
             'ADMIN_NAME':'mo-admin','ADMIN_PASSWORD':credentials['admin_password'],'ADMIN_EMAIL':'admin@example.test',
             'EXTERNAL_CONTENT_DISPLAY':'ask_before_display','INSTALL_PORT':'0','GOMAXPROCS':'2','GOMEMLIMIT':'512MiB'}
        stage='native_installation'
        proc=owned.start([str(binary),'init','-C',str(data)],private,env,'answer-init');report['native_runtime_attempted']=True
        if proc.wait(timeout=120)!=0:raise RuntimeError('Native AUTO_INSTALL failed; private log retained')
        check('native_initializer_current_schema_version',sql('SELECT id,version_number FROM version')==((1,release['expected_native_DB_version']),))
        check('native_initializer_core_tables',{'user','question','answer','tag','tag_rel','user_role_rel','config','version'}<={r[0] for r in sql('SHOW TABLES')})
        check('native_initializer_admin_bcrypt_and_role',sql("SELECT u.status,LENGTH(u.pass),r.role_id FROM user u JOIN user_role_rel r ON r.user_id=u.id WHERE u.e_mail='admin@example.test'")==((1,60,2),))
        config=data/'conf/config.yaml'
        if not config.exists():raise RuntimeError('Native generated configuration missing')
        text=config.read_text();text,n=re.subn(r'(?m)^(\s+addr:\s*)(?:0\.0\.0\.0:80|[\"\x27]:80[\"\x27])\s*$',lambda m:m[1]+'127.0.0.1:'+str(web_port),text)
        if n!=1:raise RuntimeError('Expected native generated HTTP listener setting')
        config.write_text(text);config.chmod(0o600)
        run_env={**os.environ,'GOMAXPROCS':'2','GOMEMLIMIT':'512MiB'}
        admin,owner,other,anonymous=Client(base),Client(base),Client(base),Client(base)
        def start():
            proc=owned.start([str(binary),'run','-C',str(data)],private,run_env,'answer');deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('Native Answer startup failed; private log retained')
                try:
                    response=anonymous.request('GET','/answer/api/v1/language/options',timeout=3)
                    if response.status_code==200 and response.json().get('code')==200:return proc
                except(OSError,ValueError,urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native Answer readiness')
        proc=start()
        def api(client,method,path,body=None,query=None,denied=False):
            if query:path+='?'+urllib.parse.urlencode(query)
            response=client.request(method,path,json_data=body,timeout=90);result=response.json()
            if denied:
                report.setdefault('native_denials',[]).append({'path':path.split('?')[0],'http_status':response.status_code,'native_code':result.get('code')})
                return result.get('code')!=200 and response.status_code in {200,400,401,403}
            if response.status_code!=200 or result.get('code')!=200:
                report.update(failed_HTTP_status=response.status_code,failed_native_code=result.get('code'),failed_native_endpoint=path.split('?')[0])
                private_file(private/('failed-native-'+str(len(report['checks']))+'.json'),response.content);raise AssertionError('native_HTTP_'+method+'_'+path.split('?')[0])
            return result.get('data')
        def login(client,label):
            result=api(client,'POST','/answer/api/v1/user/login/email',{'e_mail':label+'@example.test','pass':credentials[label+'_password']})
            client.headers['Authorization']=result['access_token'];credentials[label+'_token']=result['access_token'];return result
        stage='native_users';admin_info=login(admin,'admin')
        check('native_admin_password_login',admin_info['role_id']==2 and admin_info['e_mail']=='admin@example.test')
        ids={}
        for label,client in [('owner',owner),('other',other)]:
            api(admin,'POST','/answer/admin/api/user',{'display_name':label+' 中文 😀𠮷','email':label+'@example.test','password':credentials[label+'_password']})
            user=login(client,label);ids[label]=str(user['id'])
            check('native_ordinary_user_'+label,user['role_id']==1 and sql('SELECT is_admin,status,LENGTH(pass) FROM user WHERE id=%s',(ids[label],))==((0,1,60),))
        (private/'credentials.json').write_text(json.dumps(credentials))
        check('wrong_password_login_denied',api(anonymous,'POST','/answer/api/v1/user/login/email',{'e_mail':'owner@example.test','pass':'wrong-'+secrets.token_hex(8)},denied=True))
        check('ordinary_user_admin_API_denied',api(owner,'POST','/answer/admin/api/user',{'display_name':'invalid-admin','email':'invalid@example.test','password':'Unused-Test-1234'},denied=True)
              and sql("SELECT COUNT(*) FROM user WHERE e_mail='invalid@example.test'")==((0,),))
        check('anonymous_question_write_denied',api(anonymous,'POST','/answer/api/v1/question',{'title':'unauthorized question','content':'invalid'},denied=True)
              and sql("SELECT COUNT(*) FROM question WHERE title='unauthorized question'")==((0,),))
        stage='native_QA_workflow'
        tag={'slug_name':'matrixone'}
        seed=api(admin,'POST','/answer/api/v1/question',{'title':'MatrixOne native fixture seed','content':'原生标签初始化 中文 😀𠮷','tags':[tag]})
        check('native_seed_tag_created',len(sql("SELECT id FROM tag WHERE slug_name='matrixone'"))==1)
        title='MatrixOne 问题 中文 😀𠮷';content='## 原生 Markdown\n\n数据库问题正文 中文 😀𠮷'
        question=api(owner,'POST','/answer/api/v1/question',{'title':title,'content':content,'tags':[tag]});qid=str(question['id'])
        check('native_question_values_and_owner',sql('SELECT title,original_text,user_id FROM question WHERE id=%s',(qid,))==((title,content,int(ids['owner'])),))
        check('native_question_tag_relation',sql("SELECT COUNT(*) FROM tag_rel r JOIN tag t ON t.id=r.tag_id WHERE r.object_id=%s AND t.slug_name='matrixone'",(qid,))==((1,),))
        answer_text='## 原生回答\n\n关联回答正文 中文 😀𠮷'
        answer=api(other,'POST','/answer/api/v1/answer',{'question_id':qid,'content':answer_text});aid=str(answer['info']['id'])
        check('native_answer_relation_and_owner',sql('SELECT question_id,user_id,original_text FROM answer WHERE id=%s',(aid,))==((int(qid),int(ids['other']),answer_text),))
        updated='## 更新回答\n\n重启持久化 中文 😀𠮷'
        api(other,'PUT','/answer/api/v1/answer',{'id':aid,'content':updated,'edit_summary':'原生更新'})
        check('native_answer_update_exact',sql('SELECT original_text FROM answer WHERE id=%s',(aid,))==((updated,),))
        before=sql('SELECT status,original_text FROM question WHERE id=%s',(qid,))
        check('other_user_question_delete_denied_no_change',api(other,'DELETE','/answer/api/v1/question',{'id':qid},denied=True)
              and sql('SELECT status,original_text FROM question WHERE id=%s',(qid,))==before)
        def readback(label):
            data=api(owner,'GET','/answer/api/v1/question/info',query={'id':qid})
            check(label+'_native_question_exact',str(data['id'])==qid and data['title']==title and data['content']==content)
            data=api(other,'GET','/answer/api/v1/answer/info',query={'id':aid})['info']
            check(label+'_native_answer_exact',str(data['id'])==aid and data['content']==updated)
            check(label+'_SQL_question_answer_relation',sql('SELECT a.question_id,a.user_id,q.user_id,q.title FROM answer a JOIN question q ON q.id=a.question_id WHERE a.id=%s',(aid,))==((int(qid),int(ids['other']),int(ids['owner']),title),))
        readback('before_restart');stage='native_restart';before=sql('SELECT original_text,user_id FROM answer WHERE id=%s',(aid,));old_pid=proc.pid;owned.stop(proc);proc=start()
        check('real_Answer_process_restart',proc.pid!=old_pid);readback('after_restart')
        check('after_restart_SQL_original_values_and_version',before==sql('SELECT original_text,user_id FROM answer WHERE id=%s',(aid,)) and sql('SELECT id,version_number FROM version')==((1,release['expected_native_DB_version']),))
        check('after_restart_ordinary_admin_denied',api(owner,'GET','/answer/admin/api/users/page',query={'page':1},denied=True))
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),));report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    return finish(out,report,'answer-native')


if __name__=='__main__':raise SystemExit(main())
