"""Pinned unmodified Memos source build: native bootstrap, private notes and restart."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import shutil
import time
import urllib.error
import uuid

from native_common import runtime_root, Client, Processes, connection_config, digest, finish, port, private_file
from build_go_sdk import verified_binary

ROOT = Path(__file__).resolve().parent
COMMIT = 'd5df8915f70a108971f9bf01151ecd3de3e0c91f'
SHA = '97e52d79444628fcd5b3343d2c048be8ac81e9393c7c8d551d0dc8f2dd46c98e'


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=os.getenv('MO_MEMOS_BINARY') or None)
    parser.add_argument('--build-manifest', type=Path, default=os.getenv('MO_MEMOS_BUILD_MANIFEST') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('memos-' + uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:
        parser.error('Minimum admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_memos_' + uuid.uuid4().hex[:16]
    private = runtime_root() / schema; private.mkdir(parents=True, mode=0o700)
    report = {'app': 'usememos/memos', 'commit': COMMIT, 'binary_sha256': SHA, 'schema': schema,
              'passed': False, 'checks': [], 'native_runtime_attempted': False, 'source_edits': False,
              'manual_users_or_migration_stamps': False, 'existing_databases_modified': False, 'min_free_mib': args.min_free_mib,
              'native_rate_limits_retained': True, 'limitations': ['native API only; full browser UI, integrations and populated upgrades unverified']}
    owned = Processes(private, report); stage = 'admission'

    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)

    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free < args.min_free_mib * 1024**2:
            raise RuntimeError('Pinned native binary and disk headroom required')
        app = args.binary.resolve()
        report['binary_identity'] = verified_binary(app, SHA, args.build_manifest, 'memos')
        report['binary_sha256'] = report['binary_identity']['sha256']
        check('pinned_native_binary', True)
        cfg = connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()')
                report['server_version'], report['runtime_git_version'] = q.fetchone()
                check('actual_matrixone', 'MatrixOne' in report['server_version'])
                q.execute('CREATE DATABASE `' + schema + '` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
        cfg['database'] = schema
        def sql(query, params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:
                    q.execute(query, params); return q.fetchall()
        web_port = port(); base = 'http://127.0.0.1:' + str(web_port)
        anonymous, owner, other = Client(base), Client(base), Client(base)
        creds = {'owner': {'username': 'mo-owner', 'password': secrets.token_urlsafe(24)},
                 'other': {'username': 'mo-other', 'password': secrets.token_urlsafe(24)}}
        private_file(private / 'credentials.json', json.dumps(creds))
        host = cfg['host']; host = '[' + host + ']' if ':' in host else host
        dsn = f"{cfg['user']}:{cfg['password']}@tcp({host}:{cfg['port']})/{schema}?charset=utf8mb4&parseTime=true&loc=UTC&multiStatements=true"
        env = {k: v for k, v in os.environ.items() if not k.startswith('MEMOS_')}
        env.update(MEMOS_DRIVER='mysql', MEMOS_DSN=dsn, MEMOS_ADDR='127.0.0.1', MEMOS_PORT=str(web_port),
                   MEMOS_DATA=str(private / 'data'), MEMOS_DEMO='false', MEMOS_RATE_LIMIT='true',
                   MEMOS_LOG_LEVEL='warn', MEMOS_INSTANCE_URL=base, GOMAXPROCS='2', GOMEMLIMIT='512MiB')
        def start():
            process = owned.start([str(app)], private, env, 'memos'); report['native_runtime_attempted'] = True
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Native initialization exited; private log retained')
                try:
                    response = anonymous.request('GET', '/api/instance/profile', timeout=2)
                    if response.status_code == 200:
                        return process
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.2)
            raise TimeoutError('Native Memos startup')
        stage = 'native_initialization'; proc = start()
        tables = {row[0] for row in sql('SHOW TABLES')}
        check('native_schema_created', {'user', 'memo', 'system_setting', 'space', 'attachment'}.issubset(tables))
        check('no_manual_users_before_bootstrap', sql('SELECT COUNT(*) FROM `user`') == ((0,),))
        stage = 'native_bootstrap'
        response = anonymous.request('POST', '/api/users', json_data={**creds['owner'], 'displayName': 'MatrixOne 管理员 😀𠮷'})
        model = response.json()
        check('native_first_user_admin_bootstrap', response.status_code == 200 and model.get('username') == 'mo-owner' and model.get('role') == 'ADMIN')
        def signin(client, label, wrong=False):
            submitted = creds[label].copy()
            if wrong:
                submitted['password'] = 'incorrect-' + uuid.uuid4().hex
            response = client.request('POST', '/api/auth/signin', json_data={'passwordCredentials': submitted})
            if wrong:
                check('wrong_password_denied', response.status_code in {400, 401} and not response.json().get('accessToken')); return
            model = response.json()
            check('native_password_login_' + label, response.status_code == 200 and bool(model.get('accessToken')) and model.get('user', {}).get('username') == creds[label]['username'])
            client.headers['Authorization'] = 'Bearer ' + model['accessToken']
        signin(anonymous, 'owner', wrong=True); signin(owner, 'owner')
        response = owner.request('POST', '/api/users', json_data={**creds['other'], 'role': 'USER', 'displayName': '普通用户 中文 😀'})
        check('native_ordinary_user_creation', response.status_code == 200 and response.json().get('role') == 'USER')
        signin(other, 'other')
        check('native_password_hashes_and_roles', sql('SELECT username,role,LENGTH(password_hash) FROM `user` ORDER BY username') == (('mo-other', 'USER', 60), ('mo-owner', 'ADMIN', 60)))
        stage = 'native_private_memos'
        content = '# MatrixOne 回归\n\n正文 中文 😀𠮷\n\n金额 1234.56\n\n- [ ] 未完成\n\n#mo_reg_tag'
        def create(text):
            response = owner.request('POST', '/api/memos', json_data={'content': text, 'visibility': 'PRIVATE'})
            model = response.json()
            if response.status_code != 200 or model.get('content') != text or model.get('visibility') != 'PRIVATE' or model.get('creator') != 'users/mo-owner' or not model.get('name'):
                raise AssertionError('native_memo_exact_create')
            return model
        memo = create(content); name = memo['name']; check('native_private_memo_create', True)
        response = owner.request('GET', '/api/' + name)
        check('native_exact_content_and_creator_read', response.status_code == 200 and all(response.json().get(k) == memo[k] for k in ['name', 'content', 'visibility', 'creator']))
        check('anonymous_private_memo_denied', anonymous.request('GET', '/api/' + name).status_code in {401, 403, 404})
        check('other_user_private_memo_denied', other.request('GET', '/api/' + name).status_code in {403, 404})
        before = sql('SELECT content FROM memo WHERE uid=%s', (name.split('/')[-1],))
        response = other.request('PATCH', '/api/' + name + '?updateMask=content', json_data={'content': 'Forbidden change'})
        check('cross_user_update_denied_zero_content_change', response.status_code in {403, 404} and before == sql('SELECT content FROM memo WHERE uid=%s', (name.split('/')[-1],)))
        updated = content + '\n\n更新内容 精确 😀𠮷'
        response = owner.request('PATCH', '/api/' + name + '?updateMask=content', json_data={'content': updated})
        check('native_memo_update_exact', response.status_code == 200 and response.json().get('content') == updated)
        stage = 'concurrent_memos'
        texts = ['并发记录-' + uuid.uuid4().hex + ' 中文 😀𠮷' for _ in range(4)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            written = list(pool.map(create, texts))
        check('native_concurrent_ACK_identifiers_unique', len({doc['name'] for doc in written}) == 4)
        expected = {doc['name'].split('/')[-1]: doc['content'] for doc in written}
        expected[name.split('/')[-1]] = updated
        def audit(label):
            rows = sql('SELECT m.uid,m.content,m.visibility,u.username FROM memo m JOIN `user` u ON u.id=m.creator_id')
            check(label, len(rows) == len(expected) and {r[0]: r[1] for r in rows} == expected and all(r[2:] == ('PRIVATE', 'mo-owner') for r in rows))
            return sorted(rows)
        before = audit('SQL_exact_all_content_and_owner_links')
        def read_all(label):
            response = owner.request('GET', '/api/memos?pageSize=100'); models = response.json().get('memos', [])
            mapping = {doc['name'].split('/')[-1]: doc for doc in models}
            check(label, response.status_code == 200 and len(models) == len(expected) and all(
                mapping.get(uid, {}).get('content') == text and mapping[uid].get('creator') == 'users/mo-owner' for uid, text in expected.items()))
        read_all('native_authenticated_list_exact')
        response = other.request('GET', '/api/memos?pageSize=100')
        check('ordinary_user_list_excludes_owner_private_memos', response.status_code == 200 and not response.json().get('memos'))
        stage = 'native_restart'; old_pid = proc.pid; owned.stop(proc); proc = start()
        check('real_process_restart', proc.pid != old_pid)
        check('SQL_exact_original_content_after_restart', before == audit('restart_SQL_exact_all_content_and_owner_links'))
        read_all('native_original_token_list_after_restart')
        check('restart_ordinary_user_private_read_denied', other.request('GET', '/api/' + name).status_code in {403, 404})
        stage = 'native_delete'
        check('native_memo_delete', owner.request('DELETE', '/api/' + name).status_code == 200)
        check('native_deleted_memo_not_readable', owner.request('GET', '/api/' + name).status_code == 404)
        check('SQL_deleted_memo_absent', sql('SELECT COUNT(*) FROM memo WHERE uid=%s', (name.split('/')[-1],)) == ((0,),))
        check('post_trigger_SQL_health', sql('SELECT 1') == ((1,),))
        report['passed'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, failed_stage=stage)
        if isinstance(exc, AssertionError):
            report['failed_check'] = str(exc)
    finally:
        owned.close()
    return finish(out, report, 'memos-native')


if __name__ == '__main__':
    raise SystemExit(main())
