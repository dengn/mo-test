"""Pinned phpMyAdmin native cookie/CSRF SQL console, export and process restart."""
import argparse
import csv
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from run_baikal import Session
from native_common import Processes, connection_config, digest, finish, port, private_file, runtime_root

ROOT = Path(__file__).resolve().parent
PHP_SHA = '9f738981bbcce1906329b751e57411171d5db0629ee00da0a41514f4a3d2f280'
URL = 'https://files.phpmyadmin.net/phpMyAdmin/5.2.3/phpMyAdmin-5.2.3-all-languages.tar.xz'
ARCHIVE_SHA = '57881348297c4412f86c410547cf76b4d8a236574dd2c6b7d6a2beebe7fc44e3'


def release(provided, private):
    archive = provided
    if not archive:
        archive = private / 'official.tar.xz'
        with urllib.request.urlopen(URL, timeout=90) as response:
            data = response.read(10 * 1024**2 + 1)
        private_file(archive, data)
    if digest(archive) != ARCHIVE_SHA:
        raise RuntimeError('Official phpMyAdmin archive digest mismatch')
    target = private / 'app'; target.mkdir(mode=0o700)
    count = 0; total = 0; prefix = 'phpMyAdmin-5.2.3-all-languages/'
    with tarfile.open(archive, 'r:xz') as tar:
        for member in tar:
            if member.isdir():continue
            if not member.isfile() or not member.name.startswith(prefix):
                raise RuntimeError('Unexpected official archive entry')
            relative = Path(member.name[len(prefix):])
            if relative.is_absolute() or '..' in relative.parts:
                raise RuntimeError('Unsafe official release path')
            total += member.size
            if total > 100 * 1024**2:raise RuntimeError('Expanded release exceeds bound')
            destination = target / relative; destination.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, destination.open('xb') as out:
                shutil.copyfileobj(source, out)
            destination.chmod(0o644); count += 1
    if count != 4314:raise RuntimeError('Pinned release file count mismatch')
    manifest = json.loads((ROOT / 'fixtures/phpmyadmin/adaptation-manifest.json').read_text())
    for entry in manifest['files']:
        source = target / entry['path']; adapted = ROOT / 'fixtures/phpmyadmin/adapted' / entry['path']
        if digest(source) != entry['original_sha256'] or digest(adapted) != entry['adapted_sha256']:
            raise RuntimeError('Pinned adaptation source mismatch')
        source.write_bytes(adapted.read_bytes())
    return target, count


