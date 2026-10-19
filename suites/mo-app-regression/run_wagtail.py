"""Native Wagtail migrations, page drafts/publishing, permissions and restart."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import urllib.error
import uuid

from bs4 import BeautifulSoup
from native_common import Client, Processes, connection_config, finish, port, private_file, runtime_root
from run_baikal import Session
from wagtail_runtime import prepare

ROOT = Path(__file__).resolve().parent


def fields(response, action=None):
    """Replay the real native form, including CSRF and revision concurrency fields."""
    document = BeautifulSoup(response.text, 'html.parser')
    forms = document.find_all('form')
    form = next((f for f in forms if f.find('input', attrs={'name': 'csrfmiddlewaretoken'})
                 and (action is None or f.get('action') in {action, '', None})), None)
    if response.status_code != 200 or form is None:
        raise AssertionError('native_form_missing')
    result = {}
    for element in form.find_all(['input', 'textarea', 'select']):
        name = element.get('name')
        if not name or element.has_attr('disabled'):
            continue
        if element.name == 'input':
            kind = element.get('type', '').lower()
            if kind in {'submit', 'button', 'file'} or (kind in {'checkbox', 'radio'} and not element.has_attr('checked')):
                continue
            result[name] = element.get('value', '')
        elif element.name == 'textarea':
            result[name] = element.get_text()
        else:
            options = element.find_all('option', selected=True) or element.find_all('option')[:1]
            result[name] = options[0].get('value', '') if options else ''
    return result


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-config', type=Path, default=os.getenv('MO_WAGTAIL_RUNTIME_CONFIG') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT/'artifacts'/('wagtail-'+uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:
        parser.error('Minimum disk admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_wagtail_'+uuid.uuid4().hex[:16]
    private = runtime_root()/schema; private.mkdir(mode=0o700)
    report = {'app': 'wagtail/wagtail', 'version': '8.0', 'schema': schema, 'passed': False,
              'checks': [], 'native_runtime_attempted': False, 'min_free_mib': args.min_free_mib,
              'existing_databases_modified': False, 'manual_SQL_users_or_migration_stamps': False,
              'observer_provisioning': 'Django create_user and native permission ORM in fixture command',
              'limitations': ['prepared dependencies only; full cold installation unverified',
                              'minimal HomePage fixture; browser/static UI, StreamField, uploads, workflows, search and load unverified',
                              'no SAVEPOINT; upgrade/downgrade and transaction nesting unverified',
                              'specific legacy permission CHECK replaced with stricter NOT NULL after verified backfill; general CHECK unverified',
                              '0086 correlated UPDATE uses native ORM row updates; original panic is not retested or claimed fixed']}
    owned = Processes(private, report); stage = 'admission'

    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)

    try:
        if not args.runtime_config or shutil.disk_usage(runtime_root()).free < args.min_free_mib*1024**2:
            raise RuntimeError('Prepared SDK config and runtime headroom required')
        stage = 'verified_SDK'; python, app, identity = prepare(args.runtime_config, private)
        report['SDK_identity'] = identity
        check('pinned_wheel_SDK_and_dependencies', identity['dependency_packages_verified'] == 41 and identity['dependency_files_verified'] == 10230)
        cfg = connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()'); report['server_version'], report['runtime_git_version'] = q.fetchone()
                check('actual_matrixone', 'MatrixOne' in report['server_version'])
                q.execute('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4')
        cfg['database'] = schema

        def sql(query, params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:
                    q.execute(query, params); return q.fetchall()

        credentials = {'secret_key': secrets.token_urlsafe(48), 'admin_password': 'Mo1-'+secrets.token_hex(12),
                       'observer_password': 'Mo1-'+secrets.token_hex(12)}
        private_file(private/'credentials.json', json.dumps(credentials))
        base = 'http://127.0.0.1:'+str(port())
        env = {**os.environ, 'MO_HOST': cfg['host'], 'MO_PORT': str(cfg['port']), 'MO_USER': cfg['user'],
               'MO_NATIVE_SCHEMA': schema, 'MO_NATIVE_BASE_URL': base, 'MO_NATIVE_SECRET_KEY': credentials['secret_key'],
               'MO_NATIVE_OBSERVER_PASSWORD': credentials['observer_password'], 'DJANGO_SETTINGS_MODULE': 'settings',
               'MO_NATIVE_SQL_ERROR_FILE': str(private/'sql-errors.private.jsonl'),
               'DJANGO_SUPERUSER_PASSWORD': credentials['admin_password'], 'PYTHONPATH': str(app),
               'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPYCACHEPREFIX': str(private/'pycache')}

        def task(label, arguments, timeout=900):
            process = owned.start([str(python), 'manage.py', *arguments], app, env, label)
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                owned.stop(process); raise
            check(label, code == 0)

        stage = 'native_migrations'; report['native_runtime_attempted'] = True
        check('fresh_schema_empty', sql('SHOW TABLES') == ())
        task('native_all_migrations', ['migrate', '--noinput'])
        task('native_migration_plan', ['showmigrations', '--plan'])
        plan = (private/'native_migration_plan-1.log').read_text(errors='replace')
        migration_count = sql('SELECT COUNT(*) FROM django_migrations')[0][0]
        report['native_migrations'] = migration_count; report['native_tables'] = len(sql('SHOW TABLES'))
        # Squashed migrations record their replaced predecessors as well. The
        # native execution plan has 185 nodes; the recorder contains 222 rows.
        check('all_native_migration_records_and_plan', '[ ]' not in plan and plan.count('[X]') == 185 and migration_count == 222)
        task('native_no_pending_migration_gate', ['migrate', '--check', '--noinput'])
        check('permission_backfill_has_no_nulls', sql('SELECT COUNT(*) FROM wagtailcore_grouppagepermission WHERE permission_id IS NULL') == ((0,),))
        stage = 'native_accounts'
        task('native_createsuperuser', ['createsuperuser', '--noinput', '--username', 'moadmin', '--email', 'admin@example.test'])
        observer = owned.start([str(python), 'create_observer.py'], app, env, 'observer-native-ORM')
        check('native_observer_create', observer.wait(timeout=120) == 0)
        users = sql('SELECT username,is_superuser,LENGTH(password) FROM auth_user ORDER BY username')
        check('native_two_password_hashes', tuple(x[:2] for x in users) == (('moadmin', 1), ('moobserver', 0)) and all(x[2] > 60 for x in users))
        check('observer_has_only_native_admin_access', sql('SELECT p.codename FROM auth_user u JOIN auth_user_user_permissions up ON up.user_id=u.id JOIN auth_permission p ON p.id=up.permission_id WHERE u.username=%s', ('moobserver',)) == (('access_admin',),))
        anonymous = Client(base); admin = Session(base); other = Session(base)

        def start():
            process = owned.start([str(python), '-m', 'gunicorn', 'wsgi:application', '--bind', base[7:],
                                   '--workers', '1', '--threads', '4', '--timeout', '120'], app, env, 'wagtail')
            deadline = time.monotonic()+120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Native Wagtail exited; private log retained')
                try:
                    if anonymous.request('GET', '/admin/login/', timeout=3).status_code == 200:
                        return process
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.2)
            raise TimeoutError('Native Wagtail startup')

        def save_private(response, label):
            private_file(private/(label+'-'+uuid.uuid4().hex+'.private.html'), response.content)

        def login(client, username, label):
            payload = fields(client.request('GET', '/admin/login/'))
            payload.update(username=username, password=credentials[label+'_password'])
            response = client.request('POST', '/admin/login/', data=payload, headers={'Referer': base+'/admin/login/'})
            save_private(response, label+'-login')
            check('native_'+label+'_password_session', response.status_code == 200 and '/login/' not in response.path)
            cookies = list(client.opener.handlers)
            for handler in cookies:
                if hasattr(handler, 'cookiejar'):
                    credentials[label+'_cookies'] = [c.value for c in handler.cookiejar]
            (private/'credentials.json').write_text(json.dumps(credentials))

        proc = start(); login(admin, 'moadmin', 'admin'); login(other, 'moobserver', 'observer')
        wrong = Session(base); data = fields(wrong.request('GET', '/admin/login/'))
        data.update(username='moadmin', password='incorrect-'+uuid.uuid4().hex)
        response = wrong.request('POST', '/admin/login/', data=data)
        check('wrong_password_not_authenticated', response.status_code == 200 and '/login/' in response.path)
        stage = 'native_page_draft'
        home = sql('SELECT p.id,p.path,p.url_path FROM wagtailcore_page p JOIN home_homepage h ON h.page_ptr_id=p.id')[0]
        parent_id = home[0]; add_path = '/admin/pages/add/home/homepage/'+str(parent_id)+'/'
        title = '原生草稿 中文 😀𠮷'; description = '说明正文 中文 😀𠮷'
        draft_form = fields(admin.request('GET', add_path), add_path)
        draft_form.update(title=title, slug='native-page', search_description=description, **{'action-save-draft': 'action-save-draft'})
        response = admin.request('POST', add_path, data=draft_form, headers={'Referer': base+add_path}); save_private(response, 'create-draft')
        rows = sql('SELECT id,title,draft_title,live,path,url_path,latest_revision_id FROM wagtailcore_page WHERE slug=%s', ('native-page',))
        check('native_draft_exact_SQL_and_tree', response.status_code == 200 and len(rows) == 1 and rows[0][1:4] == (title, title, 0) and rows[0][4].startswith(home[1]) and rows[0][5] == home[2]+'native-page/')
        page_id = rows[0][0]; edit_path = '/admin/pages/'+str(page_id)+'/edit/'
        api_path = '/api/v2/pages/'+str(page_id)+'/'
        check('draft_absent_from_public_API', anonymous.request('GET', api_path).status_code == 404)
        check('native_subclass_link', sql('SELECT page_ptr_id FROM home_homepage WHERE page_ptr_id=%s', (page_id,)) == ((page_id,),))

        def revision_exact(expected):
            row = sql('SELECT r.object_id,r.content,p.latest_revision_id,r.id FROM wagtailcore_page p JOIN wagtailcore_revision r ON r.id=p.latest_revision_id WHERE p.id=%s', (page_id,))[0]
            content = json.loads(row[1]) if isinstance(row[1], (str, bytes)) else row[1]
            return str(row[0]) == str(page_id) and content['title'] == expected and content['search_description'] == description and row[2] == row[3]

        check('native_draft_revision_exact_JSON', revision_exact(title))
        stage = 'native_permission_denials'
        before = sql('SELECT COUNT(*) FROM wagtailcore_revision')
        def permission_denied(response):
            # Wagtail's standard non-AJAX denial redirects to the dashboard
            # with this exact error message. A generic HTTP 200 is insufficient.
            if response.status_code == 403:
                return True
            message = BeautifulSoup(response.text, 'html.parser').select_one('.messages')
            return (response.status_code == 200 and response.path == '/admin/' and message is not None
                    and 'Sorry, you do not have permission to access this area.' in message.get_text(' ', strip=True))
        other_response = other.request('GET', edit_path)
        check('observer_page_edit_denied', permission_denied(other_response))
        observer_csrf = next(c.value for h in other.opener.handlers if hasattr(h, 'cookiejar')
                             for c in h.cookiejar if c.name == 'csrftoken')
        response = other.request('POST', edit_path, data={**draft_form, 'csrfmiddlewaretoken': observer_csrf},
                                 headers={'Referer': base+edit_path})
        check('observer_page_update_denied_zero_revision', permission_denied(response)
              and 'CSRF verification failed' not in response.text
              and sql('SELECT COUNT(*) FROM wagtailcore_revision') == before)
        anon_response = anonymous.request('GET', edit_path)
        check('anonymous_admin_login_required', anon_response.status_code == 302 and '/admin/login/' in anon_response.headers.get('Location', ''))
        invalid = fields(admin.request('GET', edit_path), edit_path)
        invalid.update(title='invalid CSRF write', csrfmiddlewaretoken='invalid-token', **{'action-publish': 'action-publish'})
        response = admin.request('POST', edit_path, data=invalid)
        check('invalid_CSRF_denied_zero_revision', response.status_code == 403 and sql('SELECT COUNT(*) FROM wagtailcore_revision') == before)

        def edit(expected, publish):
            payload = fields(admin.request('GET', edit_path), edit_path)
            key = 'action-publish' if publish else 'action-save-draft'
            payload.update(title=expected, search_description=description, **{key: key})
            response = admin.request('POST', edit_path, data=payload, headers={'Referer': base+edit_path})
            save_private(response, 'publish' if publish else 'update-draft')
            check('native_editor_'+key, response.status_code == 200 and revision_exact(expected))

        def public_exact(expected, label):
            response = anonymous.request('GET', api_path)
            document = response.json() if response.status_code == 200 else {}
            check(label+'_public_API_exact', response.status_code == 200 and document['title'] == expected and document['meta']['first_published_at'])
            public = anonymous.request('GET', '/native-page/')
            check(label+'_public_HTML_exact', public.status_code == 200 and BeautifulSoup(public.text, 'html.parser').h1.get_text() == expected and description in public.text)
            check(label+'_published_SQL_exact', sql('SELECT title,live,search_description FROM wagtailcore_page WHERE id=%s', (page_id,)) == ((expected, 1, description),))

        stage = 'native_publish'; edit(title, True); public_exact(title, 'first_publish')
        updated = '更新草稿 中文 😀𠮷'; edit(updated, False)
        check('new_draft_exact_revision', revision_exact(updated))
        public_exact(title, 'draft_keeps_live_version')
        edit(updated, True); public_exact(updated, 'second_publish')
        stage = 'native_restart'; previous = proc.pid; owned.stop(proc); proc = start()
        check('real_Gunicorn_process_restart', proc.pid != previous)
        public_exact(updated, 'after_restart')
        check('after_restart_native_admin_session', admin.request('GET', edit_path).status_code == 200)
        check('after_restart_observer_session_still_authenticated', other.request('GET', '/admin/').status_code == 200)
        check('after_restart_observer_denied', permission_denied(other.request('GET', edit_path)))
        check('after_restart_revision_and_migrations_exact', revision_exact(updated) and sql('SELECT COUNT(*) FROM django_migrations') == ((migration_count,),))
        stage = 'native_unpublish'
        path = '/admin/pages/'+str(page_id)+'/unpublish/'
        data = fields(admin.request('GET', path), path)
        response = admin.request('POST', path, data=data)
        check('native_unpublish_SQL_and_public_denial', response.status_code == 200 and sql('SELECT live FROM wagtailcore_page WHERE id=%s', (page_id,)) == ((0,),) and anonymous.request('GET', api_path).status_code == 404)
        check('post_trigger_SQL_health', sql('SELECT 1') == ((1,),))
        report['passed'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, failed_stage=stage)
        if isinstance(exc, AssertionError):
            report['failed_check'] = str(exc)
    finally:
        owned.close()
    return finish(out, report, 'wagtail-native')


if __name__ == '__main__':
    raise SystemExit(main())
