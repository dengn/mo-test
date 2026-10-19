"""Pinned FreshRSS web installer, native account controllers and Google Reader APIs."""
import argparse
import base64
import datetime
import email.utils
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import time
import urllib.error
import uuid
import zlib

from run_baikal import Session
from native_common import Client, Processes, connection_config, copy_pinned_source, digest, finish, port, private_file, runtime_root

ROOT = Path(__file__).resolve().parent
PHP_SHA = '9f738981bbcce1906329b751e57411171d5db0629ee00da0a41514f4a3d2f280'


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=os.getenv('MO_PHP_BINARY') or None)
    parser.add_argument('--source-tree', type=Path, default=os.getenv('MO_FRESHRSS_SOURCE_TREE') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('freshrss-' + uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128:
        parser.error('Minimum admission floor is 128 MiB')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_freshrss_' + uuid.uuid4().hex[:16]
    private = runtime_root() / schema; private.mkdir(mode=0o700, parents=True)
    report = {'app': 'FreshRSS/FreshRSS', 'commit': '4a810f1624b9d0b97b4400614cf9aacc8ada40e3', 'schema': schema,
              'passed': False, 'checks': [], 'native_runtime_attempted': False, 'manual_SQL_users_or_migration_stamps': False,
              'existing_databases_modified': False, 'source_edits': ['CategoryDAO.php', 'EntryDAO.php'],
              'min_free_mib': args.min_free_mib, 'limitations': ['Google Reader API only; complete UI/populated upgrades/concurrent feed commits unverified']}
    owned = Processes(private, report); fixture = None; thread = None; stage = 'admission'
    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)
    try:
        if not args.binary or not args.source_tree or shutil.disk_usage(runtime_root()).free < args.min_free_mib * 1024**2 + 32 * 1024**2:
            raise RuntimeError('Pinned PHP/source SDK and space for private source copy required')
        php = args.binary.resolve(); check('pinned_FrankenPHP_runtime', digest(php) == PHP_SHA)
        app = private / 'app'; manifests = ROOT / 'fixtures/freshrss'
        manifest = json.loads((manifests / 'source-manifest.json').read_text())
        patches = {'app/Models/CategoryDAO.php': manifests / 'CategoryDAO.php', 'app/Models/EntryDAO.php': manifests / 'EntryDAO.php'}
        report['verified_source_blobs'] = copy_pinned_source(args.source_tree, app, manifest, patches)
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
        credentials = {'owner_password': secrets.token_urlsafe(24), 'owner_api_password': secrets.token_urlsafe(24),
                       'other_password': secrets.token_urlsafe(24), 'other_api_password': secrets.token_urlsafe(24)}
        private_file(private / 'credentials.json', json.dumps(credentials))
        env = {**os.environ, 'XDG_CONFIG_HOME': str(private / 'config'), 'XDG_DATA_HOME': str(private / 'data'),
               'GOMAXPROCS': '2', 'GOMEMLIMIT': '512MiB', 'CADDY_ADMIN': 'off'}
        def task(label, script, arguments):
            joined = []
            i = 0
            while i < len(arguments):
                option = arguments[i]
                if i + 1 < len(arguments) and not arguments[i + 1].startswith('--'):
                    joined.append(option + '=' + arguments[i + 1]); i += 2
                else:
                    joined.append(option); i += 1
            # Native PHP getopt reads the actual process argv, not a rewritten PHP variable.
            # Database password uses FreshRSS's supported private config override below.
            p = owned.start([str(php), 'php-cli', str(app / 'cli' / script), *joined], app, env, label)
            report['native_runtime_attempted'] = True
            code = p.wait(timeout=120); check(label, code == 0)
        fixture_port = port()
        private_file(app / 'data/config.custom.php', '<?php return ["api_enabled"=>true,"allow_anonymous"=>false,"allow_anonymous_refresh"=>false,"default_feeds"=>[],"disable_update"=>true,"internal_host_allowlist"=>["127.0.0.1:' + str(fixture_port) + '"]];')
        report['native_internal_host_allowlist'] = ['127.0.0.1:' + str(fixture_port)]
        stage = 'native_prepare'; task('native_prepare_directories', 'prepare.php', [])
        # All remote feed fetching is constrained to this owned fixture; article URLs are also loopback.
        cohort = uuid.uuid4().hex; titles = ['原生文章 中文 😀𠮷 & A', '原生文章 中文 😀𠮷 B']
        bodies = ['<p>精确正文 中文 😀𠮷 A</p>', '<p>精确正文 中文 😀𠮷 B</p>']
        fixture_base = 'http://127.0.0.1:' + str(fixture_port)
        guids = ['urn:mo:' + cohort + ':' + str(i) for i in range(2)]
        now = email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc), usegmt=True)
        items = ''.join('<item><title>' + html.escape(titles[i]) + '</title><link>' + fixture_base + '/article/' + str(i) + '</link>'
                        '<guid isPermaLink="false">' + guids[i] + '</guid><pubDate>' + now + '</pubDate><description>' + html.escape(bodies[i]) + '</description></item>' for i in range(2))
        rss = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>MatrixOne Feed 中文 😀𠮷</title><link>' + fixture_base + '</link><description>Native fixture</description>' + items + '</channel></rss>').encode()
        class Feed(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != '/feed.xml':
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.send_header('Content-Type', 'application/rss+xml; charset=utf-8')
                self.send_header('Content-Length', str(len(rss))); self.end_headers(); self.wfile.write(rss)
            def log_message(self, *args):pass
        fixture = ThreadingHTTPServer(('127.0.0.1', fixture_port), Feed); thread = threading.Thread(target=fixture.serve_forever, daemon=True); thread.start()
        owner, other, anonymous = Client(base), Client(base), Client(base); installer = Session(base)
        prefix = '/api/greader.php/'
        def start(install=False):
            p = owned.start([str(php), 'php-server', '--root', str(app / 'p'), '--listen', '127.0.0.1:' + str(web_port)], app, env, 'freshrss')
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if p.poll() is not None:raise RuntimeError('Native PHP process exited; private log retained')
                try:
                    response = installer.request('GET', '/i/index.php?step=0', timeout=2) if install else anonymous.request('POST', prefix + 'accounts/ClientLogin', data={'Email': 'moalice', 'Passwd': 'invalid'}, timeout=2)
                    if response.status_code == (200 if install else 401):return p
                except (OSError, urllib.error.URLError):pass
                time.sleep(.2)
            raise TimeoutError('Native FreshRSS startup')
        stage = 'native_web_installer'; proc = start(install=True)
        response = installer.request('POST', '/i/index.php?step=0', data={'language':'en'})
        check('native_language_and_session_step', response.status_code == 200 and 'step=2' in response.text)
        response = installer.request('POST', '/i/index.php?step=2', data={'type':'mysql','host':cfg['host']+':'+str(cfg['port']),
            'user':cfg['user'],'pass':cfg['password'],'base':schema,'prefix':'rss_'})
        check('native_database_installer_step', response.status_code == 200 and 'passwordPlain' in response.text)
        response = installer.request('POST', '/i/index.php?step=3', data={'default_user':'moalice','auth_type':'form',
            'passwordPlain':credentials['owner_password'],'title':'MatrixOne 原生 RSS 回归'})
        check('native_admin_created', response.status_code == 200 and (app/'data/users/moalice/config.php').exists())
        response = installer.request('GET', '/i/index.php?step=5')
        check('native_admin_setup_and_migration_marker', response.status_code == 200 and (app/'data/applied_migrations.txt').exists())
        # Invoke the same original user/API controllers as the upstream admin CLI, with
        # secrets supplied by environment. No direct users/config-hash/SQL insertion.
        for label, username in [('owner','moalice'),('other','mobob')]:
            wrapper = private/(label+'-native-controller.php')
            path_literal = base64.b64encode(str(app/'cli/_cli.php').encode()).decode()
            code = '<?php require base64_decode('+repr(path_literal)+'); '
            if label=='other':
                code += 'if (!FreshRSS_user_Controller::createUser(getenv("REG_USER"), "", getenv("REG_PASSWORD"), ["enabled"=>true,"is_admin"=>false], false)) {exit(1);} '
            code += 'cliInitUser(getenv("REG_USER")); if (FreshRSS_api_Controller::updatePassword(getenv("REG_API_PASSWORD")) !== false) {exit(2);} '
            private_file(wrapper,code)
            process=owned.start([str(php),'php-cli',str(wrapper)],app,{**env,'REG_USER':username,'REG_PASSWORD':credentials[label+'_password'],
                'REG_API_PASSWORD':credentials[label+'_api_password']},'native-controller-'+label)
            check('native_controller_account_and_API_password_'+label,process.wait(timeout=120)==0)
        tables={row[0] for row in sql('SHOW TABLES')}
        check('native_both_users_isolated_tables',{'rss_moalice_entry','rss_moalice_feed','rss_mobob_entry','rss_mobob_feed'}.issubset(tables))
        stage = 'native_API_authentication'
        for label, username, client in [('owner', 'moalice', owner), ('other', 'mobob', other)]:
            response = client.request('POST', prefix + 'accounts/ClientLogin', data={'Email': username, 'Passwd': credentials[label + '_api_password']})
            auth = next((line[5:] for line in response.text.splitlines() if line.startswith('Auth=')), '')
            check('native_API_password_login_' + label, response.status_code == 200 and auth.startswith(username + '/'))
            client.headers['Authorization'] = 'GoogleLogin auth=' + auth
        endpoint = prefix + 'reader/api/0/'
        check('anonymous_API_denied', anonymous.request('GET', endpoint + 'subscription/list?output=json').status_code == 401)
        stage = 'native_feed_subscription'
        initial_subscriptions = owner.request('GET', endpoint + 'subscription/list?output=json').json().get('subscriptions', [])
        report['native_initial_subscription_count'] = len(initial_subscriptions)
        response = owner.request('GET', endpoint + 'token'); token = response.text.strip(); check('native_write_token', response.status_code == 200 and len(token) >= 16)
        response = owner.request('POST', endpoint + 'subscription/quickadd', data={'quickadd': fixture_base + '/feed.xml', 'T': token})
        feed = response.json()
        private_file(private / 'native-quickadd-response.json', json.dumps(feed, ensure_ascii=False))
        report['quickadd_HTTP_status'] = response.status_code
        report['quickadd_num_results'] = feed.get('numResults')
        check('native_RSS_quickadd', response.status_code == 200 and feed.get('numResults') == 1 and feed.get('streamName') == 'MatrixOne Feed 中文 😀𠮷')
        stream = feed['streamId']
        def content(client, label):
            response = client.request('GET', endpoint + 'stream/contents/' + stream + '?output=json&n=100')
            items = response.json().get('items', [])
            # Upstream's compat API deliberately replaces &, <, > with fullwidth
            # characters. SQL retains HTML-encoded original text, asserted separately.
            expected_titles = {title.translate(str.maketrans({'&':'＆','<':'＜','>':'＞'})) for title in titles}
            check(label, response.status_code == 200 and len(items) == 2 and {item['title'] for item in items} == expected_titles
                  and all(item.get('summary', {}).get('content') in bodies for item in items))
            return items
        stage = 'native_exact_feed_read'; models = content(owner, 'native_exact_UTF8_titles_and_HTML_content')
        response = owner.request('GET', endpoint + 'subscription/list?output=json'); subscriptions = response.json().get('subscriptions', [])
        check('native_subscription_listing', response.status_code == 200 and len(subscriptions) == len(initial_subscriptions) + 1
              and sum(s.get('id') == stream and s.get('url') == fixture_base + '/feed.xml' for s in subscriptions) == 1)
        response = other.request('GET', endpoint + 'subscription/list?output=json')
        check('other_user_has_no_owner_subscription', response.status_code == 200 and all(
            s.get('url') != fixture_base + '/feed.xml' for s in response.json().get('subscriptions', [])))
        check('other_user_database_has_no_owner_entries', sql('SELECT COUNT(*) FROM rss_mobob_entry') == ((0,),))
        def audit(label):
            rows = sql('SELECT e.id,e.guid,e.title,e.content_bin,e.id_feed,f.name,f.url FROM rss_moalice_entry e JOIN rss_moalice_feed f ON f.id=e.id_feed ORDER BY e.guid')
            mapping = {row[1]: row for row in rows}
            def decoded_blob(value):
                # MySQL-style length prefix; observed MO uses raw DEFLATE while
                # a future runtime may use a zlib wrapper. Assert bytes and length,
                # and expose framing instead of certifying cross-vendor blob format.
                for bits, format_name in [(15, 'zlib'), (-15, 'raw_deflate')]:
                    try:
                        decoded = zlib.decompress(value[4:], bits)
                    except zlib.error:
                        continue
                    if int.from_bytes(value[:4], 'little') != len(decoded):
                        raise AssertionError('compressed_length_prefix')
                    report['observed_COMPRESS_framing'] = format_name
                    return decoded.decode()
                raise AssertionError('compressed_blob_not_decodable')
            check(label, len(rows) == len(mapping) == 2 and all(guid in mapping and html.unescape(mapping[guid][2]) == titles[i]
                  and decoded_blob(mapping[guid][3]) == bodies[i]
                  and mapping[guid][5:] == ('MatrixOne Feed 中文 😀𠮷', fixture_base + '/feed.xml') for i, guid in enumerate(guids)))
            check(label + '_API_identifiers_match_SQL', {int(item['id'].rsplit('/', 1)[-1], 16) for item in models} == {row[0] for row in rows})
            return rows
        before = audit('SQL_exact_GUID_UTF8_compressed_content_feed_links')
        stage = 'native_read_state'
        item_id = models[0]['id']; row_id = int(item_id.rsplit('/', 1)[-1], 16)
        response = owner.request('POST', endpoint + 'edit-tag', data={'i': item_id, 'a': 'user/-/state/com.google/read', 'T': 'invalid-token'})
        check('invalid_write_token_rejected_no_state_change', response.status_code in {400, 401} and sql('SELECT is_read FROM rss_moalice_entry WHERE id=%s', (row_id,)) == ((0,),))
        response = owner.request('POST', endpoint + 'edit-tag', data={'i': item_id, 'a': 'user/-/state/com.google/read', 'T': token})
        check('native_mark_read_and_SQL_state', response.status_code == 200 and sql('SELECT is_read FROM rss_moalice_entry WHERE id=%s', (row_id,)) == ((1,),))
        stage = 'native_restart'; old_pid = proc.pid; owned.stop(proc); proc = start(); check('real_PHP_process_restart', proc.pid != old_pid)
        check('restart_SQL_original_values_and_links', before == audit('restart_SQL_exact_feed_content'))
        content(owner, 'native_original_API_auth_and_content_after_restart')
        check('restart_native_read_state_preserved', sql('SELECT is_read FROM rss_moalice_entry WHERE id=%s', (row_id,)) == ((1,),))
        check('post_trigger_SQL_health', sql('SELECT 1') == ((1,),)); report['passed'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, failed_stage=stage)
        if isinstance(exc, AssertionError):report['failed_check'] = str(exc)
    finally:
        owned.close()
        if fixture:fixture.shutdown(); fixture.server_close()
        if thread:thread.join(timeout=5)
    return finish(out, report, 'freshrss-native')


if __name__ == '__main__':
    raise SystemExit(main())