def main():
    import pymysql
    from bs4 import BeautifulSoup
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=os.getenv('MO_PHP_BINARY') or None)
    parser.add_argument('--release-archive', type=Path, default=os.getenv('MO_PHPMYADMIN_RELEASE_ARCHIVE') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('phpmyadmin-' + uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:parser.error('Minimum disk admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_phpmyadmin_' + uuid.uuid4().hex[:16]; private = runtime_root() / schema; private.mkdir(parents=True, mode=0o700)
    report = {'app': 'phpmyadmin/phpmyadmin', 'version': '5.2.3', 'commit': '962857e4f63d42e38f11ff4d63f5e722018add76',
              'schema': schema, 'passed': False, 'checks': [], 'native_runtime_attempted': False,
              'official_archive_sha256': ARCHIVE_SHA, 'existing_databases_modified': False,
              'optional_configuration_storage_unverified': True, 'all_fixture_DDL_and_DML_through_native_HTTP': True,
              'source_edits': ['SHOW COLLATION metadata', 'foreign-key boolean case', 'role without host', 'avoid redundant session SET around native transaction'],
              'min_free_mib': args.min_free_mib,
              'limitations': ['full schema alteration/privilege management/import/plugins/populated upgrade unverified']}
    owned = Processes(private, report); stage = 'admission'
    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:raise AssertionError(name)
    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free < args.min_free_mib * 1024**2 + 80 * 1024**2:
            raise RuntimeError('Pinned PHP SDK and fresh release headroom required')
        php = args.binary.resolve(); check('pinned_FrankenPHP', digest(php) == PHP_SHA)
        app, count = release(args.release_archive, private); report['verified_release_files'] = count
        check('fresh_official_release_without_old_config', not (app / 'config.inc.php').exists())
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
        (app / 'tmp').mkdir(exist_ok=True)
        config = "<?php\n$cfg['blowfish_secret']=" + json.dumps(secrets.token_hex(16)) + ";\n$i=1;\n"
        for key, value in {'auth_type':'cookie', 'host':cfg['host'], 'port':cfg['port'], 'AllowNoPassword':False}.items():
            config += "$cfg['Servers'][$i][" + json.dumps(key) + '] = ' + (str(value).lower() if isinstance(value, (bool,int)) else json.dumps(value)) + ';\n'
        config += "$cfg['DefaultLang']='en';\n$cfg['TempDir']=__DIR__.'/tmp';\n$cfg['PmaAbsoluteUri']=" + json.dumps(base + '/') + ';\n'
        private_file(app / 'config.inc.php', config)
        ini = private / 'php-ini'; ini.mkdir(mode=0o700); sessions = private / 'sessions'; sessions.mkdir(mode=0o700)
        private_file(ini / 'local.ini', 'session.save_path=' + json.dumps(str(sessions)) + '\n')
        caddy = private / 'Caddyfile'
        private_file(caddy, '{\n admin off\n auto_https off\n frankenphp {\n  num_threads 4\n }\n}\n' + base + ' {\n root * ' + str(app) + '\n @blocked path /config.inc.php /vendor/* /libraries/* /tmp/* /setup/* /sql/* /examples/* /test/* /tests/*\n respond @blocked 403\n php_server\n}\n')
        env = {**os.environ, 'MATRIXONE_ADAPTER':'1', 'PHP_INI_SCAN_DIR':str(ini), 'GOMAXPROCS':'2', 'GOMEMLIMIT':'512MiB',
               'XDG_CONFIG_HOME':str(private/'config'), 'XDG_DATA_HOME':str(private/'data')}
        def start():
            process = owned.start([str(php), 'run', '--config', str(caddy)], app, env, 'phpmyadmin')
            report['native_runtime_attempted'] = True; deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:raise RuntimeError('Native phpMyAdmin startup failed; private log retained')
                try:
                    if anonymous.request('GET', '/', timeout=2).status_code == 200:return process
                except (OSError, urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native phpMyAdmin startup')
        proc = start(); stage = 'native_authentication'
        def soup(response):return BeautifulSoup(response.text, 'html.parser')
        def hidden(form):return {n['name']:n.get('value','') for n in form.select('input[type=hidden][name]')}
        def action(form):
            parsed = urllib.parse.urlsplit(urllib.parse.urljoin(base+'/', form.get('action','')))
            if (parsed.scheme, parsed.netloc) != ('http', '127.0.0.1:'+str(web_port)):raise RuntimeError('Native form must target this owned app')
            return parsed.path + ('?' + parsed.query if parsed.query else '')
        def login(client, password):
            page = soup(client.request('GET','/')); field = page.select_one('input[name=pma_username]')
            if field is None:raise AssertionError('native_login_form_required')
            form = field.find_parent('form'); data = hidden(form); data.update(pma_username=cfg['user'],pma_password=password)
            response = client.request('POST', action(form), data=data); return response,soup(response)
        response,page = login(wrong, 'incorrect-'+uuid.uuid4().hex)
        check('wrong_database_password_denied', page.select_one('input[name=pma_username]') is not None and bool(page.select('.alert-danger')))
        response,page = login(owner,cfg['password'])
        check('native_password_cookie_login', response.status_code == 200 and page.select_one('input[name=pma_username]') is None)
        check('private_configuration_not_served', anonymous.request('GET','/config.inc.php').status_code == 403)
        def sql_form():
            response = owner.request('GET','/index.php?'+urllib.parse.urlencode({'route':'/database/sql','db':schema,'server':1}))
            form = soup(response).select_one('#sqlqueryform')
            if form is None:raise AssertionError('native_SQL_form_required')
            data = hidden(form); data.update(SQL='Go',sql_delimiter=';',server=1,fk_checks=1)
            return action(form),data
        def query(statement, expected_error=False, invalid_csrf=False):
            path,data = sql_form(); data.update(sql_query=statement,ajax_request=1)
            if invalid_csrf:data['token']='deliberately-invalid-csrf'
            response = owner.request('POST',path,data=data,timeout=90); result = response.json()
            if response.status_code != 200 or (result.get('success') is True) == expected_error:
                report['query_HTTP_status']=response.status_code; report['query_native_success']=result.get('success')
                private_file(private/('failed-native-query-'+str(len(report['checks']))+'.json'),response.content)
                raise AssertionError('native_SQL_success_and_error_gate')
            return result
        stage = 'native_SQL_DDL'
        query('CREATE TABLE contacts (id BIGINT PRIMARY KEY,name VARCHAR(255) NOT NULL,amount DECIMAL(12,2) NOT NULL,payload VARBINARY(255)); CREATE TABLE notes (id BIGINT PRIMARY KEY,contact_id BIGINT NOT NULL,note VARCHAR(255),FOREIGN KEY(contact_id) REFERENCES contacts(id)); CREATE TABLE typed (id BIGINT PRIMARY KEY,choice ENUM(\'MiXeD\',\'ABC\') NOT NULL,nullable_text VARCHAR(64),number BIGINT)')
        check('native_SQL_three_tables_created',{r[0] for r in sql('SHOW TABLES')} == {'contacts','notes','typed'})
        query("INSERT INTO contacts VALUES(1,'MatrixOne contact 中文 😀𠮷',1234.56,X'00FF4100'); INSERT INTO notes VALUES(1,1,'关联备注 中文 😀𠮷'); INSERT INTO typed VALUES(1,'MiXeD',NULL,-42)")
        check('native_insert_values_and_FK_relation',sql('SELECT n.note,c.name FROM notes n JOIN contacts c ON c.id=n.contact_id') == (('关联备注 中文 😀𠮷','MatrixOne contact 中文 😀𠮷'),))
        query('UPDATE contacts SET amount=2345.67 WHERE id=1')
        check('native_update_decimal_exact',sql('SELECT amount FROM contacts WHERE id=1') == ((Decimal('2345.67'),),))
        query('START TRANSACTION; UPDATE contacts SET amount=9999.99 WHERE id=1; ROLLBACK;')
        check('native_transaction_rollback_exact',sql('SELECT amount FROM contacts WHERE id=1') == ((Decimal('2345.67'),),))
        query("INSERT INTO notes VALUES(999,999,'invalid FK')",expected_error=True)
        check('native_FK_rejection_zero_row',sql('SELECT COUNT(*) FROM notes WHERE id=999') == ((0,),))
        query('UPDATE contacts SET amount=8888.88 WHERE id=1',expected_error=True,invalid_csrf=True)
        check('invalid_CSRF_write_denied_no_change',sql('SELECT amount FROM contacts WHERE id=1') == ((Decimal('2345.67'),),))
        check('native_ENUM_NULL_signed_integer_exact',sql('SELECT choice,nullable_text,number FROM typed WHERE id=1') == (('MiXeD',None,-42),))
        response = anonymous.request('GET','/index.php?'+urllib.parse.urlencode({'route':'/sql','db':schema,'table':'contacts','sql_query':'SELECT * FROM contacts'}))
        check('anonymous_SQL_requires_login',soup(response).select_one('input[name=pma_username]') is not None)
        def readback(label):
            result = query('SELECT id,name,amount,HEX(payload) AS bytes_hex FROM contacts WHERE id=1')
            grids = [BeautifulSoup(v,'html.parser').select_one('table.table_results') for v in result.values() if isinstance(v,str)]
            grid = next((g for g in grids if g is not None),None)
            text = grid.get_text(' ',strip=True) if grid else ''
            check(label+'_native_result_grid_exact', all(value in text for value in ['MatrixOne contact 中文 😀𠮷','2345.67','00FF4100']))
            _,data = sql_form()
            data = {'token':data['token'],'server':1,'db':schema,'table':'contacts','export_type':'table','export_method':'custom','what':'csv','output_format':'sendit',
                    'filename_template':'matrixone_contacts','csv_separator':',','csv_enclosed':'"','csv_escaped':'"','csv_terminated':'AUTO','csv_null':'NULL',
                    'csv_columns':'yes','csv_structure_or_data':'data','charset_of_file':'utf-8','allrows':1,'sql_query':'SELECT id,name,amount,HEX(payload) AS bytes_hex FROM contacts WHERE id=1'}
            response = owner.request('POST','/index.php?route=/export',data=data,timeout=90)
            rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
            check(label+'_native_CSV_exact',response.status_code == 200 and rows == [['id','name','amount','bytes_hex'],['1','MatrixOne contact 中文 😀𠮷','2345.67','00FF4100']])
        readback('before_restart'); before = sql('SELECT id,name,amount,HEX(payload) FROM contacts')
        stage = 'native_restart'; old_pid=proc.pid; owned.stop(proc); proc=start(); check('real_PHP_process_restart',proc.pid != old_pid)
        readback('original_cookie_after_restart'); check('SQL_original_values_after_restart',before == sql('SELECT id,name,amount,HEX(payload) FROM contacts'))
        query('DELETE FROM notes WHERE id=1'); check('native_delete_and_zero_relation',sql('SELECT COUNT(*) FROM notes') == ((0,),))
        check('post_trigger_SQL_health',sql('SELECT 1') == ((1,),)); report['passed']=True
    except Exception as exc:
        report.update(error_type=type(exc).__name__,failed_stage=stage)
        if isinstance(exc,AssertionError):report['failed_check']=str(exc)
    finally:owned.close()
    return finish(out,report,'phpmyadmin-native')


if __name__ == '__main__':raise SystemExit(main())
