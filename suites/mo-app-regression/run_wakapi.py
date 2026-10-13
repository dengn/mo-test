"""Pinned Wakapi native migrations/signup/API keys, exact heartbeat ledger/restart."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import time
import urllib.error
import urllib.parse
import uuid

from build_go_sdk import verified_binary
from native_common import Client, Processes, connection_config, digest, finish, port, private_file, runtime_root
from run_baikal import Session

ROOT = Path(__file__).resolve().parent
BINARY_SHA = '8c2f033b23814a1836b21d388a2dca1b35b3a1a23c5754962a2114b4a0c39ad6'


def main():
    import pymysql
    from bs4 import BeautifulSoup
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,default=os.getenv('MO_WAKAPI_BINARY') or None)
    parser.add_argument('--build-manifest',type=Path,default=os.getenv('MO_WAKAPI_BUILD_MANIFEST') or None)
    parser.add_argument('--min-free-mib',type=int,default=2048)
    parser.add_argument('--out',type=Path,default=ROOT/'artifacts'/('wakapi-'+uuid.uuid4().hex[:12]))
    args=parser.parse_args()
    if args.min_free_mib<128:parser.error('Minimum disk admission floor is 128 MiB')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    schema='mo_reg_wakapi_'+uuid.uuid4().hex[:16];private=runtime_root()/schema;private.mkdir(mode=0o700)
    report={'app':'muety/wakapi','version':'2.18.1','commit':'347f1f45ae2863d9499236471317a76630c5308f',
            'schema':schema,'passed':False,'checks':[],'min_free_mib':args.min_free_mib,
            'native_runtime_attempted':False,'existing_databases_modified':False,'manual_users_or_migration_stamps':False,
            'adaptation_patch_sha256':digest(ROOT/'fixtures/wakapi/matrixone-runtime.patch'),
            'limitations':['fresh native schema/pre-post migrations; populated upgrades and complete UI unverified',
                           'basic finite heartbeats only; historical unproved acknowledgments remain unproved',
                           'loopback HTTP with supported insecure_cookies, native auth/rate limits retained',
                           'native leaderboard/cache warming/external import/mail disabled through supported configuration']}
    owned=Processes(private,report);stage='admission'
    def check(name,value):
        report['checks'].append({'name':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free<args.min_free_mib*1024**2+40*1024**2:
            raise RuntimeError('Prepared pinned SDK and runtime headroom required')
        binary=args.binary.resolve();report['binary_identity']=verified_binary(binary,BINARY_SHA,args.build_manifest,'wakapi')
        check('pinned_native_binary',bool(report['binary_identity']))
        cfg=connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()');report['server_version'],report['runtime_git_version']=q.fetchone()
                check('actual_matrixone','MatrixOne' in report['server_version']);q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database']=schema
        def sql(query,params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query,params);return q.fetchall()
        base='http://localhost:'+str(port());web_port=int(base.rsplit(':',1)[1])
        config=private/'config.yml';private_file(config,'env: production\n')
        credentials={k:secrets.token_urlsafe(24) for k in ['admin_password','owner_password','other_password','password_salt']}
        credentials['cookie_key']=base64.b64encode(secrets.token_bytes(32)).decode();private_file(private/'credentials.json',json.dumps(credentials))
        env={**os.environ,'GOMAXPROCS':'2','GOMEMLIMIT':'512MiB','TZ':'UTC','WAKAPI_PORT':str(web_port),
             'WAKAPI_LISTEN_IPV4':'127.0.0.1','WAKAPI_LISTEN_IPV6':'-','WAKAPI_PUBLIC_URL':base,
             'WAKAPI_DB_HOST':cfg['host'],'WAKAPI_DB_PORT':str(cfg['port']),'WAKAPI_DB_USER':cfg['user'],
             'WAKAPI_DB_PASSWORD':cfg['password'],'WAKAPI_DB_NAME':schema,'WAKAPI_DB_TYPE':'mysql','WAKAPI_DB_CHARSET':'utf8mb4',
             'WAKAPI_DB_MAX_CONNECTIONS':'8','WAKAPI_DB_AUTOMIGRATE_FAIL_SILENTLY':'false',
             'WAKAPI_PASSWORD_SALT':credentials['password_salt'],'WAKAPI_COOKIE_KEY':credentials['cookie_key'],
             'WAKAPI_INSECURE_COOKIES':'true','WAKAPI_ALLOW_SIGNUP':'true','WAKAPI_MAIL_ENABLED':'false',
             'WAKAPI_LEADERBOARD_ENABLED':'false','WAKAPI_WARM_CACHES':'false','WAKAPI_IMPORT_ENABLED':'false'}
        admin=Session(base);owner=Session(base);other=Session(base);anonymous=Client(base)
        def start(timeout=90):
            proc=owned.start([str(binary),'-config',str(config)],private,env,'wakapi');report['native_runtime_attempted']=True
            started=time.monotonic();deadline=started+timeout
            while time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('Native Wakapi failed; private log retained')
                try:
                    if anonymous.request('GET','/login',timeout=3).status_code==200:
                        report.setdefault('native_startup_seconds',[]).append(round(time.monotonic()-started,3));return proc
                except(OSError,urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native Wakapi startup')
        stage='native_migrations';proc=start();report['native_table_count']=len(sql('SHOW TABLES'))
        check('native_core_schema',all(sql('SHOW TABLES LIKE %s',(n,)) for n in ['users','heartbeats','api_keys','summaries','summary_items']))
        before_foreign=sql('SELECT constraint_name,table_name,referenced_table_name FROM information_schema.referential_constraints WHERE constraint_schema=%s ORDER BY constraint_name',(schema,))
        check('native_heartbeat_foreign_key_retained',any(r[1]=='heartbeats' and r[2]=='users' for r in before_foreign))
        stage='native_users'
        users={'admin':('moadmin',admin),'owner':('moowner',owner),'other':('moother',other)}
        keys={}
        for label,(username,client) in users.items():
            response=client.request('POST','/signup',data={'username':username,'email':'',
                     'password':credentials[label+'_password'],'password_repeat':credentials[label+'_password'],'location':'UTC'})
            report.setdefault('signup_HTTP_statuses',{})[label]=response.status_code
            private_file(private/('signup-'+label+'.private.html'),response.content)
            check('native_signup_'+label,response.status_code==200 and sql('SELECT COUNT(*) FROM users WHERE id=%s',(username,))==((1,),))
            response=client.request('POST','/login',data={'username':username,'password':credentials[label+'_password']})
            check('native_password_cookie_login_'+label,response.status_code==200 and response.path.startswith('/summary'))
            response=client.request('GET','/setup');field=BeautifulSoup(response.text,'html.parser').select_one('#api-key-instruction')
            check('native_API_key_setup_'+label,response.status_code==200 and field is not None and len(field.get_text(strip=True))>=32)
            keys[label]=field.get_text(strip=True);credentials[label+'_api_key']=keys[label]
            (private/'credentials.json').write_text(json.dumps(credentials))
        check('native_roles_and_password_hashes',sql('SELECT id,is_admin,LEFT(password,10),auth_type,location FROM users ORDER BY id')==(('moadmin',1,'$argon2id$','local','UTC'),('moother',0,'$argon2id$','local','UTC'),('moowner',0,'$argon2id$','local','UTC')))
        check('native_distinct_keys_exact_SQL',len(set(keys.values()))==3 and dict(sql('SELECT id,api_key FROM users'))=={users[k][0]:v for k,v in keys.items()})
        response=Session(base).request('POST','/login',data={'username':'moowner','password':'incorrect-'+uuid.uuid4().hex})
        check('wrong_password_denied',response.status_code==401)
        def api_client(key):
            client=Client(base);client.headers={'Authorization':'Basic '+base64.b64encode(key.encode()).decode()};return client
        api={label:api_client(key) for label,key in keys.items()};wrong=api_client('incorrect-'+uuid.uuid4().hex)
        endpoint='/api/compat/wakatime/v1/users/current/heartbeats'
        today=datetime.now(timezone.utc).strftime('%Y-%m-%d');query='?'+urllib.parse.urlencode({'date':today})
        check('anonymous_heartbeat_read_denied',anonymous.request('GET',endpoint+query).status_code==401)
        check('wrong_API_key_denied',wrong.request('GET',endpoint+query).status_code==401)
        check('other_user_private_read_denied',api['other'].request('GET',endpoint.replace('current','moowner')+query).status_code==401)
        stage='native_heartbeats';stamp=int(time.time())-120;expected={};payloads={}
        for label in ['owner','other']:
            payloads[label]=[{'entity':'/原生目录/中文 😀𠮷-'+label+'-'+str(i)+'.py','type':'file','category':'coding',
                             'project':'原生项目 中文 😀𠮷 '+label,'language':'Python','time':stamp+i,
                             'is_write':bool(i%2),'branch':'分支 中文 😀𠮷'} for i in range(8)]
            expected.update({(users[label][0],p['entity']):p for p in payloads[label]})
        def send(label):
            response=api[label].request('POST','/api/heartbeat',json_data=payloads[label],headers={'X-Machine-Name':'mo-native-machine'})
            data=response.json()
            return response.status_code==201 and len(data.get('responses',[]))==8 and all(r[1]==201 for r in data['responses'])
        with ThreadPoolExecutor(max_workers=2) as pool:acknowledged=list(pool.map(send,['owner','other']))
        check('native_two_user_16_heartbeats_acknowledged',all(acknowledged));report['acknowledged_heartbeats']=16
        def audit(label):
            rows=sql('SELECT h.id,h.user_id,h.entity,h.type,h.category,h.project,h.language,h.`time`,h.is_write,h.branch,h.machine,u.id FROM heartbeats h JOIN users u ON h.user_id=u.id')
            found={(r[1],r[2]):r for r in rows};check(label+'_all_acknowledged_rows_present',len(rows)==16 and set(found)==set(expected))
            check(label+'_exact_values_times_and_user_links',all(r[1]==r[11] and r[3:7]==(p['type'],p['category'],p['project'],p['language']) and r[7]==datetime.fromtimestamp(p['time'],timezone.utc).replace(tzinfo=None) and bool(r[8])==p['is_write'] and r[9]==p['branch'] and r[10]=='mo-native-machine' for k,p in expected.items() for r in [found[k]]))
            report['durable_heartbeats']=len(rows);report['native_ID_count']=len({r[0] for r in rows})
            check(label+'_native_primary_ID_unique',report['native_ID_count']==16)
        audit('after_write')
        for label in ['owner','other']:
            response=api[label].request('POST','/api/heartbeat',json_data=payloads[label],headers={'X-Machine-Name':'mo-native-machine'})
            check('native_duplicate_batch_ACK_'+label,response.status_code==201 and all(r[1]==201 for r in response.json()['responses']))
        check('native_duplicate_no_extra_rows',sql('SELECT COUNT(*) FROM heartbeats')==((16,),))
        response=api['other'].request('POST','/api/users/moowner/heartbeats',json_data=payloads['owner'])
        check('cross_user_write_denied_zero_write',response.status_code==401 and sql('SELECT COUNT(*) FROM heartbeats')==((16,),))
        check('anonymous_write_denied_zero_write',anonymous.request('POST','/api/heartbeat',json_data=payloads['owner']).status_code==401 and sql('SELECT COUNT(*) FROM heartbeats')==((16,),))
        def readback(prefix):
            for label in ['owner','other']:
                response=api[label].request('GET',endpoint+query);data=response.json().get('data',[])
                found={p['entity']:p for p in data};expected_user={p['entity']:p for p in payloads[label]}
                check(prefix+'_native_API_exact_'+label,response.status_code==200 and len(data)==8 and set(found)==set(expected_user) and all(found[e]['user_id']==users[label][0] and all(found[e][k]==p[k] for k in ['type','category','project','language','time','is_write','branch']) for e,p in expected_user.items()))
        readback('before_restart');stage='native_restart';previous=proc.pid;owned.stop(proc);report['restart_startup_timeout_seconds']=180;proc=start(timeout=180)
        check('real_Wakapi_process_restart',proc.pid!=previous);readback('after_restart');audit('after_restart')
        check('native_foreign_keys_unchanged_after_restart',sql('SELECT constraint_name,table_name,referenced_table_name FROM information_schema.referential_constraints WHERE constraint_schema=%s ORDER BY constraint_name',(schema,))==before_foreign)
        response=owner.request('GET','/settings');check('native_cookie_auth_after_restart',response.status_code==200 and response.path=='/settings')
        check('after_restart_other_user_denied',api['other'].request('GET',endpoint.replace('current','moowner')+query).status_code==401)
        check('post_trigger_SQL_health',sql('SELECT 1')==((1,),));report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    finish(out,report,'wakapi-native');return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
