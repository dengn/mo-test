"""Build pinned Memos/ntfy source into a private, independently attested test SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from native_common import digest, private_file

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', choices=['memos', 'ntfy'], required=True)
    parser.add_argument('--source-tree', type=Path, required=True, help='Pristine checkout of the full pinned commit')
    parser.add_argument('--go', default='go', help='Go 1.27.1 executable')
    parser.add_argument('--out', type=Path, required=True, help='New directory; source, cache, logs and binary remain private')
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'app': args.app, 'passed': False, 'build_started': False, 'source_blobs_verified': 0,
              'UI_scope': 'placeholder assets; only native API tested', 'exit_code': 2}
    process = None
    try:
        if shutil.disk_usage(out).free < 4 * 1024**3:
            report['blocked_reason'] = 'Native Go SDK build requires at least 4 GiB free at admission'
            raise RuntimeError(report['blocked_reason'])
        version = subprocess.check_output([args.go, 'version'], text=True).strip()
        if not version.startswith('go version go1.27.1 '):
            raise RuntimeError('Go 1.27.1 is required for the pinned SDK recipe')
        report['go_version'] = version
        manifest = json.loads((ROOT / 'fixtures' / args.app / 'source-manifest.json').read_text())
        report['commit'] = manifest['commit']
        source = out / 'source'; source.mkdir(mode=0o700)
        for entry in manifest['files']:
            relative = Path(entry['path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise RuntimeError('Unsafe source manifest path')
            original = args.source_tree / relative
            if original.is_symlink() or entry['mode'] not in {'100644', '100755'}:
                raise RuntimeError('Unsupported source file mode')
            data = original.read_bytes()
            observed = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if observed != entry['git_blob']:
                raise RuntimeError('Pristine pinned source required: ' + entry['path'])
            destination = source / relative; destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data); destination.chmod(0o755 if entry['mode'] == '100755' else 0o644)
        report['source_blobs_verified'] = len(manifest['files'])
        if args.app == 'ntfy':
            patch = ROOT / 'fixtures/ntfy/matrixone-runtime.patch'
            report['patch_sha256'] = digest(patch)
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=source, check=True, capture_output=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True, capture_output=True)
            placeholders = ['server/site/index.html', 'server/docs/index.html']
            package = '.'
            tags = 'nofirebase,nopayments,sqlite_omit_load_extension,osusergo,netgo'
            ldflags = '-s -w -X main.version=2.29.0-matrixone -X main.commit=' + manifest['commit']
        else:
            placeholders = ['server/frontend/dist/index.html']
            package, tags = './cmd/memos', ''
            ldflags = ('-s -w -X github.com/usememos/memos/internal/version.Version=26.10 '
                       '-X github.com/usememos/memos/internal/version.Commit=' + manifest['commit'])
        for relative in placeholders:
            path = source / relative; path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text('<!doctype html><title>Native API regression fixture</title>')
        cache = out / 'cache'; cache.mkdir(mode=0o700)
        env = {**os.environ, 'GOTOOLCHAIN': 'local', 'GOWORK': 'off', 'GOMAXPROCS': '2',
               'GOMEMLIMIT': '900MiB', 'CGO_ENABLED': '0', 'GOMODCACHE': str(cache / 'mod'),
               'GOCACHE': str(cache / 'build'), 'GOPATH': str(cache / 'gopath')}
        binary = out / args.app
        command = [args.go, 'build', '-p', '2', '-mod=readonly', '-buildvcs=false', '-trimpath',
                   '-ldflags', ldflags, '-o', str(binary)]
        if tags:
            command += ['-tags', tags]
        command += [package]
        report['build_started'] = True
        with os.fdopen(os.open(out / 'build.log', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as log:
            process = subprocess.Popen(command, cwd=source, env=env, stdout=log, stderr=log, start_new_session=True)
            started = time.monotonic()
            while process.poll() is None:
                if shutil.disk_usage(out).free < 2 * 1024**3 or time.monotonic() - started > 1800:
                    report['blocked_reason'] = 'Build disk/time resource guard stopped this owned process group'
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
                    raise RuntimeError(report['blocked_reason'])
                time.sleep(.5)
        report['build_exit'] = process.returncode
        if process.returncode != 0:
            raise RuntimeError('Native Go build failed; private log retained')
        binary.chmod(0o700)
        report['binary_sha256'] = digest(binary)
        report['binary_name'] = binary.name
        report['passed'] = True; report['exit_code'] = 0
    except Exception as exc:
        report['error_type'] = type(exc).__name__
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
        report['time_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        (out / 'build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report.get(key) for key in ['app', 'passed', 'build_started', 'exit_code', 'blocked_reason']}))
    return report['exit_code']


def verified_binary(path, legacy_sha, manifest_path, app):
    """Bind either the historical pinned binary or a reviewed SDK build to its manifest."""
    observed = digest(path)
    if observed == legacy_sha:
        return {'sha256': observed, 'provenance': 'historical_pinned_source_build'}
    if manifest_path:
        report = json.loads(Path(manifest_path).read_text())
        expected = json.loads((ROOT / 'fixtures' / app / 'source-manifest.json').read_text())
        valid = report.get('passed') is True and report.get('build_exit') == 0 and report.get('app') == app
        valid = valid and report.get('commit') == expected['commit'] and report.get('binary_sha256') == observed
        valid = valid and report.get('source_blobs_verified') == len(expected['files']) and report.get('go_version', '').startswith('go version go1.27.1 ')
        if app == 'ntfy':
            valid = valid and report.get('patch_sha256') == digest(ROOT / 'fixtures/ntfy/matrixone-runtime.patch')
        if valid:
            return {'sha256': observed, 'provenance': 'prepared_SDK_build_manifest', 'commit': report['commit']}
    raise RuntimeError('Binary differs from pinned source build; valid prepared SDK build manifest required')


if __name__ == '__main__':
    raise SystemExit(main())
