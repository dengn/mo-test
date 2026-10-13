"""Pinned Documize binary, fresh native setup, real HTTP/FTS/SQL and process restart."""
import argparse
import base64
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid

from native_common import runtime_root, Client, Processes, connection_config, digest, finish, port, private_file

ROOT = Path(__file__).resolve().parent
SHA = 'be729653f76fde784a339a7e89b48481db322502ef28e0e32f3df057790efb8f'
URL = 'https://github.com/documize/community/releases/download/v5.14.0/documize-community-linux-amd64'


class Meta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('property') in {'dbname', 'dbhash'}:
            self.values[attrs['property']] = attrs.get('content', '')


def binary(provided):
    if provided:
        target = provided.resolve()
    else:
        target = runtime_root() / 'documize-v5.14.0/documize'
        if not target.exists():
            if shutil.disk_usage(runtime_root()).free < 2 * 1024**3 + 62032210:
                raise RuntimeError('Keep 2 GiB free after downloading native binary')
            target.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(URL, timeout=90) as response:
                data = response.read(62032211)
            if len(data) != 62032210:
                raise RuntimeError('Official binary size mismatch')
            private_file(target, data)
            target.chmod(0o700)
    if digest(target) != SHA:
        raise RuntimeError('Official binary hash mismatch')
    return target


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('documize-' + uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128 or (args.min_free_mib < 2048 and not args.binary):
        parser.error('Below 2 GiB requires a local pinned binary; minimum 128 MiB')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_documize_' + uuid.uuid4().hex[:16]
    private = runtime_root() / schema
    private.mkdir(parents=True, mode=0o700)
    report = {'app': 'documize/community', 'version': 'v5.14.0',
              'commit': 'bdc19f135d9c9a7f448b07c584f1106e76d2f0d8', 'binary_sha256': SHA,
              'schema': schema, 'passed': False, 'checks': [], 'native_runtime_attempted': False,
              'native_binary_unmodified': True, 'local_packet_adapter': True,
              'manual_users_or_migration_stamps': False, 'existing_databases_modified': False,
              'min_free_mib': args.min_free_mib,
              'limitations': ['physical ENGINE conversions and OPTIMIZE explicitly omitted',
                              'DDL implicit commit boundary made explicit', 'populated upgrades unverified']}
    owned = Processes(private, report)
    stage = 'admission'

    def check(name, valid):
        report['checks'].append({'name': name, 'passed': bool(valid)})
        if not valid:
            raise AssertionError(name)

    try:
        if shutil.disk_usage(runtime_root()).free < args.min_free_mib * 1024**2:
            raise RuntimeError('Insufficient configured disk headroom')
        app = binary(args.binary)
        cfg = connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(), git_version()')
                report['server_version'], report['runtime_git_version'] = q.fetchone()
                check('actual_matrixone', 'MatrixOne' in report['server_version'])
                q.execute('CREATE DATABASE `' + schema + '` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
        cfg['database'] = schema

        def sql(query, params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:
                    q.execute(query, params)
                    return q.fetchall()

        web_port, adapter_port = port(), port()
        email, password, salt = 'mo-admin@documize.invalid', secrets.token_urlsafe(24), secrets.token_hex(32)
        private_file(private / 'credentials.json', json.dumps({'admin_email': email, 'admin_password': password, 'salt': salt}))
        dsn = f"{cfg['user']}:{cfg['password']}@tcp(127.0.0.1:{adapter_port})/{schema}?charset=utf8mb4&parseTime=true&multiStatements=true"
        config = '[database]\ntype = "mysql"\nconnection = ' + json.dumps(dsn) + '\nsalt = ' + json.dumps(salt)
        config += '\n\n[http]\nport = ' + str(web_port) + '\n\n[install]\nlocation = "selfhost"\n'
        private_file(private / 'documize.conf', config)
        env = {**os.environ, 'GOMAXPROCS': '2', 'GOMEMLIMIT': '512MiB',
               'XDG_CACHE_HOME': str(private / 'cache'), 'XDG_CONFIG_HOME': str(private / 'config')}
        stage = 'adapter_startup'
        adapter = owned.start([sys.executable, str(ROOT / 'adapters/documize_mysql_adapter.py'),
            '--port', str(adapter_port), '--upstream-host', cfg['host'], '--upstream-port', str(cfg['port']),
            '--audit', str(private / 'private-adapter-SQL.jsonl')], private, env, 'adapter')
        deadline = time.monotonic() + 15
        while True:
            if adapter.poll() is not None:
                raise RuntimeError('Adapter exited; private log retained')
            try:
                with socket.create_connection(('127.0.0.1', adapter_port), timeout=1):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError('Adapter startup')
                time.sleep(.1)
        client = Client('http://127.0.0.1:' + str(web_port))

        def start(setup=False):
            process = owned.start([str(app)], private, env, 'documize')
            report['native_runtime_attempted'] = True
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Native process exited; private log retained')
                try:
                    response = client.request('GET', '/setup' if setup else '/', timeout=2)
                    if response.status_code == 200:
                        return process, response
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.25)
            raise TimeoutError('Native HTTP startup')

        stage = 'native_setup'
        proc, response = start(setup=True)
        meta = Meta(); meta.feed(response.text)
        check('native_setup_token_and_fresh_database', meta.values.get('dbname') == schema and bool(meta.values.get('dbhash')))
        response = client.request('POST', '/api/setup', timeout=180, data={
            'dbname': schema, 'dbhash': meta.values['dbhash'], 'title': 'MatrixOne 文档回归 😀𠮷',
            'message': 'Native isolated regression', 'firstname': 'MatrixOne', 'lastname': 'Tester',
            'email': email, 'password': password, 'activationKey': ''})
        check('native_setup_completed', response.status_code == 200 and response.headers.get('Location') == '/')
        tables = sql('SHOW TABLES')
        version = sql("SELECT c_config FROM dmz_config WHERE c_key='META'")
        check('native_35_migrations_and_27_tables', len(tables) == 27 and len(version) == 1 and json.loads(version[0][0])['database'] == '34')
        report['native_migrations_completed'] = 35
        users = sql('SELECT c_email,c_globaladmin,LENGTH(c_password) FROM dmz_user WHERE c_email=%s', (email,))
        check('native_setup_admin_password_and_identity', users == ((email, 1, 60),))

        def request(method, path, **kwargs):
            return client.request(method, '/api/' + path, **kwargs)

        def auth(pw):
            basic = base64.b64encode((':' + email + ':' + pw).encode()).decode()
            return request('POST', 'public/authenticate', headers={'Authorization': 'Basic ' + basic})

        stage = 'authentication'
        check('wrong_password_denied', auth('incorrect-' + uuid.uuid4().hex).status_code == 401)
        check('anonymous_private_space_denied', request('GET', 'space').status_code in {401, 403})
        response = auth(password); model = response.json(); user = model.get('user', {})
        check('native_password_login', response.status_code == 200 and bool(model.get('token')) and user.get('email') == email)
        client.headers['Authorization'] = 'Bearer ' + model['token']
        stage = 'space'
        cohort = 'docreg' + uuid.uuid4().hex[:12]
        space_name = cohort + ' 空间 😀𠮷'
        response = request('POST', 'space', json_data={'name': space_name, 'icon': 'book', 'labelId': '', 'cloneId': ''})
        space = response.json(); sid = space.get('id')
        check('native_private_space_create', response.status_code == 200 and space.get('name') == space_name and bool(sid))
        stage = 'document'
        name = cohort + ' 文档 😀𠮷'
        response = request('POST', f'templates/0/folder/{sid}?type=saved', data=name.encode(), headers={'Content-Type': 'text/plain; charset=utf-8'})
        doc = response.json(); did = doc.get('id')
        check('native_document_create', response.status_code == 200 and doc.get('name') == name and doc.get('spaceId') == sid)
        updated = name + ' 更新'; doc.update(name=updated, excerpt='精确摘要 😀𠮷')
        check('native_document_update', request('PUT', 'documents/' + did, json_data=doc).status_code == 200)
        response = request('GET', 'documents/' + did); doc = response.json()
        check('native_document_exact_read', response.status_code == 200 and doc.get('name') == updated and doc.get('excerpt') == '精确摘要 😀𠮷')
        stage = 'section'
        html, title = '<p>' + cohort + ' 原生正文 中文 😀𠮷</p>', cohort + ' 章节 😀'
        response = request('POST', f'documents/{did}/pages', json_data={
            'page': {'documentId': did, 'title': title, 'contentType': 'wysiwyg', 'pageType': 'section', 'level': 1, 'sequence': 1},
            'meta': {'documentId': did, 'rawBody': html, 'config': '{}', 'externalSource': False}})
        page = response.json(); pid = page.get('id')
        check('native_section_create_render', response.status_code == 200 and page.get('title') == title and page.get('body') == html)

        def readback(prefix):
            response = request('GET', 'documents/' + did); doc = response.json()
            check(prefix + '_native_doc', response.status_code == 200 and doc.get('name') == updated and doc.get('spaceId') == sid)
            response = request('GET', f'documents/{did}/pages/{pid}'); page = response.json()
            check(prefix + '_native_section', response.status_code == 200 and page.get('title') == title and page.get('body') == html)
            for _ in range(30):
                response = request('POST', 'search', json_data={'keywords': cohort, 'doc': True, 'content': True, 'tag': False, 'attachment': False, 'slog': True})
                rows = response.json()
                if response.status_code == 200 and isinstance(rows, list) and any(x.get('documentId') == did for x in rows):
                    break
                time.sleep(.5)
            check(prefix + '_native_fulltext_search', response.status_code == 200 and isinstance(rows, list) and any(x.get('documentId') == did for x in rows))

        audit_sql = ('SELECT d.c_name,d.c_desc,d.c_userid,s.c_name,s.c_userid,p.c_name,p.c_body,p.c_docid,m.c_rawbody '
                     'FROM dmz_doc d JOIN dmz_space s ON s.c_refid=d.c_spaceid JOIN dmz_section p ON p.c_docid=d.c_refid '
                     'JOIN dmz_section_meta m ON m.c_sectionid=p.c_refid WHERE d.c_refid=%s AND p.c_refid=%s')
        def audit(prefix):
            rows = [tuple(v.decode() if isinstance(v, bytes) else v for v in row) for row in sql(audit_sql, (did, pid))]
            check(prefix + '_SQL_exact_content_and_owner_links', rows == [(updated, '精确摘要 😀𠮷', user['id'], space_name, user['id'], title, html, did, html)])
            return rows

        stage = 'before_restart'; before = audit('before_restart'); readback('before_restart')
        stage = 'native_restart'; old_pid = proc.pid; owned.stop(proc); proc, _ = start()
        check('real_process_restart', proc.pid != old_pid)
        after = audit('after_restart'); check('SQL_durability', before == after); readback('after_restart')
        check('original_JWT_survives_restart', request('GET', 'space/' + sid).status_code == 200)
        check('post_trigger_SQL_health', sql('SELECT 1') == ((1,),))
        report['passed'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, failed_stage=stage)
        if isinstance(exc, AssertionError):
            report['failed_check'] = str(exc)
    finally:
        owned.close()
    return finish(out, report, 'documize-native')


if __name__ == '__main__':
    raise SystemExit(main())
