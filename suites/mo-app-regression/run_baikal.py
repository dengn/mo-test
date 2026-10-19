"""Unmodified pinned Baikal, native web installer/CSRF, DAV digest auth and restart."""
import argparse
from html.parser import HTMLParser
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

from native_common import runtime_root, Client, Processes, connection_config, digest, finish, port, private_file

ROOT = Path(__file__).resolve().parent
PHP_SHA = '9f738981bbcce1906329b751e57411171d5db0629ee00da0a41514f4a3d2f280'
URL = 'https://github.com/sabre-io/Baikal/releases/download/0.12.1/baikal-0.12.1.zip'


class Form(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.data = {}; self.select = None; self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs); name = attrs.get('name')
        if tag == 'input' and name and (attrs.get('type') != 'checkbox' or 'checked' in attrs):
            self.data[name] = attrs.get('value', '')
        if tag == 'select':
            self.select = name
        if tag == 'option' and self.select and 'selected' in attrs:
            self.data[self.select] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'select':
            self.select = None


def release(provided, private):
    manifest = json.loads((ROOT / 'fixtures/baikal/release-manifest.json').read_text())
    target = private / 'app'; target.mkdir(mode=0o700)
    if not provided:
        with urllib.request.urlopen(URL, timeout=90) as response:
            archive = response.read(16 * 1024**2 + 1)
        if hashlib.sha256(archive).hexdigest() != manifest['official_archive_sha256']:
            raise RuntimeError('Official Baikal archive digest mismatch')
        zipped = zipfile.ZipFile(io.BytesIO(archive))
    for entry in manifest['files']:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Unsafe release manifest path')
        if provided:
            original = provided / relative
            if original.is_symlink():
                raise RuntimeError('Unexpected source release symlink')
            data = original.read_bytes()
        else:
            data = zipped.read('baikal/' + entry['path'])
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise RuntimeError('Release file differs from pinned distribution: ' + entry['path'])
        path = target / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    return target, len(manifest['files'])


class Session(Client):
    def request(self, method, path, **kwargs):
        for _ in range(8):
            response = super().request(method, path, **kwargs)
            if response.status_code not in {301, 302, 303, 307, 308}:
                response.path = path; return response
            parsed = urllib.parse.urlsplit(urllib.parse.urljoin(self.base + path, response.headers['Location']))
            base = urllib.parse.urlsplit(self.base)
            if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
                raise RuntimeError('Redirect must remain on this owned native app')
            path = parsed.path + ('?' + parsed.query if parsed.query else '')
            if response.status_code in {301, 302, 303}:
                method, kwargs = 'GET', {}
        raise RuntimeError('Native redirect bound exceeded')

    def with_digest(self, username, password):
        manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, self.base + '/dav.php/', username, password)
        self.opener.add_handler(urllib.request.HTTPDigestAuthHandler(manager))
        return self


