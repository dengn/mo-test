"""Adapted pinned ntfy: native CLI, identity/ACL, live protocols, cache and restart."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
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

from native_common import runtime_root, Client, Processes, connection_config, digest, finish, port, private_file
from native_websocket import WebSocket
from build_go_sdk import verified_binary

ROOT = Path(__file__).resolve().parent
SHA = '9158288f609906d7bca174a71ad2ccf5603425bb10459d22a890e81568cccca1'
COMMIT = 'f18d1137c63a26e85b91ce639e7bc72bb9a82736'


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=os.getenv('MO_NTFY_BINARY') or None)
    parser.add_argument('--build-manifest', type=Path, default=os.getenv('MO_NTFY_BUILD_MANIFEST') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('ntfy-' + uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:
        parser.error('Minimum admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_ntfy_' + uuid.uuid4().hex[:16]
    private = runtime_root() / schema; private.mkdir(parents=True, mode=0o700)
    report = {'app': 'binwiederhier/ntfy', 'version': 'v2.29.0', 'commit': COMMIT,
              'binary_sha256': SHA, 'schema': schema, 'checks': [], 'passed': False,
              'native_runtime_attempted': False, 'native_CLI_users_and_ACL': True,
              'source_adapted': True, 'manual_users_or_migration_stamps': False,
              'existing_databases_modified': False, 'min_free_mib': args.min_free_mib, 'native_default_rate_limits_retained': True,
              'limitations': ['explicit MatrixOne backend with fresh schema only',
                              'populated upgrades, clustering and MatrixOne webpush unsupported',
                              'upstream nofirebase/nopayments build; placeholder web UI not verified',
                              'indexed text VARCHAR4096; broader collation equivalence unverified']}
    owned = Processes(private, report); ws = None; stage = 'admission'

    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)

    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free < args.min_free_mib * 1024**2:
            raise RuntimeError('Pinned adapted binary and configured disk headroom are required')
        app = args.binary.resolve()
        report['binary_identity'] = verified_binary(app, SHA, args.build_manifest, 'ntfy')
        report['binary_sha256'] = report['binary_identity']['sha256']
        check('pinned_adapted_native_binary', True)
        cfg = connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()')
                report['server_version'], report['runtime_git_version'] = q.fetchone()
                check('actual_matrixone', 'MatrixOne' in report['server_version'])
                q.execute('CREATE DATABASE `' + schema + '` CHARACTER SET utf8mb4')
        cfg['database'] = schema
        def sql(query, params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:
                    q.execute(query, params); return q.fetchall()
        web_port = port(); base = 'http://127.0.0.1:' + str(web_port)
        credentials = {'owner': {'username': 'moalice', 'password': secrets.token_urlsafe(24)},
                       'other': {'username': 'mobob', 'password': secrets.token_urlsafe(24)}}
        private_file(private / 'credentials.json', json.dumps(credentials))
        config_path = private / 'server.yml'
        host = cfg['host']; host = '[' + host + ']' if ':' in host else host
        database_url = 'matrixone://' + urllib.parse.quote(cfg['user'], safe='') + ':' + urllib.parse.quote(cfg['password'], safe='') + '@' + host + ':' + str(cfg['port']) + '/' + schema
        (private / 'attachments').mkdir(mode=0o700)
        # JSON is valid YAML; no dependency on the previous session's config or credentials.
        private_file(config_path, json.dumps({'base-url': base, 'listen-http': '127.0.0.1:' + str(web_port),
            'database-url': database_url, 'auth-default-access': 'deny-all', 'enable-login': True,
            'enable-signup': False, 'cache-duration': '24h', 'attachment-cache-dir': str(private / 'attachments'),
            'log-level': 'warn'}))
        env = {k: v for k, v in os.environ.items() if not k.startswith('NTFY_')}
        env.update(GOMAXPROCS='2', GOMEMLIMIT='512MiB', XDG_CONFIG_HOME=str(private / 'config'), XDG_CACHE_HOME=str(private / 'cache'))
        stage = 'native_CLI'
        for label, user in credentials.items():
            p = owned.start([str(app), 'user', '--config', str(config_path), 'add', user['username']],
                            private, {**env, 'NTFY_PASSWORD': user['password']}, 'add-' + label)
            report['native_runtime_attempted'] = True
            try:
                code = p.wait(timeout=120)
            except subprocess.TimeoutExpired:
                owned.stop(p); raise
            check('native_CLI_create_' + label, code == 0)
            pattern = 'mo_test_*' if label == 'owner' else 'mo_other_*'
            p = owned.start([str(app), 'access', '--config', str(config_path), user['username'], pattern, 'rw'], private, env, 'ACL-' + label)
            code = p.wait(timeout=120); check('native_CLI_ACL_' + label, code == 0)
        anonymous, owner, other = Client(base), Client(base), Client(base)
        def start():
            process = owned.start([str(app), 'serve', '--config', str(config_path)], private, env, 'ntfy')
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Native ntfy startup failed; private log retained')
                try:
                    if anonymous.request('GET', '/v1/health', timeout=2).status_code == 200:
                        return process
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.2)
            raise TimeoutError('Native ntfy startup')
        stage = 'authentication'; proc = start()
        def login(client, label, wrong=False):
            user = credentials[label]; pw = 'incorrect-' + uuid.uuid4().hex if wrong else user['password']
            auth = 'Basic ' + base64.b64encode((user['username'] + ':' + pw).encode()).decode()
            response = client.request('POST', '/v1/account/login', headers={'Authorization': auth})
            if wrong:
                check('wrong_password_denied', response.status_code == 401); return
            model = response.json()
            check('native_password_token_login_' + label, response.status_code == 200 and model.get('username') == user['username'] and bool(model.get('token')))
            client.headers['Authorization'] = 'Bearer ' + model['token']
        login(anonymous, 'owner', wrong=True); login(owner, 'owner'); login(other, 'other')
        check('native_schema_message15_user9', dict(sql('SELECT store,version FROM schema_version')) == {'message': 15, 'user': 9})
        check('native_normal_user_password_rows', sql("SELECT `user`,role,LENGTH(pass) FROM `user` WHERE `user` IN ('moalice','mobob') ORDER BY `user`") == (('moalice', 'user', 60), ('mobob', 'user', 60)))
        check('native_two_user_ACL_links', sql("SELECT COUNT(*) FROM user_access a JOIN `user` u ON u.id=a.user_id WHERE u.`user` IN ('moalice','mobob')") == ((2,),))
        topic = 'mo_test_' + uuid.uuid4().hex[:12]; other_topic = 'mo_other_' + uuid.uuid4().hex[:12]
        stage = 'permissions'
        before = sql('SELECT COUNT(*) FROM messages')[0][0]
        check('cross_user_publish_denied', other.request('POST', '/', json_data={'topic': topic, 'message': 'forbidden'}).status_code == 403)
        check('cross_user_cache_read_denied', other.request('GET', '/' + topic + '/json?poll=1').status_code == 403)
        check('anonymous_publish_denied', anonymous.request('POST', '/', json_data={'topic': topic, 'message': 'forbidden'}).status_code == 403)
        check('case_sensitive_topic_ACL', owner.request('POST', '/', json_data={'topic': topic.upper(), 'message': 'forbidden'}).status_code == 403)
        check('denied_publishes_no_rows', sql('SELECT COUNT(*) FROM messages')[0][0] == before)
        stage = 'native_live_delivery'
        ws = WebSocket(web_port, '/' + topic + '/ws', owner.headers['Authorization'])
        check('native_WebSocket_open', ws.message().get('event') == 'open')
        message = json.dumps({'text': 'MatrixOne 通知 😀𠮷', 'amount': '1234.56', 'nested': {'boolean': True, 'nullable': None}}, ensure_ascii=False)
        def publish(client, selected_topic, body):
            response = client.request('POST', '/', json_data={'topic': selected_topic, 'message': body,
                'title': '原生通知 中文 😀𠮷', 'priority': 4, 'tags': ['matrixone', '中文😀']})
            result = response.json()
            if response.status_code != 200 or result.get('message') != body or result.get('topic') != selected_topic or not result.get('id'):
                raise AssertionError('native_publish_exact_ACK')
            return result
        live = publish(owner, topic, message)
        # Upstream WS encodes Message directly; HTTP/JSON/SSE use ForJSON(), which
        # omits sequence_id when it equals id. Preserve and assert that native difference.
        check('native_WebSocket_exact_notification', ws.message() == {**live, 'sequence_id': live['id']})
        ws.close(); ws = None
        def history(client, selected_topic):
            response = client.request('GET', '/' + selected_topic + '/json?poll=1&since=all')
            if response.status_code != 200:
                raise AssertionError('native_authenticated_history_status')
            return [json.loads(line) for line in response.text.splitlines() if line]
        check('native_cache_exact_message', live in history(owner, topic))
        response = owner.request('GET', '/' + topic + '/sse?poll=1&since=all')
        check('native_SSE_poll_exact_notification', response.status_code == 200 and response.headers.get('Content-Type', '').startswith('text/event-stream') and any(
            json.loads(line[6:]) == live for line in response.text.splitlines() if line.startswith('data: ')))
        stage = 'shared_IP_concurrent_identity'
        work = [('owner' if i % 2 == 0 else 'other', 'parallel-' + uuid.uuid4().hex + ' 中文 😀𠮷') for i in range(8)]
        def send(item):
            label, body = item
            return label, publish(owner if label == 'owner' else other, topic if label == 'owner' else other_topic, body)
        with ThreadPoolExecutor(max_workers=4) as executor:
            writes = list(executor.map(send, work))
        check('two_native_users_concurrent_ACK_unique', len({item[1]['id'] for item in writes}) == 8)
        def audit_messages(name):
            expected = [('owner', live)] + writes
            rows = sql('SELECT m.mid,m.message,m.title,m.priority,m.tags,m.topic,u.`user` FROM messages m JOIN `user` u ON u.id=m.`user` WHERE m.topic IN (%s,%s)', (topic, other_topic))
            mapping = {row[0]: row for row in rows}
            check(name, len(rows) == len(mapping) == len(expected) and all(mapping.get(doc['id']) ==
                (doc['id'], doc['message'], doc['title'], 4, 'matrixone,中文😀', doc['topic'], credentials[label]['username']) for label, doc in expected))
            return sorted(rows)
        audit_messages('SQL_exact_notifications_and_concurrent_publisher_identity')
        stage = 'preferences'
        check('native_JSON_preferences_update', owner.request('PATCH', '/v1/account/settings', json_data={'language': 'zh', 'notification': {'min_priority': 3}}).status_code == 200)
        response = owner.request('GET', '/v1/account')
        check('native_JSON_preferences_readback', response.status_code == 200 and response.json().get('language') == 'zh')
        prefs = json.loads(sql('SELECT prefs FROM `user` WHERE `user`=%s', ('moalice',))[0][0])
        check('SQL_exact_nested_JSON_preferences', prefs.get('language') == 'zh' and prefs.get('notification', {}).get('min_priority') == 3)
        stage = 'lifecycle'; sequence = 'mo-sequence-' + uuid.uuid4().hex
        events = []
        for body in ['初始 中文 😀𠮷', '更新 中文 😀𠮷']:
            response = owner.request('POST', '/', json_data={'topic': topic, 'message': body, 'sequence_id': sequence})
            model = response.json(); check('native_sequence_ACK_' + str(len(events)), response.status_code == 200 and model.get('sequence_id') == sequence and model.get('message') == body); events.append(model)
        response = owner.request('DELETE', '/' + topic + '/' + sequence); deleted = response.json()
        check('native_sequence_delete_event', response.status_code == 200 and deleted.get('event') == 'message_delete' and deleted.get('sequence_id') == sequence)
        events.append(deleted)
        check('native_notification_lifecycle_history', all(event in history(owner, topic) for event in events))
        stage = 'attachment'; content = ('MatrixOne attachment 中文 😀𠮷\n'.encode() + b'\x00\xff') * 160
        response = owner.request('PUT', '/' + topic, data=content, headers={'Content-Type': 'application/octet-stream', 'Filename': 'matrixone-attachment.bin'})
        attachment_doc = response.json(); attachment = attachment_doc.get('attachment', {})
        parsed = urllib.parse.urlsplit(attachment.get('url', ''))
        check('native_attachment_created_on_owned_loopback', response.status_code == 200 and attachment.get('size') == len(content) and parsed.scheme == 'http' and parsed.netloc == '127.0.0.1:' + str(web_port))
        attachment_path = parsed.path
        def attachment_read(name, client):
            response = client.request('GET', attachment_path)
            check(name, response.status_code == 200 and response.content == content)
        attachment_read('native_attachment_exact_original_bytes', owner)
        attachment_read('native_default_capability_attachment_access', anonymous)
        check('SQL_attachment_original_metadata_link', sql('SELECT attachment_size,attachment_url FROM messages WHERE mid=%s', (attachment_doc['id'],)) == ((len(content), attachment['url']),))
        stage = 'restart'; before = sql('SELECT mid,message,topic,`user`,attachment_url FROM messages ORDER BY mid')
        old_pid = proc.pid; owned.stop(proc); proc = start(); check('real_process_restart', proc.pid != old_pid)
        check('SQL_exact_original_rows_after_restart', before == sql('SELECT mid,message,topic,`user`,attachment_url FROM messages ORDER BY mid'))
        check('native_original_token_and_history_after_restart', live in history(owner, topic) and all(doc in history(owner if label == 'owner' else other, topic if label == 'owner' else other_topic) for label, doc in writes))
        attachment_read('restart_original_attachment_bytes', anonymous)
        response = owner.request('GET', '/v1/account')
        check('native_original_token_and_preferences_after_restart', response.status_code == 200 and response.json().get('language') == 'zh')
        check('post_trigger_SQL_health', sql('SELECT 1') == ((1,),))
        report['passed'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, failed_stage=stage)
        if isinstance(exc, AssertionError):
            report['failed_check'] = str(exc)
    finally:
        if ws:
            ws.close()
        owned.close()
    return finish(out, report, 'ntfy-native')


if __name__ == '__main__':
    raise SystemExit(main())
