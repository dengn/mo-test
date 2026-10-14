"""Pinned WordPress, native web installation, REST roles/content and restart."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time
import urllib.error
import urllib.parse
import uuid

from bs4 import BeautifulSoup
from native_common import Client, Processes, connection_config, copy_pinned_source, digest, finish, port, private_file, runtime_root
from run_baikal import Session

ROOT = Path(__file__).resolve().parent
PHP_SHA = '9f738981bbcce1906329b751e57411171d5db0629ee00da0a41514f4a3d2f280'


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=os.getenv('MO_PHP_BINARY') or None)
    parser.add_argument('--source-tree', type=Path, default=os.getenv('MO_WORDPRESS_SOURCE_TREE') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT/'artifacts'/('wordpress-'+uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:
        parser.error('Minimum admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_wordpress_'+uuid.uuid4().hex[:16]
    private = runtime_root()/schema; private.mkdir(mode=0o700)
    report = {'app': 'WordPress/WordPress', 'version': '7.2-alpha-64292',
              'commit': '5c09ed3ccb354b0553e9b59c2876be0fc40574ca', 'schema': schema,
              'passed': False, 'checks': [], 'native_runtime_attempted': False,
              'min_free_mib': args.min_free_mib, 'existing_databases_modified': False,
              'manual_SQL_users_or_migration_stamps': False,
              'limitations': ['pinned historical alpha snapshot; not stable-release certification',
                              'native local-environment application passwords on owned loopback server only',
                              'cron, automatic core/plugin updates disabled; plugins, uploads, multisite, upgrades and load unverified']}
    owned = Processes(private, report); stage = 'admission'

    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)

    try:
        if not args.binary or not args.source_tree or shutil.disk_usage(runtime_root()).free < args.min_free_mib*1024**2+128*1024**2:
            raise RuntimeError('Pinned PHP/source SDK and private source copy headroom required')
        php = args.binary.resolve(); check('pinned_PHP_runtime', digest(php) == PHP_SHA)
        fixture = ROOT/'fixtures/wordpress'; manifest = json.loads((fixture/'source-manifest.json').read_text())
        app = private/'app'; count = copy_pinned_source(args.source_tree.resolve(), app, manifest)
        report['verified_source_blobs'] = count
        check('pinned_all_source_without_old_config', count == 5028 and not(app/'wp-config.php').exists() and not(app/'wp-content/db.php').exists())
        (app/'wp-content/db.php').write_bytes((fixture/'db.php').read_bytes())
        report['adapter_sha256'] = digest(fixture/'db.php')
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

        credentials = {'admin_password': 'Mo1-'+secrets.token_hex(12), 'subscriber_password': 'Mo1-'+secrets.token_hex(12),
                       'auth_salt': secrets.token_urlsafe(64)}
        private_file(private/'credentials.json', json.dumps(credentials))
        base = 'http://127.0.0.1:'+str(port()); admin_cookie = Session(base); anonymous = Client(base)
        private_file(app/'wp-config.php', "<?php\n"
            "define('DB_NAME',getenv('MO_NATIVE_SCHEMA')); define('DB_USER',getenv('MO_USER')); define('DB_PASSWORD',getenv('MO_PASSWORD'));\n"
            "define('DB_HOST',getenv('MO_NATIVE_DB_HOST')); define('DB_CHARSET','utf8mb4'); define('DB_COLLATE','');\n"
            "foreach(['AUTH_KEY','SECURE_AUTH_KEY','LOGGED_IN_KEY','NONCE_KEY','AUTH_SALT','SECURE_AUTH_SALT','LOGGED_IN_SALT','NONCE_SALT'] as $name) { define($name,hash('sha256',getenv('MO_NATIVE_AUTH_SALT').$name)); }\n"
            "define('WP_HOME',getenv('MO_NATIVE_BASE_URL')); define('WP_SITEURL',getenv('MO_NATIVE_BASE_URL')); define('WP_ENVIRONMENT_TYPE','local');\n"
            "define('DISABLE_WP_CRON',true); define('AUTOMATIC_UPDATER_DISABLED',true); define('WP_AUTO_UPDATE_CORE',false); define('DISALLOW_FILE_MODS',true);\n"
            "define('WP_DEBUG',false); define('WP_DEBUG_DISPLAY',false); $table_prefix='wp_';\n"
            "if(!defined('ABSPATH')) define('ABSPATH',__DIR__.'/'); require_once ABSPATH.'wp-settings.php';\n")
        ini = private/'php-ini'; ini.mkdir(mode=0o700)
        private_file(ini/'local.ini', 'date.timezone=UTC\ndisplay_errors=Off\nlog_errors=On\nmemory_limit=256M\n')
        caddy = private/'Caddyfile'
        private_file(caddy, '{\n admin off\n auto_https off\n frankenphp {\n  num_threads 4\n }\n}\n'+base+' {\n root * '+str(app)+'\n @blocked path /wp-config.php /license.txt /readme.html\n respond @blocked 403\n php_server\n}\n')
        host = '['+cfg['host']+']' if ':' in cfg['host'] else cfg['host']
        env = {**os.environ, 'MO_HOST': cfg['host'], 'MO_PORT': str(cfg['port']), 'MO_USER': cfg['user'],
               'MO_NATIVE_SCHEMA': schema, 'MO_NATIVE_DB_HOST': host+':'+str(cfg['port']),
               'MO_NATIVE_AUTH_SALT': credentials['auth_salt'], 'MO_NATIVE_BASE_URL': base,
               'PHP_INI_SCAN_DIR': str(ini), 'GOMAXPROCS': '2', 'GOMEMLIMIT': '512MiB',
               'XDG_CONFIG_HOME': str(private/'config'), 'XDG_DATA_HOME': str(private/'data')}

        def start():
            process = owned.start([str(php), 'run', '--config', str(caddy)], app, env, 'wordpress')
            report['native_runtime_attempted'] = True; deadline = time.monotonic()+90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Native WordPress startup failed; private log retained')
                try:
                    if anonymous.request('GET', '/wp-login.php', timeout=3).status_code in {200, 302}:
                        return process
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.2)
            raise TimeoutError('Native WordPress startup')

        stage = 'native_install'; proc = start()
        response = admin_cookie.request('POST', '/wp-admin/install.php?step=2', data={
            'weblog_title': '原生WordPress 中文 😀𠮷', 'user_name': 'moadmin', 'admin_password': credentials['admin_password'],
            'admin_password2': credentials['admin_password'], 'pw_weak': '1', 'admin_email': 'admin@example.test', 'blog_public': '0'}, timeout=180)
        private_file(private/'install-response.private.html', response.content)
        check('native_web_installer', response.status_code == 200 and 'WordPress has been installed' in response.text)
        report['native_table_count'] = len(sql('SHOW TABLES'))
        check('native_core_tables', report['native_table_count'] == 12)
        admin_id = sql('SELECT ID FROM wp_users WHERE user_login=%s', ('moadmin',))[0][0]
        check('native_admin_password_hash_and_role', sql('SELECT LENGTH(user_pass) FROM wp_users WHERE ID=%s', (admin_id,))[0][0] > 50
              and 'administrator' in sql('SELECT meta_value FROM wp_usermeta WHERE user_id=%s AND meta_key=%s', (admin_id, 'wp_capabilities'))[0][0])
        stage = 'native_authentication'
        admin_cookie.request('GET', '/wp-login.php')
        response = admin_cookie.request('POST', '/wp-login.php', data={'log': 'moadmin', 'pwd': credentials['admin_password'],
            'wp-submit': 'Log In', 'redirect_to': base+'/wp-admin/', 'testcookie': '1'}, timeout=90)
        check('native_password_cookie_login', response.status_code == 200 and response.path.startswith('/wp-admin/'))
        response = admin_cookie.request('GET', '/wp-admin/admin-ajax.php?action=rest-nonce')
        nonce = response.text.strip()
        check('native_REST_nonce', response.status_code == 200 and bool(re.fullmatch('[a-zA-Z0-9]{8,16}', nonce)))
        credentials['REST_nonce'] = nonce
        admin_cookie.headers['X-WP-Nonce'] = nonce

        def rest(client, method, path, body=None, denied=False, codes=None):
            response = client.request(method, '/index.php?rest_route='+path, json_data=body, timeout=120)
            try:
                doc = response.json()
            except ValueError:
                private_file(private/('REST-'+uuid.uuid4().hex+'.private'), response.content)
                raise AssertionError('native_REST_JSON')
            if denied:
                return response.status_code in (codes or {401, 403, 404}) and isinstance(doc, dict) and bool(doc.get('code'))
            if response.status_code not in {200, 201}:
                private_file(private/('REST-'+uuid.uuid4().hex+'.private.json'), response.content)
                raise AssertionError('native_REST_'+method+'_'+path.split('&')[0])
            return doc

        def application_password(user_id, label):
            doc = rest(admin_cookie, 'POST', '/wp/v2/users/'+str(user_id)+'/application-passwords', {'name': 'MatrixOne regression '+label})
            credentials[label+'_application_password'] = doc['password']; credentials[label+'_application_password_uuid'] = doc['uuid']
            (private/'credentials.json').write_text(json.dumps(credentials))
            return doc['password']

        def basic(username, password):
            client = Client(base)
            client.headers['Authorization'] = 'Basic '+base64.b64encode((username+':'+password).encode()).decode()
            return client

        admin = basic('moadmin', application_password(admin_id, 'admin'))
        check('native_application_password_auth', rest(admin, 'GET', '/wp/v2/users/me&context=edit')['id'] == admin_id)
        subscriber_doc = rest(admin, 'POST', '/wp/v2/users', {'username': 'moother', 'email': 'subscriber@example.test',
            'password': credentials['subscriber_password'], 'roles': ['subscriber']})
        subscriber_id = subscriber_doc['id']; other = basic('moother', application_password(subscriber_id, 'subscriber'))
        check('native_subscriber_role', rest(other, 'GET', '/wp/v2/users/me&context=edit')['roles'] == ['subscriber'])
        check('wrong_application_password_denied', rest(basic('moadmin', 'incorrect-'+uuid.uuid4().hex), 'GET', '/wp/v2/users/me', denied=True, codes={401}))
        before = sql('SELECT COUNT(*) FROM wp_posts')
        check('subscriber_post_create_denied_zero_write', rest(other, 'POST', '/wp/v2/posts', {'title': 'invalid write'}, denied=True) and sql('SELECT COUNT(*) FROM wp_posts') == before)
        check('anonymous_post_create_denied_zero_write', rest(anonymous, 'POST', '/wp/v2/posts', {'title': 'invalid write'}, denied=True) and sql('SELECT COUNT(*) FROM wp_posts') == before)
        stage = 'native_content'
        category_name = '原生分类 中文 😀𠮷'
        category = rest(admin, 'POST', '/wp/v2/categories', {'name': category_name, 'slug': 'native-category'})['id']
        before = sql('SELECT COUNT(*) FROM wp_terms')
        check('native_duplicate_category_denied_zero_write', rest(admin, 'POST', '/wp/v2/categories', {'name': category_name, 'slug': 'native-category'}, denied=True, codes={400}) and sql('SELECT COUNT(*) FROM wp_terms') == before)
        title = '原生草稿 中文 😀𠮷'; content = '<p>原生正文 中文 😀𠮷</p>'
        post = rest(admin, 'POST', '/wp/v2/posts', {'title': title, 'content': content, 'status': 'draft', 'categories': [category]})['id']
        check('native_draft_SQL_exact', sql('SELECT post_title,post_content,post_status,post_author FROM wp_posts WHERE ID=%s', (post,)) == ((title, content, 'draft', admin_id),))
        check('anonymous_draft_denied', rest(anonymous, 'GET', '/wp/v2/posts/'+str(post), denied=True))
        check('subscriber_private_draft_denied', rest(other, 'GET', '/wp/v2/posts/'+str(post), denied=True))
        title = '已发布文章 中文 😀𠮷'
        rest(admin, 'POST', '/wp/v2/posts/'+str(post), {'title': title, 'status': 'publish'})

        def readback(prefix):
            doc = rest(admin, 'GET', '/wp/v2/posts/'+str(post)+'&context=edit')
            check(prefix+'_native_raw_content_and_author', doc['title']['raw'] == title and doc['content']['raw'] == content and doc['author'] == admin_id and doc['status'] == 'publish' and doc['categories'] == [category])
            public = rest(anonymous, 'GET', '/wp/v2/posts/'+str(post))
            check(prefix+'_public_rendered_exact', public['title']['rendered'] == title and BeautifulSoup(public['content']['rendered'], 'html.parser').get_text(strip=True) == '原生正文 中文 😀𠮷')
            check(prefix+'_SQL_post_category_exact', sql('SELECT p.post_title,p.post_content,p.post_status,p.post_author,t.name FROM wp_posts p JOIN wp_term_relationships r ON r.object_id=p.ID JOIN wp_term_taxonomy tt ON tt.term_taxonomy_id=r.term_taxonomy_id JOIN wp_terms t ON t.term_id=tt.term_id WHERE p.ID=%s AND tt.taxonomy=%s', (post, 'category')) == ((title, content, 'publish', admin_id, category_name),))

        readback('before_restart')
        comment_text = '原生评论 中文 😀𠮷'
        comment = rest(admin, 'POST', '/wp/v2/comments', {'post': post, 'content': comment_text, 'status': 'approved'})['id']
        check('native_comment_SQL_owner_and_post', sql('SELECT comment_post_ID,user_id,comment_content,comment_approved FROM wp_comments WHERE comment_ID=%s', (comment,)) == ((post, admin_id, comment_text, '1'),))
        previous_published = title; title = '再次更新文章 中文 😀𠮷'
        rest(admin, 'POST', '/wp/v2/posts/'+str(post), {'title': title})
        revisions = rest(admin, 'GET', '/wp/v2/posts/'+str(post)+'/revisions&context=edit')
        check('native_revision_parent_and_previous_published_title',
              any(r['parent'] == post and r['title']['raw'] == previous_published for r in revisions)
              and any(r['parent'] == post and r['title']['raw'] == title for r in revisions))
        invalid = dict(admin_cookie.headers); admin_cookie.headers['X-WP-Nonce'] = 'invalid-native-nonce'
        before = sql('SELECT COUNT(*) FROM wp_posts')
        check('invalid_cookie_REST_nonce_denied_zero_write', rest(admin_cookie, 'POST', '/wp/v2/posts', {'title': 'invalid nonce'}, denied=True, codes={403}) and sql('SELECT COUNT(*) FROM wp_posts') == before)
        admin_cookie.headers = invalid
        before = sql('SELECT post_title,post_content,post_status FROM wp_posts WHERE ID=%s', (post,))
        check('subscriber_update_denied_zero_write', rest(other, 'POST', '/wp/v2/posts/'+str(post), {'title': 'invalid cross-user update'}, denied=True) and sql('SELECT post_title,post_content,post_status FROM wp_posts WHERE ID=%s', (post,)) == before)
        stage = 'native_restart'; previous = proc.pid; owned.stop(proc); proc = start()
        check('real_PHP_process_restart', proc.pid != previous); readback('after_restart')
        check('after_restart_comment_API_exact', BeautifulSoup(rest(anonymous, 'GET', '/wp/v2/comments/'+str(comment))['content']['rendered'], 'html.parser').get_text(strip=True) == comment_text)
        check('after_restart_subscriber_auth_and_denial', rest(other, 'GET', '/wp/v2/users/me')['id'] == subscriber_id and rest(other, 'POST', '/wp/v2/posts/'+str(post), {'title': 'invalid write'}, denied=True))
        revoked = rest(admin, 'DELETE', '/wp/v2/users/'+str(subscriber_id)+'/application-passwords/'+credentials['subscriber_application_password_uuid'])
        check('native_application_password_revoke', revoked['deleted'] is True and rest(other, 'GET', '/wp/v2/users/me', denied=True, codes={401}))
        check('no_native_WordPress_database_error_logs', all(b'WordPress database error' not in p.read_bytes() for p in private.glob('wordpress-*.log')))
        check('post_trigger_SQL_health', sql('SELECT 1') == ((1,),)); report['passed'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, failed_stage=stage)
        if isinstance(exc, AssertionError):
            report['failed_check'] = str(exc)
    finally:
        owned.close()
    return finish(out, report, 'wordpress-native')


if __name__ == '__main__':
    raise SystemExit(main())