def main():
    import pymysql
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=os.getenv('MO_PHP_BINARY') or None, help='Pinned FrankenPHP runtime')
    parser.add_argument('--release-dir', type=Path, default=os.getenv('MO_BAIKAL_RELEASE_DIR') or None)
    parser.add_argument('--min-free-mib', type=int, default=2048)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts' / ('baikal-' + uuid.uuid4().hex[:12]))
    args = parser.parse_args()
    if args.min_free_mib < 128 or (args.min_free_mib < 2048 and not args.release_dir):
        parser.error('Low-disk basic validation requires an existing pinned release directory')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    schema = 'mo_reg_baikal_' + uuid.uuid4().hex[:16]
    private = runtime_root() / schema; private.mkdir(parents=True, mode=0o700)
    report = {'app': 'sabre-io/Baikal', 'version': '0.12.1', 'commit': 'cfa7433ea444b3cbc84761b3efbf2562c3a53949',
              'schema': schema, 'passed': False, 'checks': [], 'native_runtime_attempted': False,
              'source_edits': False, 'native_auth_and_CSRF_retained': True, 'manual_users_or_migration_stamps': False,
              'existing_databases_modified': False, 'min_free_mib': args.min_free_mib,
              'limitations': ['full upgrades, recurring/invited scheduling, sharing and locking semantics unverified']}
    owned = Processes(private, report); stage = 'admission'
    def check(name, value):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)
    try:
        if not args.binary or shutil.disk_usage(runtime_root()).free < args.min_free_mib * 1024**2 + 16 * 1024**2:
            raise RuntimeError('Pinned PHP runtime and space for fresh release copy required')
        php = args.binary.resolve(); check('pinned_FrankenPHP_runtime', digest(php) == PHP_SHA)
        app, count = release(args.release_dir, private); report['verified_release_files'] = count
        check('fresh_release_without_existing_installation', not (app / 'Specific/INSTALL_DISABLED').exists() and not (app / 'config/baikal.yaml').exists())
        cfg = connection_config()
        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as q:
                q.execute('SELECT VERSION(),git_version()'); report['server_version'], report['runtime_git_version'] = q.fetchone()
                check('actual_matrixone', 'MatrixOne' in report['server_version'])
                q.execute('CREATE DATABASE `' + schema + '` CHARACTER SET utf8mb4')
        cfg['database'] = schema
        def sql(query, params=()):
            with pymysql.connect(**cfg) as conn:
                with conn.cursor() as q:
                    q.execute(query, params); return q.fetchall()
        credentials = {'admin_password': secrets.token_urlsafe(24), 'owner_password': secrets.token_urlsafe(24), 'other_password': secrets.token_urlsafe(24)}
        private_file(private / 'credentials.json', json.dumps(credentials))
        web_port = port(); base = 'http://127.0.0.1:' + str(web_port); admin = Session(base); anonymous = Session(base)
        env = {**os.environ, 'XDG_CONFIG_HOME': str(private / 'caddy-config'), 'XDG_DATA_HOME': str(private / 'caddy-data'),
               'GOMAXPROCS': '2', 'GOMEMLIMIT': '512MiB', 'CADDY_ADMIN': 'off'}
        def start():
            process = owned.start([str(php), 'php-server', '--root', str(app / 'html'), '--listen', '127.0.0.1:' + str(web_port)], app, env, 'baikal')
            report['native_runtime_attempted'] = True; deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Native PHP startup failed; private log retained')
                try:
                    response = admin.request('GET', '/admin/install/', timeout=3)
                    if response.status_code == 200:
                        return process, response
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.25)
            raise TimeoutError('Native Baikal startup')
        stage = 'native_web_installation'; proc, response = start(); data = Form(response.text).data
        data.update({'data[timezone]': 'UTC', 'data[card_enabled]': '1', 'data[cal_enabled]': '1', 'data[invite_from]': '',
                     'data[dav_auth_type]': 'Digest', 'data[admin_passwordhash]': credentials['admin_password'],
                     'data[admin_passwordhash_confirm]': credentials['admin_password']})
        response = admin.request('POST', response.path, data=data)
        check('native_admin_settings_and_database_form', response.status_code == 200 and 'data[backend]' in response.text)
        response = admin.request('GET', '/admin/install/?/database'); data = Form(response.text).data
        data.update({'data[backend]': 'mysql', 'refreshed': '1'}); response = admin.request('POST', response.path, data=data)
        data = Form(response.text).data
        data.update({'data[backend]': 'mysql', 'refreshed': '0', 'data[mysql_host]': cfg['host'] + ';port=' + str(cfg['port']),
                     'data[mysql_dbname]': schema, 'data[mysql_username]': cfg['user'], 'data[mysql_password]': cfg['password'], 'data[mysql_ca_cert]': ''})
        response = admin.request('POST', response.path, data=data, timeout=60)
        check('native_MatrixOne_schema_installer', response.status_code == 200 and 'Baïkal is now installed' in response.text and (app / 'Specific/INSTALL_DISABLED').exists())
        check('native_14_tables', len(sql('SHOW TABLES')) == 14)
        for path in (app / 'config').glob('*.yaml'):
            path.chmod(0o600)
        stage = 'native_admin_authentication'; response = admin.request('GET', '/admin/'); data = Form(response.text).data
        data.update(login='admin', password=credentials['admin_password']); response = admin.request('POST', response.path, data=data)
        check('native_admin_password_login', response.status_code == 200 and 'Logout' in response.text and 'Dashboard' in response.text)
        for username, label in [('moalice', 'owner'), ('mobob', 'other')]:
            response = admin.request('GET', '/admin/?/users/new/1/'); data = Form(response.text).data
            check('native_user_creation_CSRF_' + label, 'CSRF_TOKEN' in data and 'data[username]' in data)
            data.update({'data[username]': username, 'data[displayname]': '原生用户 中文 😀𠮷', 'data[email]': username + '@example.test',
                         'data[password]': credentials[label + '_password'], 'data[passwordconfirm]': credentials[label + '_password']})
            response = admin.request('POST', response.path, data=data)
            check('native_user_creation_' + label, response.status_code == 200 and sql('SELECT COUNT(*) FROM users WHERE username=%s', (username,)) == ((1,),))
        stage = 'native_DAV_authentication'
        owner = Session(base).with_digest('moalice', credentials['owner_password']); other = Session(base).with_digest('mobob', credentials['other_password'])
        wrong = Session(base).with_digest('moalice', 'incorrect-' + uuid.uuid4().hex)
        def dav(client, method, path, expected, **kwargs):
            response = client.request(method, '/dav.php' + path, **kwargs)
            check('native_' + method + '_' + str(expected) + '_' + str(len(report['checks'])), response.status_code == expected)
            return response
        xml = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>'
        headers = {'Depth': '0', 'Content-Type': 'application/xml; charset=utf-8'}
        dav(anonymous, 'PROPFIND', '/', 401, data=xml, headers=headers)
        dav(wrong, 'PROPFIND', '/', 401, data=xml, headers=headers)
        dav(owner, 'PROPFIND', '/calendars/moalice/default/', 207, data=xml, headers=headers)
        cohort = uuid.uuid4().hex; uri, uid = 'native-' + cohort + '.ics', 'native-' + cohort + '@example.test'
        event = ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//MatrixOne Regression//EN\r\nBEGIN:VEVENT\r\nUID:' + uid + '\r\nDTSTAMP:20261012T000000Z\r\nDTSTART:20261012T090000Z\r\nDTEND:20261012T100000Z\r\nSUMMARY:中文日历 😀𠮷\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n').encode()
        event_path = '/calendars/moalice/default/' + uri
        stage = 'native_CalDAV'; dav(owner, 'PUT', event_path, 201, data=event, headers={'Content-Type': 'text/calendar; charset=utf-8', 'If-None-Match': '*'})
        response = dav(owner, 'GET', event_path, 200); etag = response.headers['ETag']; check('native_calendar_original_bytes', response.content == event)
        dav(other, 'GET', event_path, 403)
        card_uri = 'native-' + cohort + '.vcf'; card_path = '/addressbooks/moalice/default/' + card_uri
        card = ('BEGIN:VCARD\r\nVERSION:3.0\r\nUID:' + uid + '\r\nFN:中文联系人 😀𠮷\r\nN:联系人;中文;;;\r\nEMAIL:person@example.test\r\nEND:VCARD\r\n').encode()
        stage = 'native_CardDAV'; dav(owner, 'PUT', card_path, 201, data=card, headers={'Content-Type': 'text/vcard; charset=utf-8', 'If-None-Match': '*'})
        check('native_contact_original_bytes', dav(owner, 'GET', card_path, 200).content == card)
        dav(other, 'DELETE', card_path, 403)
        stage = 'conditional_update'; changed = event.replace('中文日历'.encode(), '修改日历'.encode())
        dav(owner, 'PUT', event_path, 412, data=changed, headers={'Content-Type': 'text/calendar', 'If-Match': '"invalid-test-etag"'})
        check('failed_ETag_update_preserves_bytes', dav(owner, 'GET', event_path, 200).content == event)
        dav(owner, 'PUT', event_path, 204, data=changed, headers={'Content-Type': 'text/calendar; charset=utf-8', 'If-Match': etag})
        check('native_conditional_update_exact_bytes', dav(owner, 'GET', event_path, 200).content == changed)
        def audit():
            calendars = sql('SELECT o.uri,o.calendardata,o.size,o.uid,i.principaluri FROM calendarobjects o JOIN calendarinstances i ON i.calendarid=o.calendarid WHERE o.uri=%s', (uri,))
            check('SQL_calendar_exact_blob_size_UID_owner', calendars == ((uri.encode(), changed, len(changed), uid.encode(), b'principals/moalice'),))
            cards = sql('SELECT c.uri,c.carddata,c.size,a.principaluri FROM cards c JOIN addressbooks a ON a.id=c.addressbookid WHERE c.uri=%s', (card_uri,))
            check('SQL_contact_exact_blob_size_owner', cards == ((card_uri.encode(), card, len(card), b'principals/moalice'),))
            return calendars, cards
        before = audit(); stage = 'native_restart'; old_pid = proc.pid; owned.stop(proc); proc, _ = start()
        check('real_PHP_process_restart', old_pid != proc.pid); check('restart_SQL_exact_original_rows', before == audit())
        check('restart_calendar_original_bytes', dav(owner, 'GET', event_path, 200).content == changed)
        check('restart_contact_original_bytes', dav(owner, 'GET', card_path, 200).content == card)
        stage = 'native_delete'; dav(owner, 'DELETE', event_path, 204); dav(owner, 'GET', event_path, 404)
        dav(owner, 'DELETE', card_path, 204); dav(owner, 'GET', card_path, 404)
        check('SQL_deleted_calendar_and_contact_absent', sql('SELECT COUNT(*) FROM calendarobjects WHERE uri=%s', (uri,)) == ((0,),) and sql('SELECT COUNT(*) FROM cards WHERE uri=%s', (card_uri,)) == ((0,),))
        check('post_trigger_SQL_health', sql('SELECT 1') == ((1,),)); report['passed'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, failed_stage=stage)
        if isinstance(exc, AssertionError):
            report['failed_check'] = str(exc)
    finally:
        owned.close()
    return finish(out, report, 'baikal-native')


if __name__ == '__main__':
    raise SystemExit(main())
