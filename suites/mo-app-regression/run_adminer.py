"""Pinned Adminer native PDO login/forms/SQL/CSV, types, constraints and restart."""
import argparse
import csv
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from run_baikal import Session
from native_common import Processes, connection_config, digest, finish, port, private_file, runtime_root

ROOT = Path(__file__).resolve().parent
PHP_SHA = '9f738981bbcce1906329b751e57411171d5db0629ee00da0a41514f4a3d2f280'
ORIGINAL_SHA = 'b32316156bd18ffa99c1a27617142c2e5ad72260e37f15da4e9937a3dbb15f57'
ADAPTED_SHA = '18c566f45c5b885dd9b937b91ba0e6347203740b6344ba0b74ec5508fcf9b0ab'
URL = 'https://github.com/vrana/adminer/releases/download/v6.1.2/adminer-6.1.2.php'


def package(provided, app):
    if provided:
        data = provided.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:data = response.read(2 * 1024**2)
    import hashlib
    actual = hashlib.sha256(data).hexdigest()
    if actual == ORIGINAL_SHA:
        source = data.decode(); needle = 'list($cn,$y,$nn)=parse_type($T);'
        if source.count(needle) != 1:raise RuntimeError('Pinned adaptation anchor mismatch')
        source = source.replace(needle, needle + 'if(getenv("MATRIXONE_ADAPTER")==="1"&&stripos(connection()->server_info,"MatrixOne")!==false){$cn=strtolower($cn);}')
        data = source.encode()
    elif actual != ADAPTED_SHA:
        raise RuntimeError('Official or exact adapted Adminer release required')
    if hashlib.sha256(data).hexdigest() != ADAPTED_SHA:raise RuntimeError('Adaptation digest mismatch')
    private_file(app / 'index.php', data)


