"""Strapi native schema/admin registration, draft/publish/relation/auth/restart."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import time
import urllib.error
import uuid

from native_common import Client,Processes,connection_config,finish,port,private_file,runtime_root
from strapi_runtime import prepare

ROOT=Path(__file__).resolve().parent


def main() -> int:
    import pymysql
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-config',type=Path,default=os.getenv('MO_STRAPI_RUNTIME_CONFIG') or None)
    parser.add_argument('--min-free-mib',type=int,default=2048)
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts'/('strapi-'+uuid.uuid4().hex[:12]))
    args=parser.parse_args()
    if args.min_free_mib<128:parser.error('Minimum disk admission floor is128MiB')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    schema='mo_reg_strapi_'+uuid.uuid4().hex[:16];private=runtime_root()/schema;private.mkdir(mode=0o700)
    report={'app':'strapi/strapi','version':'5.57.0','schema':schema,'passed':False,'checks':[],
            'existing_databases_modified':False,'manual_users_or_migration_stamps':False,'native_runtime_attempted':False,
            'min_free_mib':args.min_free_mib,'limitations':['prepared dependency/admin-build SDK only; cold installation/full monorepo/full UI unverified',
            'only article/category fixture content types and scoped UTF8 text decoding; unknown/binary types unverified',
            'basic draft/publish/relation and native RBAC; workflows/plugins/external providers/upgrade/load unverified']}
    owned=Processes(private,report);stage='admission'
    def check(name: str,value: object) -> None:
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        if not args.runtime_config or shutil.disk_usage(runtime_root()).free<args.min_free_mib*1024**2+20*1024**2:
            raise RuntimeError('Prepared SDK config and fresh assets headroom required')
        stage='verified_SDK';node,app,identity=prepare(args.runtime_config,private);report['SDK_identity']=identity
        check('pinned_Node_and_dependency_SDK',identity['dependency_files_verified']==66843 and identity['dependency_links_verified']==59)
        check('fresh_public_scaffold_and_original_admin_build',identity['scaffold_files_verified']==19 and identity['admin_asset_files_verified']==336 and not(app/'.env').exists())
        cfg=connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()');report['server_version'],report['runtime_git_version']=q.fetchone();check('actual_matrixone','MatrixOne' in report['server_version'])
                q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database']=schema
        def sql(query: str,params: tuple=()) -> tuple:
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query,params);return q.fetchall()
        credentials={k:secrets.token_hex(32) for k in ['admin_jwt_secret','api_token_salt','transfer_token_salt','encryption_key','app_key1','app_key2','jwt_secret']}
        credentials.update(admin_password='Mo1-'+secrets.token_hex(12),other_password='Mo1-'+secrets.token_hex(12));private_file(private/'credentials.json',json.dumps(credentials))
        base='http://127.0.0.1:'+str(port());web_port=base.rsplit(':',1)[1]
        env={**os.environ,'NODE_ENV':'production','NODE_OPTIONS':'--max-old-space-size=768','HOST':'127.0.0.1','PORT':web_port,
             'MATRIXONE_ADAPTER':'true','MO_NATIVE_METADATA_LOG':str(private/'typecast-metadata.private.jsonl'),'DATABASE_CLIENT':'mysql','DATABASE_HOST':cfg['host'],'DATABASE_PORT':str(cfg['port']),
             'DATABASE_NAME':schema,'DATABASE_USERNAME':cfg['user'],'DATABASE_PASSWORD':cfg['password'],'DATABASE_SSL':'false',
             'DATABASE_POOL_MIN':'0','DATABASE_POOL_MAX':'8','APP_KEYS':credentials['app_key1']+','+credentials['app_key2'],
             'ADMIN_JWT_SECRET':credentials['admin_jwt_secret'],'JWT_SECRET':credentials['jwt_secret'],
             'API_TOKEN_SALT':credentials['api_token_salt'],'TRANSFER_TOKEN_SALT':credentials['transfer_token_salt'],'ENCRYPTION_KEY':credentials['encryption_key'],
             'STRAPI_TELEMETRY_DISABLED':'true','STRAPI_DISABLE_UPDATE_NOTIFICATION':'true','BROWSER':'none',
             'XDG_CACHE_HOME':str(private/'cache'),'XDG_CONFIG_HOME':str(private/'config'),'XDG_DATA_HOME':str(private/'data')}
        anonymous=Client(base);admin=Client(base);other=Client(base)
        def start():
            p=owned.start([str(node),'node_modules/@strapi/strapi/bin/strapi.js','start'],app,env,'strapi');report['native_runtime_attempted']=True
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                if p.poll() is not None:raise RuntimeError('Native Strapi failed; private log retained')
                try:
                    if anonymous.request('GET','/_health',timeout=3).status_code in {200,204}:return p
                except(OSError,urllib.error.URLError):pass
                time.sleep(.3)
            raise TimeoutError('Native Strapi startup')
        stage='native_schema_sync';proc=start();report['native_table_count']=len(sql('SHOW TABLES'))
        check('native_schema_core_tables',all(sql('SHOW TABLES LIKE %s',(t,)) for t in ['admin_users','articles','categories','articles_category_lnk']))
        check('scoped_fixture_no_binary_columns',sql("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=%s AND LOWER(data_type) IN ('binary','varbinary','blob','tinyblob','mediumblob','longblob')",(schema,))==((0,),))
        def api(client: Client,method: str,path: str,body: dict|None=None,denied: bool=False):
            response=client.request(method,path,json_data=body,timeout=120)
            if denied:
                report.setdefault('denial_HTTP_statuses',[]).append({'path':path,'status':response.status_code})
                return response.status_code in {401,403,404} or (path=='/admin/login' and response.status_code==400)
            if response.status_code not in {200,201}:
                private_file(private/('failed-API-'+uuid.uuid4().hex+'.private'),response.content);raise AssertionError('native_API_'+method+'_'+path)
            return response.json()
        stage='native_admin_accounts'
        d=api(admin,'POST','/admin/register-admin',{'email':'admin@example.test','firstname':'Native','lastname':'Admin','password':credentials['admin_password']})['data']
        admin_id=d['user']['id'];credentials['admin_access_token']=d['token'];admin.headers['Authorization']='Bearer '+d['token'];(private/'credentials.json').write_text(json.dumps(credentials))
        check('native_first_admin_registration',sql('SELECT email,is_active,LENGTH(password) FROM admin_users WHERE id=%s',(admin_id,))==(('admin@example.test',1,60),))
        check('native_password_login',bool(api(Client(base),'POST','/admin/login',{'email':'admin@example.test','password':credentials['admin_password']})['data']['token']))
        check('wrong_admin_password_denied',api(Client(base),'POST','/admin/login',{'email':'admin@example.test','password':'incorrect-'+uuid.uuid4().hex},denied=True))
        roles=api(admin,'GET','/admin/roles')['data'];author_id=next(r['id'] for r in roles if r['code']=='strapi-author')
        d=api(admin,'POST','/admin/users',{'firstname':'Native','lastname':'Author','email':'other@example.test','roles':[author_id]})['data']
        registration=d['registrationToken'];credentials['other_registration_token']=registration
        d=api(other,'POST','/admin/register',{'registrationToken':registration,'userInfo':{'firstname':'Native','lastname':'Author','password':credentials['other_password']}})['data']
        other_id=d['user']['id'];credentials['other_access_token']=d['token'];other.headers['Authorization']='Bearer '+d['token'];(private/'credentials.json').write_text(json.dumps(credentials))
        check('native_second_account_registration_and_hash',other_id!=admin_id and sql('SELECT email,is_active,LENGTH(password) FROM admin_users WHERE id=%s',(other_id,))==(('other@example.test',1,60),))
        before=sql('SELECT COUNT(*) FROM admin_users')
        check('ordinary_admin_user_management_denied_zero_write',api(other,'POST','/admin/users',{'firstname':'Invalid','email':'invalid@example.test','roles':[author_id]},denied=True) and sql('SELECT COUNT(*) FROM admin_users')==before)
        stage='native_content_types'
        category_name='原生分类 中文 😀𠮷';category=api(admin,'POST','/content-manager/collection-types/api::category.category',{'name':category_name})['data'];category_doc=category['documentId']
        title='原生文章 中文 😀𠮷';body='文章正文 中文 😀𠮷'
        article=api(admin,'POST','/content-manager/collection-types/api::article.article',{'title':title,'body':body,'category':{'connect':[{'documentId':category_doc}]}})['data'];article_doc=article['documentId']
        path='/content-manager/collection-types/api::article.article/'+article_doc
        check('native_draft_values_and_owner',sql('SELECT title,body,created_by_id,published_at FROM articles WHERE document_id=%s',(article_doc,))==((title,body,admin_id,None),))
        check('native_category_exact',sql('SELECT name,document_id FROM categories WHERE document_id=%s',(category_doc,))==((category_name,category_doc),))
        check('native_draft_relation',sql('SELECT c.document_id FROM articles a JOIN articles_category_lnk l ON l.article_id=a.id JOIN categories c ON c.id=l.category_id WHERE a.document_id=%s',(article_doc,))==((category_doc,),))
        d=api(admin,'POST','/admin/api-tokens',{'name':'Native read/write token','description':'Isolated regression','type':'full-access','lifespan':604800000})['data']
        credentials['content_api_token']=d['accessKey'];(private/'credentials.json').write_text(json.dumps(credentials));content=Client(base);content.headers['Authorization']='Bearer '+d['accessKey']
        before=sql('SELECT COUNT(*) FROM strapi_api_tokens')
        check('ordinary_admin_privileged_token_denied_zero_write',api(other,'POST','/admin/api-tokens',{'name':'Invalid token','type':'full-access','lifespan':604800000},denied=True) and sql('SELECT COUNT(*) FROM strapi_api_tokens')==before)
        draft=api(content,'GET','/api/articles/'+article_doc+'?status=draft&populate=category')['data']
        check('native_token_draft_and_relation_readback',draft['title']==title and draft['body']==body and draft['category']['documentId']==category_doc)
        published=api(admin,'POST',path+'/actions/publish',{})['data'];check('native_publish_timestamp',bool(published.get('publishedAt')))
        def audit(label: str):
            rows=sql('SELECT title,body,created_by_id,published_at FROM articles WHERE document_id=%s',(article_doc,))
            check(label+'_native_two_versions_exact',len(rows)==2 and all(r[:3]==(title,body,admin_id) for r in rows) and sum(r[3] is None for r in rows)==1)
            check(label+'_native_relation_for_both_versions',sql('SELECT COUNT(*) FROM articles a JOIN articles_category_lnk l ON l.article_id=a.id JOIN categories c ON c.id=l.category_id WHERE a.document_id=%s AND c.document_id=%s',(article_doc,category_doc))==((2,),))
        audit('after_publish')
        check('anonymous_content_API_denied',api(anonymous,'GET','/api/articles/'+article_doc,denied=True))
        check('anonymous_admin_content_denied',api(anonymous,'GET',path,denied=True))
        invalid=Client(base);invalid.headers['Authorization']='Bearer incorrect-'+uuid.uuid4().hex
        check('wrong_content_token_denied',api(invalid,'GET','/api/articles/'+article_doc,denied=True))
        def readback(label: str):
            d=api(content,'GET','/api/articles/'+article_doc+'?populate=category')['data']
            private_file(private/(label+'-published-readback.private.json'),json.dumps(d,ensure_ascii=False))
            report.setdefault('published_readback_field_matches',{})[label]={'title':d.get('title')==title,'body':d.get('body')==body,'category_name':d.get('category',{}).get('name')==category_name,'category_document':d.get('category',{}).get('documentId')==category_doc,'published_at':bool(d.get('publishedAt'))}
            check(label+'_published_API_exact',d['title']==title and d['body']==body and d['category']['name']==category_name and d['category']['documentId']==category_doc and bool(d['publishedAt']))
        readback('before_restart')
        title='更新文章 中文 😀𠮷';body='更新正文 中文 😀𠮷';d=api(admin,'PUT',path,{'title':title,'body':body,'category':{'connect':[{'documentId':category_doc}]}})['data']
        check('native_draft_update',d['title']==title and d['body']==body);api(admin,'POST',path+'/actions/publish',{});audit('after_update')
        stage='native_restart';previous=proc.pid;owned.stop(proc);proc=start();check('real_Strapi_process_restart',proc.pid!=previous)
        readback('after_restart');audit('after_restart')
        check('native_admin_token_after_restart',api(admin,'GET','/admin/users/me')['data']['id']==admin_id)
        check('ordinary_privileged_token_still_denied',api(other,'POST','/admin/api-tokens',{'name':'Invalid restart token','type':'full-access','lifespan':604800000},denied=True))
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),));report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    finish(out,report,'strapi-native');return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
