"""Pinned Gogs native schema/users/tokens/private Git/issues/comments and restart."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import sys
import time
import urllib.error
import uuid

from build_go_sdk import verified_binary
from native_common import Client, Processes, connection_config, finish, port, private_file, runtime_root

ROOT = Path(__file__).resolve().parent
COMMIT = 'dbbd717e923694c36f41b0360515b4374bbe6ee0'
LEGACY_SHA = '472668c143db076052594ce046de109203df181f703ad615286ddd9b83b6bf2d'


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=os.getenv('MO_GOGS_BINARY') or None)
    parser.add_argument('--build-manifest', type=Path, default=os.getenv('MO_GOGS_BUILD_MANIFEST') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT/'artifacts'/('gogs-'+uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:parser.error('Minimum disk admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_gogs_'+uuid.uuid4().hex[:16]; private = runtime_root()/schema; private.mkdir(parents=True, mode=0o700)
    report = {'app':'gogs/gogs', 'commit':COMMIT, 'schema':schema, 'passed':False, 'checks':[],
              'native_runtime_attempted':False, 'existing_databases_modified':False, 'manual_users_or_migration_stamps':False,
              'min_free_mib':args.min_free_mib, 'source_edits':['pinned vendored XORM table and index metadata recognition'],
              'limitations':['known native concurrent NextIssueIndex race remains; issue writes here are sequential',
                             'full new UI/SSH/mirrors/hooks/plugins/populated upgrades unverified',
                             'periodic cron disabled on this owned test instance']}
    owned = Processes(private, report); stage = 'admission'
    def check(name, value):
        report['checks'].append({'name':name, 'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free < args.min_free_mib*1024**2+32*1024**2:
            raise RuntimeError('Pinned native SDK and runtime disk reserve required')
        binary = args.binary.resolve(); report['binary_identity'] = verified_binary(binary, LEGACY_SHA, args.build_manifest, 'gogs')
        check('pinned_native_binary', True)
        cfg = connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()'); report['server_version'], report['runtime_git_version'] = q.fetchone()
                check('actual_matrixone', 'MatrixOne' in report['server_version']); q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database'] = schema
        def sql(query, params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query, params); return q.fetchall()
        credentials = {k:secrets.token_urlsafe(32) for k in ['bootstrap_password','owner_password','other_password','secret_key']}
        private_file(private/'credentials.json', json.dumps(credentials))
        web_port = port(); base = 'http://127.0.0.1:'+str(web_port)
        config = private/'app.ini'; host = cfg['host']; host = '['+host+']' if ':' in host else host
        private_file(config, 'BRAND_NAME = Gogs regression\nRUN_USER = '+pwd.getpwuid(os.getuid()).pw_name+'\nRUN_MODE = prod\n'
            '[server]\nHTTP_ADDR = 127.0.0.1\nHTTP_PORT = '+str(web_port)+'\nEXTERNAL_URL = '+base+'/\nDISABLE_SSH = true\n'
            'SSH_ROOT_PATH = '+str(private/'ssh')+'\nAPP_DATA_PATH = '+str(private/'data')+'\nOFFLINE_MODE = true\n'
            '[repository]\nROOT = '+str(private/'repos')+'\n[database]\nTYPE = mysql\nHOST = ${MO_GOGS_DB_HOST}\n'
            'NAME = '+schema+'\nUSER = ${MO_GOGS_DB_USER}\nPASSWORD = ${MO_GOGS_DB_PASSWORD}\n'
            '[security]\nSECRET_KEY = ${MO_GOGS_SECRET_KEY}\n'
            '[session]\nPROVIDER = file\nPROVIDER_CONFIG = '+str(private/'sessions')+'\n'
            '[log]\nROOT_PATH = '+str(private/'logs')+'\n[cron]\nENABLED = false\nRUN_AT_START = false\n')
        env = {**os.environ, 'MO_GOGS_DB_HOST':host+':'+str(cfg['port']), 'MO_GOGS_DB_USER':cfg['user'],
               'MO_GOGS_DB_PASSWORD':cfg['password'], 'MO_GOGS_SECRET_KEY':credentials['secret_key'],
               'GOGS_WORK_DIR':str(private), 'GOGS_CUSTOM':str(private/'custom'), 'GIT_CONFIG_GLOBAL':str(private/'gitconfig'),
               'GIT_TERMINAL_PROMPT':'0', 'GOMAXPROCS':'2', 'GOMEMLIMIT':'512MiB'}
        private_file(private/'gitconfig', '[user]\n name = MO regression\n email = regression@example.test\n[commit]\n gpgsign = false\n')
        bootstrap, owner, other, anonymous = Client(base), Client(base), Client(base), Client(base)
        def start():
            p = owned.start([str(binary),'web','--config',str(config)], private, env, 'gogs'); report['native_runtime_attempted'] = True
            deadline = time.monotonic()+60
            while time.monotonic()<deadline:
                if p.poll() is not None:raise RuntimeError('Native Gogs startup failed; private log retained')
                try:
                    if anonymous.request('GET','/api/v1/users/search?q=mo',timeout=3).status_code==200:return p
                except (OSError,urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native Gogs readiness')
        stage = 'native_schema'; proc = start()
        check('native_schema_version_22', sql('SELECT id,version FROM version')==((1,22),))
        check('native_schema_core_tables', {'user','repository','issue','comment','access_token','version'} <= {r[0] for r in sql('SHOW TABLES')})
        p = owned.start([str(binary),'admin','create-user','--name','mo-bootstrap','--password',credentials['bootstrap_password'],
                         '--email','bootstrap@example.test','--admin','--config',str(config)],private,env,'gogs-bootstrap')
        if p.wait(timeout=60)!=0:raise RuntimeError('Native CLI bootstrap failed; private log retained')
        check('native_CLI_bootstrap_user', sql("SELECT name,is_admin FROM user")==(('mo-bootstrap',1),))
        def api(client, method, path, data=None, status=200, headers=None):
            response = client.request(method, '/api/v1'+path, json_data=data, headers=headers, timeout=90)
            if response.status_code != status:
                report.update(failed_HTTP_status=response.status_code, failed_native_endpoint=path)
                private_file(private/('failed-native-'+str(len(report['checks']))+'.response'), response.content)
                raise AssertionError('native_HTTP_'+method+'_'+path)
            return response.json() if response.content else None
        def token(client, username, password):
            headers = {'Authorization':'Basic '+base64.b64encode((username+':'+password).encode()).decode()}
            result = api(client,'POST','/users/'+username+'/tokens',{'name':'owned-regression'},status=201,headers=headers)
            value = result['sha1']; client.headers['Authorization'] = 'token '+value
            return value
        stage = 'native_users'
        credentials['bootstrap_token'] = token(bootstrap,'mo-bootstrap',credentials['bootstrap_password'])
        user_ids = {}
        for label,client in [('owner',owner),('other',other)]:
            result = api(bootstrap,'POST','/admin/users',{'username':'mo-'+label,'full_name':label+' 中文 😀𠮷',
                'email':label+'@example.test','password':credentials[label+'_password'],'send_notify':False},status=201)
            user_ids[label] = int(result['id']); credentials[label+'_token'] = token(client,'mo-'+label,credentials[label+'_password'])
            check('native_ordinary_user_'+label,sql('SELECT name,is_admin FROM user WHERE id=%s',(result['id'],))==(('mo-'+label,0),))
        (private/'credentials.json').write_text(json.dumps(credentials))
        rows = sql('SELECT name,passwd,salt FROM user')
        check('native_PBKDF2_passwords_exact', all(hashlib.pbkdf2_hmac('sha256',credentials[name.removeprefix('mo-')+'_password'].encode(),salt.encode(),10000,50).hex()==hashed for name,hashed,salt in rows))
        rows = sql('SELECT uid,sha256,sha1 FROM access_token'); identities = {r[0]:r[1] for r in sql('SELECT id,name FROM user')}
        check('native_token_hash_not_plaintext', len(rows)==3 and all(hashlib.sha256(credentials[identities[uid].removeprefix('mo-')+'_token'].encode()).hexdigest()==sha and sha[:40]==prefix for uid,sha,prefix in rows))
        check('native_owner_token_identity',api(owner,'GET','/user')['id']==user_ids['owner'])
        wrong = Client(base); response = wrong.request('POST','/api/v1/users/mo-owner/tokens',json_data={'name':'invalid'},
            headers={'Authorization':'Basic '+base64.b64encode(('mo-owner:incorrect-'+uuid.uuid4().hex).encode()).decode()})
        check('wrong_password_token_denied_zero_new_token',response.status_code==401 and sql('SELECT COUNT(*) FROM access_token')==((3,),))
        response = owner.request('POST','/api/v1/admin/users',json_data={'username':'invalid-admin','email':'invalid@example.test','password':'unused-fixture'})
        check('ordinary_user_admin_creation_denied',response.status_code==403 and sql("SELECT COUNT(*) FROM user WHERE name='invalid-admin'")==((0,),))
        stage = 'native_private_repository'
        repo_name='mo-private'; description='私有仓库 中文 😀𠮷'
        result = api(owner,'POST','/user/repos',{'name':repo_name,'description':description,'private':True,'auto_init':True,'readme':'Default'},status=201)
        repo_id = int(result['id']); repo_path='/repos/mo-owner/'+repo_name
        check('native_private_repository_owner',sql('SELECT owner_id,is_private,description FROM repository WHERE id=%s',(repo_id,))==((user_ids['owner'],1,description),))
        check('other_user_private_repo_denied',other.request('GET','/api/v1'+repo_path).status_code==404)
        check('anonymous_private_repo_denied',anonymous.request('GET','/api/v1'+repo_path).status_code==404)
        stage = 'native_git_HTTP'
        askpass=private/'git-askpass.py'; private_file(askpass,'#!'+sys.executable+'\nimport os,sys\nprint(os.environ["MO_GOGS_GIT_USER"] if "username" in sys.argv[1].lower() else os.environ["MO_GOGS_GIT_PASSWORD"])\n'); askpass.chmod(0o700)
        git_env={**env,'GIT_ASKPASS':str(askpass),'MO_GOGS_GIT_USER':'mo-owner','MO_GOGS_GIT_PASSWORD':credentials['owner_password']}
        clone=private/'clone'
        def git(args,cwd=private):
            import subprocess
            result=subprocess.run(['git',*args],cwd=cwd,env=git_env,capture_output=True,timeout=90)
            if result.returncode:
                private_file(private/('failed-git-'+str(len(report['checks']))+'.log'),result.stdout+result.stderr)
                raise AssertionError('native_Git_HTTP_operation')
            return result.stdout.strip().decode()
        git(['clone',base+'/mo-owner/'+repo_name+'.git',str(clone)])
        check('native_Git_HTTP_clone', (clone/'.git').is_dir() and (clone/'README.md').is_file())
        payload=bytes(range(256))*4+'Git 原字节 中文 😀𠮷\n'.encode(); (clone/'fixture.bin').write_bytes(payload)
        git(['add','fixture.bin'],clone);git(['commit','-m','Native fixture UTF8'],clone);commit=git(['rev-parse','HEAD'],clone);branch=git(['symbolic-ref','--short','HEAD'],clone)
        git(['push','origin',branch],clone); raw_path=repo_path+'/raw/'+branch+'/fixture.bin'
        response=owner.request('GET','/api/v1'+raw_path)
        check('native_Git_HTTP_push_and_exact_bytes', response.status_code==200 and response.content==payload)
        report['Git_fixture_sha256']=hashlib.sha256(payload).hexdigest();report['Git_fixture_commit']=commit
        stage='native_issues_comments';expected={}
        for i in range(4):
            title='原生 issue 中文 😀𠮷 '+str(i);body='关联仓库正文 中文 😀𠮷 '+str(i)
            result=api(owner,'POST',repo_path+'/issues',{'title':title,'body':body},status=201);expected[int(result['number'])]=(int(result['id']),title,body)
        check('native_four_issues_and_owner_relations',{n:(ident,title,body) for n,ident,title,body in sql('SELECT `index`,id,name,content FROM issue WHERE repo_id=%s',(repo_id,))}==expected
              and sql('SELECT COUNT(*) FROM issue WHERE repo_id=%s AND poster_id=%s',(repo_id,user_ids['owner']))==((4,),))
        number=next(iter(expected));issue_path=repo_path+'/issues/'+str(number);issue_id=expected[number][0];comment_text='原生评论 中文 😀𠮷'
        result=api(owner,'POST',issue_path+'/comments',{'body':comment_text},status=201);comment_id=int(result['id'])
        check('native_comment_SQL_owner_and_issue',sql('SELECT content,poster_id,issue_id FROM comment WHERE id=%s',(comment_id,))==((comment_text,user_ids['owner'],issue_id),))
        new_title='更新 issue 中文 😀𠮷';new_body='更新正文 中文 😀𠮷';api(owner,'PATCH',issue_path,{'title':new_title,'body':new_body},status=201);expected[number]=(issue_id,new_title,new_body)
        check('native_issue_update_exact',sql('SELECT name,content FROM issue WHERE id=%s',(issue_id,))==((new_title,new_body),))
        response=other.request('PATCH','/api/v1'+issue_path,json_data={'title':'invalid cross user'})
        check('other_user_issue_update_denied_zero_change',response.status_code==404 and sql('SELECT name FROM issue WHERE id=%s',(issue_id,))==((new_title,),))
        check('anonymous_issue_read_denied',anonymous.request('GET','/api/v1'+issue_path).status_code==401)
        def readback(label):
            issues=api(owner,'GET',repo_path+'/issues');actual={int(r['number']):(int(r['id']),r['title'],r['body']) for r in issues}
            check(label+'_native_issues_exact',actual==expected)
            comments=api(owner,'GET',issue_path+'/comments');check(label+'_native_comment_exact',len(comments)==1 and comments[0]['body']==comment_text and int(comments[0]['id'])==comment_id)
            response=owner.request('GET','/api/v1'+raw_path);check(label+'_native_Git_bytes',response.status_code==200 and response.content==payload)
        readback('before_restart');before=sql('SELECT `index`,id,name,content FROM issue WHERE repo_id=%s ORDER BY `index`',(repo_id,))
        stage='native_restart';old_pid=proc.pid;owned.stop(proc);proc=start();check('real_Gogs_process_restart',old_pid!=proc.pid)
        readback('after_restart');check('after_restart_SQL_values_and_native_schema',before==sql('SELECT `index`,id,name,content FROM issue WHERE repo_id=%s ORDER BY `index`',(repo_id,)) and sql('SELECT id,version FROM version')==((1,22),))
        check('after_restart_other_user_denied',other.request('GET','/api/v1'+issue_path).status_code==404)
        api(owner,'DELETE',issue_path+'/comments/'+str(comment_id),status=204)
        check('native_comment_delete_zero_row',sql('SELECT COUNT(*) FROM comment WHERE id=%s',(comment_id,))==((0,),))
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),));report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    return finish(out,report,'gogs-native')


if __name__=='__main__':raise SystemExit(main())