def main():
    import pymysql
    from bs4 import BeautifulSoup
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=os.getenv('MO_PHP_BINARY') or None)
    parser.add_argument('--release-file', type=Path, default=os.getenv('MO_ADMINER_RELEASE_FILE') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('adminer-' + uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:parser.error('Minimum disk admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_adminer_' + uuid.uuid4().hex[:16]; private = runtime_root() / schema; private.mkdir(parents=True, mode=0o700)
    report = {'app': 'vrana/adminer', 'version': 'v6.1.2', 'schema': schema, 'passed': False, 'checks': [],
              'native_runtime_attempted': False, 'official_release_sha256': ORIGINAL_SHA, 'adapted_release_sha256': ADAPTED_SHA,
              'source_edits': ['actual MatrixOne parsed type-name lowercase only'], 'native_driver': 'PDO_MySQL',
              'application_has_no_internal_migration_runner': True, 'all_fixture_DDL_and_DML_through_native_HTTP': True,
              'existing_databases_modified': False, 'min_free_mib': args.min_free_mib,
              'limitations': ['other database drivers/plugins/full privilege management/populated schema changes unverified']}
    owned = Processes(private, report); stage = 'admission'
    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:raise AssertionError(name)
    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free < args.min_free_mib * 1024**2:
            raise RuntimeError('Pinned PHP SDK and disk headroom required')
        php = args.binary.resolve(); check('pinned_FrankenPHP', digest(php) == PHP_SHA)
        app = private / 'app'; app.mkdir(mode=0o700); package(args.release_file, app)
        cfg = connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()'); report['server_version'], report['runtime_git_version'] = q.fetchone()
                check('actual_matrixone', 'MatrixOne' in report['server_version']); q.execute('CREATE DATABASE `' + schema + '` CHARACTER SET utf8mb4')
        cfg['database'] = schema
        def sql(query, params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:q.execute(query, params); return q.fetchall()
        web_port = port(); base = 'http://127.0.0.1:' + str(web_port)
        owner, anonymous, wrong = Session(base), Session(base), Session(base)
        ini = private / 'php-ini'; ini.mkdir(mode=0o700); sessions = private / 'sessions'; sessions.mkdir(mode=0o700)
        private_file(ini / 'local.ini', 'session.save_path=' + json.dumps(str(sessions)) + '\n')
        env = {**os.environ, 'MATRIXONE_ADAPTER': '1', 'PHP_INI_SCAN_DIR': str(ini),
               'XDG_CONFIG_HOME': str(private / 'config'), 'XDG_DATA_HOME': str(private / 'data'),
               'GOMAXPROCS': '2', 'GOMEMLIMIT': '512MiB', 'CADDY_ADMIN': 'off'}
        def start():
            p = owned.start([str(php), 'php-server', '--root', str(app), '--listen', '127.0.0.1:' + str(web_port)], app, env, 'adminer')
            report['native_runtime_attempted'] = True; deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if p.poll() is not None:raise RuntimeError('Native Adminer startup failed; private log retained')
                try:
                    if anonymous.request('GET', '/?ext=pdo', timeout=2).status_code == 200:return p
                except (OSError, urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native Adminer startup')
        proc = start(); stage = 'native_authentication'
        host = cfg['host']; host = '[' + host + ']' if ':' in host else host
        server = host + ':' + str(cfg['port'])
        def params(**extra):return '/?' + urllib.parse.urlencode({'server': server, 'username': cfg['user'], 'db': schema, 'ext': 'pdo', **extra})
        def soup(response):return BeautifulSoup(response.text, 'html.parser')
        def hidden(form):return {node['name']: node.get('value', '') for node in form.select('input[type=hidden][name]')}
        def login(client, password):
            response = client.request('GET', '/?ext=pdo'); page = soup(response); field = page.select_one('input[name="auth[username]"]')
            if field is None:raise AssertionError('native_login_form_required')
            data = hidden(field.find_parent('form')); data.update({'auth[driver]': 'server', 'auth[server]': server,
                'auth[username]': cfg['user'], 'auth[password]': password, 'auth[db]': schema})
            response = client.request('POST', '/?ext=pdo', data=data); return response, soup(response)
        response, page = login(wrong, 'incorrect-' + uuid.uuid4().hex)
        check('wrong_database_password_denied', page.select_one('input[name="auth[username]"]') is not None and bool(page.select('.error')))
        response, page = login(owner, cfg['password'])
        check('native_PDO_password_cookie_login', response.status_code == 200 and page.select_one('input[name="auth[username]"]') is None and not page.select('.error'))
        def sql_form():
            path = params(sql=''); response = owner.request('GET', path); page = soup(response); field = page.select_one('textarea[name=query]')
            if field is None:raise AssertionError('native_SQL_form')
            return path, hidden(field.find_parent('form'))
        def query(statement, expected_error=False, invalid_csrf=False):
            path, data = sql_form(); data.update(query=statement, limit='100', execute='Execute')
            if invalid_csrf:data['token'] = 'deliberately-invalid-token'
            response = owner.request('POST', path, data=data, timeout=90); page = soup(response)
            status_ok = response.status_code == 200 or (invalid_csrf and expected_error and response.status_code == 403
                and 'Invalid CSRF token' in page.get_text())
            if not status_ok or bool(page.select('.error')) != expected_error:
                report['query_HTTP_status'] = response.status_code
                report['query_error_elements'] = len(page.select('.error'))
                report['query_login_form_present'] = page.select_one('input[name="auth[username]"]') is not None
                private_file(private / ('failed-native-query-' + str(len(report['checks'])) + '.html'), response.content)
                raise AssertionError('native_SQL_status_and_error_gate')
            return response, page
        stage = 'native_SQL_DDL'
        query("CREATE TABLE contacts (id BIGINT PRIMARY KEY,name VARCHAR(255) NOT NULL,amount DECIMAL(12,2) NOT NULL,payload VARBINARY(255)); CREATE TABLE notes (id BIGINT PRIMARY KEY,contact_id BIGINT NOT NULL,note VARCHAR(255),FOREIGN KEY(contact_id) REFERENCES contacts(id)); CREATE TABLE typed (id BIGINT PRIMARY KEY,choice ENUM('MiXeD','ABC') NOT NULL,nullable_text VARCHAR(64),number BIGINT)")
        check('native_SQL_three_tables_created', {r[0] for r in sql('SHOW TABLES')} == {'contacts', 'notes', 'typed'})
        query("INSERT INTO contacts VALUES (1,'MatrixOne contact 中文 😀𠮷',1234.56,X'00FF4100'); INSERT INTO notes VALUES (1,1,'关联备注 中文 😀𠮷'); INSERT INTO typed VALUES (1,'MiXeD',NULL,-42)")
        stage = 'native_edit_forms'
        def edit(table, fields, identity=None):
            options = {'edit': table}
            if identity is not None:options['where[id]'] = str(identity)
            path = params(**options); response = owner.request('GET', path); page = soup(response)
            field = page.select_one('input[name="fields[id]"]')
            if field is None:raise AssertionError('native_insert_edit_form')
            data = hidden(field.find_parent('form'))
            for key, value in fields.items():data['fields[' + key + ']'] = str(value); data['function[' + key + ']'] = ''
            data['save'] = '1'; response = owner.request('POST', path, data=data, timeout=60); page = soup(response)
            if response.status_code != 200 or page.select('.error') or not page.select('.message'):raise AssertionError('native_edit_form_success')
            return page
        edit('contacts', {'id': 1, 'name': 'MatrixOne edited 中文 😀𠮷', 'amount': '2345.67', 'payload': '00FF4100'}, 1)
        check('native_edit_Unicode_decimal_binary', sql('SELECT name,amount,HEX(payload) FROM contacts WHERE id=1') == (('MatrixOne edited 中文 😀𠮷', Decimal('2345.67'), '00FF4100'),))
        edit('notes', {'id': 2, 'contact_id': 1, 'note': 'Native insert 中文 😀𠮷'})
        check('native_insert_form_and_owner_relation', sql('SELECT n.note,c.id FROM notes n JOIN contacts c ON c.id=n.contact_id WHERE n.id=2') == (('Native insert 中文 😀𠮷', 1),))
        response = owner.request('GET', params(edit='typed', **{'where[id]': '1'})); page = soup(response)
        values = [node.get_text(' ', strip=True) for node in page.select('label')] + [node.get('value', '') for node in page.select('input[name*=choice]')]
        check('native_ENUM_literal_case_preserved', 'MiXeD' in values and 'ABC' in values)
        query('START TRANSACTION; UPDATE contacts SET amount=9999.99 WHERE id=1; ROLLBACK; SELECT amount FROM contacts WHERE id=1')
        check('native_console_rollback_exact', sql('SELECT amount FROM contacts WHERE id=1') == ((Decimal('2345.67'),),))
        query("INSERT INTO notes VALUES (999,999,'invalid FK')", expected_error=True)
        check('native_FK_rejection_zero_row', sql('SELECT COUNT(*) FROM notes WHERE id=999') == ((0,),))
        query('UPDATE contacts SET amount=8888.88 WHERE id=1', expected_error=True, invalid_csrf=True)
        check('invalid_CSRF_write_denied_no_change', sql('SELECT amount FROM contacts WHERE id=1') == ((Decimal('2345.67'),),))
        check('native_ENUM_NULL_signed_integer_exact', sql('SELECT choice,nullable_text,number FROM typed WHERE id=1') == (('MiXeD', None, -42),))
        response = anonymous.request('GET', params(sql='SELECT * FROM contacts'))
        check('anonymous_SQL_requires_login', soup(response).select_one('input[name="auth[username]"]') is not None)
        def readback(label):
            response = owner.request('GET', params(select='contacts')); page = soup(response); text = page.get_text(' ', strip=True)
            check(label + '_native_browse_grid', response.status_code == 200 and not page.select('.error') and 'MatrixOne edited 中文 😀𠮷' in text and '2345.67' in text)
            path, data = sql_form(); data.update(query='SELECT id,name,amount,HEX(payload) AS bytes_hex FROM contacts WHERE id=1', export='Export', format='csv', output='file')
            response = owner.request('POST', path, data=data); rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
            check(label + '_native_CSV_exact', response.status_code == 200 and rows == [['id','name','amount','bytes_hex'],['1','MatrixOne edited 中文 😀𠮷','2345.67','00FF4100']])
        readback('before_restart'); before = sql('SELECT id,name,amount,HEX(payload) FROM contacts')
        stage = 'native_restart'; old_pid = proc.pid; owned.stop(proc); proc = start(); check('real_PHP_process_restart', proc.pid != old_pid)
        readback('original_cookie_after_restart'); check('SQL_original_values_after_restart', before == sql('SELECT id,name,amount,HEX(payload) FROM contacts'))
        check('post_trigger_SQL_health', sql('SELECT 1') == ((1,),)); report['passed'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, failed_stage=stage)
        if isinstance(exc, AssertionError):report['failed_check'] = str(exc)
    finally:owned.close()
    return finish(out, report, 'adminer-native')


if __name__ == '__main__':raise SystemExit(main())
