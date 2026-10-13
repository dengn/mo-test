"""Small shared primitives for real native applications; no fixture/result replay."""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def runtime_root():
    root = Path(os.getenv('MO_APP_RUNTIME_ROOT') or Path(__file__).resolve().parent / 'runtime').resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def private_file(path, data):
    path = Path(path)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(data.encode() if isinstance(data, str) else data)


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def copy_pinned_source(source, target, manifest, adaptations=None):
    adaptations = adaptations or {}
    target.mkdir(mode=0o700)
    for entry in manifest['files']:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Unsafe pinned source path')
        original = source / relative
        if original.is_symlink():
            raise RuntimeError('Unexpected source symlink')
        data = original.read_bytes()
        expected = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        patch = adaptations.get(entry['path'])
        if expected != entry['git_blob'] and (not patch or data != patch.read_bytes()):
            raise RuntimeError('Source differs from pinned original/adaptation: ' + entry['path'])
        destination = target / relative; destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(patch.read_bytes() if patch else data)
        destination.chmod(0o755 if entry['mode'] == '100755' else 0o644)
    return len(manifest['files'])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Response:
    def __init__(self, status, headers, body):
        self.status_code, self.headers, self.content = status, headers, body
        self.text = body.decode('utf-8', errors='replace')

    def json(self):
        return json.loads(self.content)


class Client:
    def __init__(self, base):
        self.base, self.headers = base, {}
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())

    def request(self, method, path, json_data=None, data=None, headers=None, timeout=45):
        combined = {**self.headers, **(headers or {})}
        if json_data is not None:
            data = json.dumps(json_data, ensure_ascii=False).encode()
            combined['Content-Type'] = 'application/json'
        elif isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode()
            combined['Content-Type'] = 'application/x-www-form-urlencoded'
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=combined)
        try:
            response = self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            body = response.read(8 * 1024**2 + 1)
            if len(body) > 8 * 1024**2:
                raise RuntimeError('Native HTTP response exceeds test bound')
            return Response(response.code, response.headers, body)


class Processes:
    def __init__(self, private, report):
        self.private, self.report, self.running, self.logs = private, report, [], []

    def start(self, command, cwd, env, label):
        path = self.private / (label + '-' + str(len(self.logs)) + '.log')
        log = os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb')
        self.logs.append(log)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        self.running.append(process)
        return process

    def stop(self, process, timeout=20):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.report['forced_stop'] = True
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)

    def close(self):
        for process in reversed(self.running):
            self.stop(process)
        for stream in self.logs:
            stream.close()


def connection_config():
    if 'MO_PASSWORD' not in os.environ:
        raise RuntimeError('MO_PASSWORD is required')
    return dict(host=os.getenv('MO_HOST', '127.0.0.1'), port=int(os.getenv('MO_PORT', '6001')),
                user=os.getenv('MO_USER', 'root'), password=os.environ['MO_PASSWORD'],
                charset='utf8mb4', autocommit=True, connect_timeout=10, read_timeout=45, write_timeout=15)


def finish(out, report, name):
    report['finished_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    checks = report['checks'][:]
    if not report['passed'] and all(check['passed'] for check in checks):
        checks.append({'name': 'native_execution', 'passed': False})
    suite = ET.Element('testsuite', name=name, tests=str(len(checks)),
                       failures=str(sum(not c['passed'] for c in checks)))
    for check in checks:
        node = ET.SubElement(suite, 'testcase', name=check['name'], classname=name)
        if not check['passed']:
            ET.SubElement(node, 'failure', message=check['name'])
    ET.ElementTree(suite).write(out / 'junit.xml', encoding='utf-8', xml_declaration=True)
    print(json.dumps({'app': name, 'passed': report['passed'], 'checks': len(report['checks']),
                      'failed_stage': report.get('failed_stage'), 'error_type': report.get('error_type')}))
    return int(not report['passed'])
