"""Fresh pinned Huginn Rails migrations, native seed, asynchronous workflow and restart."""
import argparse
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import urllib.error
import uuid

from huginn_runtime import COMMIT, prepare
from native_common import runtime_root, Client, Processes, connection_config, finish, port, private_file

ROOT = Path(__file__).resolve().parent


class Fields(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.values = {}; self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('name'):
            self.values[attrs['name']] = attrs.get('value', '')


def scenario(secret):
    return {'schema_version': 1, 'name': 'MatrixOne 原生本地工作流 😀𠮷',
            'description': 'Isolated local Webhook to Formatter regression', 'source_url': False,
            'guid': uuid.uuid4().hex, 'tag_fg_color': '#ffffff', 'tag_bg_color': '#336699',
            'agents': [
                {'type': 'Agents::WebhookAgent', 'name': 'MatrixOne 原生接收 😀', 'disabled': False,
                 'guid': uuid.uuid4().hex, 'keep_events_for': 0, 'propagate_immediately': False,
                 'options': {'secret': secret, 'expected_receive_period_in_days': 1, 'payload_path': '$'}},
                {'type': 'Agents::EventFormattingAgent', 'name': 'MatrixOne 原生转换 😀', 'disabled': False,
                 'guid': uuid.uuid4().hex, 'keep_events_for': 0, 'propagate_immediately': False,
                 'options': {'mode': 'clean', 'instructions': {'original_text': '{{text}}', 'trace': '{{trace}}',
                             'message': '处理结果 {{text}}', 'integer': '{{integer}}'}}}],
            'links': [{'source': 0, 'receiver': 1}], 'control_links': []}


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-config', type=Path, default=os.getenv('MO_HUGINN_RUNTIME_CONFIG') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('huginn-' + uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:
        parser.error('Minimum disk admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_huginn_' + uuid.uuid4().hex[:16]
    private = runtime_root() / schema; private.mkdir(parents=True, mode=0o700)
    report = {'app': 'huginn/huginn', 'commit': COMMIT, 'schema': schema, 'passed': False, 'checks': [],
              'native_runtime_attempted': False, 'manual_users_or_migration_stamps': False,
              'existing_databases_modified': False, 'min_free_mib': args.min_free_mib,
              'prepared_dependency_SDK_required': True, 'full_load_validation': False,
              'limitations': ['CHANGE charset/collation attributes and ALTER DATABASE charset switch omitted',
                              'case-insensitive collation equivalence and populated upgrades unverified',
                              'forced process stop does not certify graceful shutdown']}
    owned = Processes(private, report); stage = 'admission'

    def check(name, valid):
        report['checks'].append({'name': name, 'passed': bool(valid)})
        if not valid:
            raise AssertionError(name)

    try:
        if not args.runtime_config:
            raise RuntimeError('Prepared runtime config is required')
        if shutil.disk_usage(runtime_root()).free < args.min_free_mib * 1024**2:
            raise RuntimeError('Insufficient configured disk headroom')
        stage = 'source_and_dependency_SDK'
        app, paths, runtime_env, count = prepare(args.runtime_config, private)
        report['verified_source_blobs'] = count
        cfg = connection_config(); test_schema = schema + '_test'
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(), git_version()')
                report['server_version'], report['runtime_git_version'] = q.fetchone()
                check('actual_matrixone', 'MatrixOne' in report['server_version'])
                q.execute('SHOW DATABASES')
                check('both_native_databases_are_new', not {schema, test_schema}.intersection(r[0] for r in q.fetchall()))
        cfg['database'] = schema
        credentials = {'admin_user': 'mo_admin', 'admin_email': 'mo-admin@huginn.invalid',
                       'admin_password': secrets.token_urlsafe(24), 'webhook_secret': secrets.token_urlsafe(24),
                       'app_secret_token': secrets.token_hex(64), 'outsider_user': 'mo_other_' + uuid.uuid4().hex[:8],
                       'outsider_email': 'mo-other-' + uuid.uuid4().hex[:8] + '@huginn.invalid',
                       'outsider_password': secrets.token_urlsafe(24)}
        private_file(private / 'credentials.json', json.dumps(credentials))
        scenario_path = private / 'native-scenario.json'
        private_file(scenario_path, json.dumps(scenario(credentials['webhook_secret']), ensure_ascii=False))
        env = {**os.environ, **runtime_env, 'APP_SECRET_TOKEN': credentials['app_secret_token'],
               'DATABASE_ADAPTER': 'mysql2', 'DATABASE_ENCODING': 'utf8mb4', 'DATABASE_NAME': schema,
               'TEST_DATABASE_NAME': test_schema, 'DATABASE_POOL': '20', 'DATABASE_USERNAME': cfg['user'],
               'DATABASE_PASSWORD': cfg['password'], 'DATABASE_HOST': cfg['host'], 'DATABASE_PORT': str(cfg['port']),
               'RAILS_ENV': 'production', 'RAILS_LOG_TO_STDOUT': 'true', 'RAILS_SERVE_STATIC_FILES': 'true',
               'FORCE_SSL': 'false', 'SEED_EMAIL': credentials['admin_email'], 'SEED_USERNAME': credentials['admin_user'],
               'SEED_PASSWORD': credentials['admin_password'], 'DEFAULT_SCENARIO_FILE': str(scenario_path),
               'IMPORT_DEFAULT_SCENARIO_FOR_ALL_USERS': 'false', 'INVITATION_CODE': 'mo-regression-only',
               'SMTP_SERVER': '127.0.0.1', 'SMTP_PORT': '9', 'SMTP_DOMAIN': 'huginn.invalid',
               'SMTP_AUTHENTICATION': 'none', 'SMTP_ENABLE_STARTTLS_AUTO': 'false'}

        def task(label, command, timeout=240):
            p = owned.start(command, app, env, label)
            try:
                code = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                owned.stop(p); raise
            report.setdefault('tasks', []).append({'name': label, 'exit_code': code})
            check(label, code == 0)

        task('pinned_ruby_version', [str(paths['ruby_binary']), '-e', 'abort "Ruby version mismatch" unless RUBY_VERSION == "3.4.11"'])
        task('locked_bundle_check', [str(paths['ruby_binary']), str(paths['bundle_binary']), 'check'])
        stage = 'native_initialization'; report['native_runtime_attempted'] = True
        for native_task in ['db:create', 'db:migrate', 'db:seed']:
            task('native_' + native_task, [str(paths['ruby_binary']), str(paths['bundle_binary']), 'exec', 'rails', native_task])

        def sql(query, params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:
                    q.execute(query, params); return q.fetchall()

        migration_versions = [p.name.split('_', 1)[0] for p in (app / 'db/migrate').glob('*.rb')]
        observed = [str(r[0]) for r in sql('SELECT version FROM schema_migrations ORDER BY version')]
        check('native_all_73_migration_versions', len(observed) == 73 and sorted(observed) == sorted(migration_versions))
        users = sql('SELECT id,username,email,admin,LENGTH(encrypted_password) FROM users WHERE email=%s', (credentials['admin_email'],))
        check('native_seed_admin_password_and_identity', len(users) == 1 and users[0][1:] == (credentials['admin_user'], credentials['admin_email'], 1, 60)); uid = users[0][0]
        agents = sql('SELECT id,type,user_id FROM agents WHERE user_id=%s ORDER BY id', (uid,))
        check('native_import_two_owned_agents', len(agents) == 2 and all(x[2] == uid for x in agents))
        source = next(x[0] for x in agents if x[1] == 'Agents::WebhookAgent')
        target = next(x[0] for x in agents if x[1] == 'Agents::EventFormattingAgent')
        check('native_scenario_receiver_link', sql('SELECT source_id,receiver_id FROM links WHERE source_id=%s AND receiver_id=%s', (source, target)) == ((source, target),))
        web_port = port(); base = 'http://127.0.0.1:' + str(web_port)
        env.update(IP='127.0.0.1', PORT=str(web_port), DOMAIN='127.0.0.1:' + str(web_port), WEB_CONCURRENCY='2', RAILS_MAX_THREADS='1')
        admin, anonymous, outsider = Client(base), Client(base), Client(base)

        def start():
            processes = [owned.start([str(paths['ruby_binary']), str(paths['bundle_binary']), 'exec', 'puma', '-C', 'config/puma.rb'], app, env, 'web'),
                         owned.start([str(paths['ruby_binary']), str(paths['bundle_binary']), 'exec', 'rails', 'runner', 'bin/threaded.rb'], app, env, 'jobs')]
            deadline = time.monotonic() + 50
            while time.monotonic() < deadline:
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError('Native process exited; private logs retained')
                try:
                    if anonymous.request('GET', '/users/sign_in', timeout=2).status_code == 200:
                        return processes
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.25)
            raise TimeoutError('Native Puma startup')

        def login(client, password, username=None):
            response = client.request('GET', '/users/sign_in'); form = Fields(response.text).values
            check('native_login_CSRF_' + str(len(report['checks'])), bool(form.get('authenticity_token')))
            form.update({'user[login]': username or credentials['admin_user'], 'user[password]': password, 'user[remember_me]': '0'})
            return client.request('POST', '/users/sign_in', data=form)

        stage = 'native_authentication'; processes = start()
        response = anonymous.request('GET', '/agents')
        check('anonymous_management_login_required', response.status_code == 302 and '/users/sign_in' in response.headers.get('Location', ''))
        response = login(anonymous, 'incorrect-' + uuid.uuid4().hex)
        denied = anonymous.request('GET', '/agents')
        check('wrong_password_denied', response.status_code in {200, 401, 422} and denied.status_code == 302 and '/users/sign_in' in denied.headers.get('Location', ''))
        check('native_password_login', login(admin, credentials['admin_password']).status_code == 302)
        response = admin.request('GET', '/agents')
        check('native_authenticated_agent_list', response.status_code == 200 and 'MatrixOne' in response.text)
        stage = 'native_webhook'
        path = f'/users/{uid}/web_requests/{source}/'
        before = sql('SELECT COUNT(*) FROM events')[0][0]
        response = anonymous.request('POST', path + 'wrong-secret', json_data={'text': 'forbidden'})
        check('wrong_webhook_secret_denied_zero_writes', response.status_code == 401 and sql('SELECT COUNT(*) FROM events')[0][0] == before)
        trace = 'hugreg' + uuid.uuid4().hex[:12]
        payload = {'text': '原生事件 中文 😀𠮷', 'trace': trace, 'integer': 9007199254740991,
                   'nested': [True, False, {'value': '精确', 'nullable': None}]}
        response = anonymous.request('POST', path + credentials['webhook_secret'], json_data=payload)
        check('native_webhook_ACK_201', response.status_code == 201)
        stage = 'native_async_workflow'; deadline = time.monotonic() + 130; selected = []
        while time.monotonic() < deadline:
            rows = sql('SELECT id,agent_id,user_id,payload FROM events WHERE agent_id IN (%s,%s) ORDER BY id', (source, target))
            selected = [(r[0], r[1], r[2], json.loads(r[3])) for r in rows if json.loads(r[3]).get('trace') == trace]
            if len(selected) == 2:
                break
            if any(p.poll() is not None for p in processes):
                raise RuntimeError('Native background worker exited')
            time.sleep(1)
        expected = {'original_text': payload['text'], 'trace': trace, 'message': '处理结果 ' + payload['text'], 'integer': str(payload['integer'])}
        check('native_background_formatter_exact_output', len(selected) == 2 and all(r[2] == uid for r in selected) and
              next(r[3] for r in selected if r[1] == source) == payload and next(r[3] for r in selected if r[1] == target) == expected)
        event_ids = [r[0] for r in selected]
        def native_events(name):
            response = admin.request('GET', '/events.json'); events = response.json()
            check(name, response.status_code == 200 and all(any(x.get('id') == item[0] and x.get('agent_id') == item[1] and
                  x.get('user_id') == uid and x.get('payload') == item[3] for x in events) for item in selected))
        native_events('native_authenticated_JSON_exact_events')
        stage = 'native_outsider_signup'; response = outsider.request('GET', '/users/sign_up'); form = Fields(response.text).values
        check('native_signup_CSRF', response.status_code == 200 and bool(form.get('authenticity_token')))
        form.update({'user[username]': credentials['outsider_user'], 'user[email]': credentials['outsider_email'],
                     'user[password]': credentials['outsider_password'], 'user[password_confirmation]': credentials['outsider_password'],
                     'user[invitation_code]': 'mo-regression-only'})
        check('native_ordinary_user_signup', outsider.request('POST', '/users', data=form).status_code == 302)
        rows = sql('SELECT id,admin FROM users WHERE username=%s', (credentials['outsider_user'],))
        check('native_ordinary_user_not_admin', len(rows) == 1 and rows[0][1] == 0); oid = rows[0][0]
        check('other_user_agent_denied', outsider.request('GET', f'/agents/{source}').status_code == 404)
        response = outsider.request('GET', '/events.json')
        check('other_user_events_exclude_owner', response.status_code == 200 and all(x.get('id') not in event_ids for x in response.json()))
        before = sql('SELECT COUNT(*) FROM events')[0][0]
        response = anonymous.request('POST', f'/users/{oid}/web_requests/{source}/' + credentials['webhook_secret'], json_data={'text': 'forbidden_owner'})
        check('wrong_owner_webhook_denied_zero_writes', response.status_code == 404 and sql('SELECT COUNT(*) FROM events')[0][0] == before)
        stage = 'native_CSRF'; response = admin.request('GET', f'/agents/{source}/edit'); form = Fields(response.text).values
        check('native_edit_form_CSRF', response.status_code == 200 and bool(form.get('authenticity_token')))
        old_name = sql('SELECT name FROM agents WHERE id=%s', (source,))[0][0]
        form.update({'authenticity_token': 'invalid-CSRF', '_method': 'patch', 'agent[name]': 'Forbidden change'})
        response = admin.request('POST', f'/agents/{source}', data=form)
        check('invalid_CSRF_denied_zero_metadata_change', response.status_code == 422 and sql('SELECT name FROM agents WHERE id=%s', (source,))[0][0] == old_name)
        stage = 'native_restart'
        before = sql('SELECT id,agent_id,user_id,payload FROM events WHERE id IN (%s,%s) ORDER BY id', tuple(event_ids))
        old_pids = [p.pid for p in processes]
        for process in reversed(processes):
            owned.stop(process, timeout=55)
        processes = start()
        check('real_Puma_and_AgentRunner_restart', old_pids != [p.pid for p in processes])
        check('SQL_exact_events_and_owner_links_after_restart', before == sql('SELECT id,agent_id,user_id,payload FROM events WHERE id IN (%s,%s) ORDER BY id', tuple(event_ids)))
        native_events('native_cookie_and_JSON_survive_restart')
        check('native_worker_alive_after_restart', all(p.poll() is None for p in processes))
        check('post_trigger_SQL_health', sql('SELECT 1') == ((1,),))
        report['passed'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, failed_stage=stage)
        if isinstance(exc, AssertionError):
            report['failed_check'] = str(exc)
    finally:
        owned.close()
    return finish(out, report, 'huginn-native')


if __name__ == '__main__':
    raise SystemExit(main())
