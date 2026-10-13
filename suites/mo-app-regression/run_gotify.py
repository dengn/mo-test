from native_common import runtime_root
"""Pinned official Gotify app: native initialization, REST, SQL audit, and process restart."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
URL = 'https://github.com/gotify/server/releases/download/v3.1.1/gotify-linux-amd64.zip'
ARCHIVE_SHA = 'd452faad071981d191d5c95f70d0f9520dc2ef2336b2b03055e12cfabfbae2d2'
BINARY_SHA = '7c5fbcce5fa130c8e7bf643fee4f069a3aed974ead16bc5a84a168e31930e7b7'


def binary(archive):
    target = runtime_root() / 'gotify-v3.1.1' / 'gotify-linux-amd64'
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == BINARY_SHA:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if archive is None:
        archive = target.parent / 'release.zip'
        with urllib.request.urlopen(URL, timeout=60) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != ARCHIVE_SHA:
            raise RuntimeError('Official archive hash mismatch')
        archive.write_bytes(data)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA:
        raise RuntimeError('Provided archive hash mismatch')
    with zipfile.ZipFile(archive) as z:
        data = z.read('gotify-linux-amd64')
    if hashlib.sha256(data).hexdigest() != BINARY_SHA:
        raise RuntimeError('Official binary hash mismatch')
    target.write_bytes(data)
    target.chmod(0o700)
    return target


def main():
    import pymysql
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, help='Optional already downloaded official zip; SHA is always verified')
    parser.add_argument('--binary', type=Path, help='Optional official binary; pinned SHA is always verified')
    parser.add_argument('--messages', type=int, default=16)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('gotify-' + uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if not 1 <= args.messages <= 256 or not 1 <= args.workers <= 16:
        parser.error('CI bounds: 1..256 messages, 1..16 workers')
    password = os.environ.get('MO_PASSWORD')
    if password is None:
        parser.error('MO_PASSWORD must be supplied through the environment')
    args.out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_gotify_' + uuid.uuid4().hex[:16]
    private = runtime_root() / schema
    private.mkdir(mode=0o700, parents=True)
    config = dict(host=os.environ.get('MO_HOST', '127.0.0.1'), port=int(os.environ.get('MO_PORT', '6001')),
                  user=os.environ.get('MO_USER', 'root'), password=password, charset='utf8mb4',
                  autocommit=True, connect_timeout=10, read_timeout=30)
    owner, owner_pass = 'reg_owner', secrets.token_urlsafe(24)
    outsider, outsider_pass = 'reg_other', secrets.token_urlsafe(24)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = 'http://127.0.0.1:' + str(port)
    report = {'app': 'gotify/server', 'version': 'v3.1.1', 'archive_sha256': ARCHIVE_SHA,
              'binary_sha256': BINARY_SHA, 'schema': schema, 'checks': [],
              'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'existing_databases_modified': False, 'native_schema_initialization': True}
    proc, log = None, None
    def check(name, condition, **metrics):
        report['checks'].append({'name': name, 'passed': bool(condition), **metrics})
        if not condition:
            raise AssertionError(name)
    def request(method, path, payload=None, token=None, auth=None, expected=200):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Gotify-Key'] = token
        if auth:
            headers['Authorization'] = 'Basic ' + base64.b64encode((':'.join(auth)).encode()).decode()
        data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        # Loopback app traffic bypasses an HTTP proxy; dependency downloads retain the normal proxy.
        local = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with local.open(req, timeout=15) as r:
                status, body = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, e.read()
        if status != expected:
            raise AssertionError(f'{method} {path} expected {expected}, received {status}')
        return json.loads(body) if body else None
    def stop():
        nonlocal proc
        if proc is not None:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=10)
            proc = None
    try:
        app_bin = args.binary.resolve() if args.binary else binary(args.archive)
        if hashlib.sha256(app_bin.read_bytes()).hexdigest() != BINARY_SHA:
            raise RuntimeError('Official binary hash mismatch')
        report['binary_source'] = 'local_pinned_binary' if args.binary else 'official_release_archive'
        with pymysql.connect(**config) as c:
            with c.cursor() as q:
                q.execute('SELECT VERSION()')
                report['server_version'] = q.fetchone()[0]
                check('target_is_matrixone', 'MatrixOne' in report['server_version'])
                q.execute('CREATE DATABASE `' + schema + '`')
        host = config['host']
        if ':' in host:
            host = '[' + host + ']'
        env = {k: v for k, v in os.environ.items() if not k.startswith('GOTIFY_')}
        env.update(GOTIFY_DATABASE_DIALECT='mysql',
                   GOTIFY_DATABASE_CONNECTION=f"{config['user']}:{password}@tcp({host}:{config['port']})/{schema}?charset=utf8mb4&parseTime=true&loc=Local",
                   GOTIFY_DEFAULTUSER_NAME=owner, GOTIFY_DEFAULTUSER_PASS=owner_pass,
                   GOTIFY_SERVER_LISTENADDR='127.0.0.1', GOTIFY_SERVER_PORT=str(port),
                   GOTIFY_UPLOADEDIMAGESDIR=str(private / 'images'), GOTIFY_LOGLEVEL='warn',
                   GOMAXPROCS='2', GOMEMLIMIT='512MiB')
        fd = os.open(private / 'native.log', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        log = os.fdopen(fd, 'wb')
        def start():
            nonlocal proc
            proc = subprocess.Popen([str(app_bin)], cwd=private, env=env, stdout=log, stderr=log, start_new_session=True)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError('Native app startup exited; private log is retained locally')
                try:
                    request('GET', '/health')
                    return
                except (OSError, AssertionError):
                    time.sleep(0.2)
            raise TimeoutError('Native app startup timed out')
        start()
        check('native_initialization_and_health', True)
        oa = (owner, owner_pass)
        ca = request('POST', '/client', {'name': 'regression client'}, auth=oa)
        app = request('POST', '/application', {'name': '回归应用 😀𠮷', 'description': 'owned fixture'}, auth=oa)
        check('native_client_and_application', bool(ca['id']) and bool(app['id']))
        request('POST', '/user', {'name': outsider, 'pass': outsider_pass, 'admin': False}, auth=oa)
        other = request('POST', '/client', {'name': 'outsider'}, auth=(outsider, outsider_pass))
        request('GET', '/message', expected=401)
        request('POST', '/message', {'message': 'must not persist'}, token='invalid-owned-test-token', expected=401)
        check('anonymous_and_invalid_token_denied', True)
        prefix = 'native-reg-' + uuid.uuid4().hex + '-'
        def publish(i):
            payload = {'message': prefix + str(i) + ' 中文 😀𠮷', 'title': '精确值 ' + str(i), 'priority': i % 5,
                       'extras': {'regression::value': {'index': i, 'unicode': '中文 😀𠮷'}}}
            row = request('POST', '/message', payload, token=app['token'])
            return {'payload': payload, 'response': row}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            written = list(pool.map(publish, range(args.messages)))
        ids = {x['response']['id'] for x in written}
        check('concurrent_native_acknowledgments', len(ids) == args.messages, attempted=args.messages,
              acknowledged=len(written), unique_ids=len(ids), workers=args.workers)
        def api_audit():
            read, path, visited = [], '/message?limit=100', set()
            for _ in range(8):
                if path in visited:
                    return False
                visited.add(path)
                page = request('GET', path, token=ca['token'])
                read.extend(page['messages'])
                path = page['paging'].get('next')
                if not path:
                    break
                if not path.startswith('/message?'):
                    return False
            else:
                return False
            byid = {x['id']: x for x in read}
            return len(read) == len(byid) == args.messages and all(x['response']['id'] in byid and
                       all(byid[x['response']['id']].get(k) == v for k, v in x['payload'].items())
                       and byid[x['response']['id']]['appid'] == app['id'] for x in written)
        check('exact_native_api_readback', api_audit())
        check('cross_user_isolation', request('GET', '/message?limit=100', token=other['token'])['messages'] == [])
        def sql_audit():
            with pymysql.connect(**config, database=schema) as c:
                with c.cursor() as q:
                    q.execute('SELECT m.id,m.message,m.title,m.priority,m.extras,a.id,u.name FROM messages m '
                              'JOIN applications a ON a.id=m.application_id JOIN users u ON u.id=a.user_id')
                    rows = {r[0]: r for r in q.fetchall()}
                    expected = {x['response']['id']: x['payload'] for x in written}
                    if set(rows) != set(expected):
                        return False
                    for mid, payload in expected.items():
                        r = rows[mid]
                        if list(r[1:4]) != [payload['message'], payload['title'], payload['priority']]:
                            return False
                        if json.loads(r[4]) != payload['extras'] or r[5] != app['id'] or r[6] != owner:
                            return False
                    return True
        check('sql_exact_content_and_owner_relationships', sql_audit())
        old_pid = proc.pid
        stop()
        start()
        check('real_process_restart', proc.pid != old_pid)
        check('restart_tokens_and_exact_api_values', api_audit())
        check('restart_sql_durability', sql_audit(), durable_messages=args.messages)
        check('restart_cross_user_isolation', request('GET', '/message?limit=100', token=other['token'])['messages'] == [])
        report['passed'] = True
    except Exception as e:
        report['passed'] = False
        report['error_type'] = type(e).__name__
        # Internal stage names are safe; no native error or HTTP response body is exported.
        if isinstance(e, AssertionError):
            report['failed_check'] = str(e) if ':' not in str(e) else 'native assertion'
    finally:
        stop()
        if log:
            log.close()
    report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    (args.out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    checks = report['checks'][:]
    if not report['passed'] and all(c['passed'] for c in checks):
        checks.append({'name': 'native_execution', 'passed': False})
    suite = ET.Element('testsuite', name='gotify-native', tests=str(len(checks)),
                       failures=str(sum(not x['passed'] for x in checks)))
    for c in checks:
        tc = ET.SubElement(suite, 'testcase', name=c['name'], classname='gotify.native')
        if not c['passed']:
            ET.SubElement(tc, 'failure', message=c['name'])
    ET.ElementTree(suite).write(args.out / 'junit.xml', encoding='utf-8', xml_declaration=True)
    print(json.dumps({'passed': report['passed'], 'checks': len(checks), 'schema': schema,
                      'error_type': report.get('error_type'), 'failed_check': report.get('failed_check')}))
    return int(not report['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
