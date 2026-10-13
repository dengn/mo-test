"""Prepare a per-run Huginn source copy from a pinned source/dependency SDK."""
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
COMMIT = 'd6f25e28a36f360ad80c73445c3ce5229be7e538'


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def prepare(config_path, private):
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text())
    def location(key):
        path = Path(config[key])
        return (path if path.is_absolute() else config_path.parent / path).resolve()
    source = location('source_tree')
    target = private / 'app'
    target.mkdir(mode=0o700)
    patches = {'config/database.yml': ROOT / 'adapters/huginn/database.yml',
               'db/migrate/20140813110107_set_charset_for_mysql.rb': ROOT / 'adapters/huginn/set_charset_for_mysql.rb'}
    manifest = json.loads((ROOT / 'fixtures/huginn/source-manifest.json').read_text())
    if manifest['commit'] != COMMIT:
        raise RuntimeError('Pinned source manifest identity mismatch')
    for entry in manifest['files']:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Unsafe source manifest path')
        original = source / relative
        if original.is_symlink():
            raise RuntimeError('Unexpected source symlink')
        data = original.read_bytes()
        valid = blob(data) == entry['git_blob']
        if entry['path'] in patches:
            # Accept only the original pinned source or the exact committed adaptation.
            valid = valid or data == patches[entry['path']].read_bytes()
        if not valid:
            raise RuntimeError('Source file differs from pinned commit: ' + entry['path'])
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        destination.chmod(0o755 if entry['mode'] == '100755' else 0o644)
    for relative, patch in patches.items():
        shutil.copyfile(patch, target / relative)
    # Only explicitly selected precompiled assets, not .env, databases, logs or old app state.
    assets = location('assets_dir')
    if not any(assets.glob('.sprockets-manifest-*.json')):
        raise RuntimeError('Native assets must be precompiled for the pinned source')
    for path in assets.rglob('*'):
        if path.is_symlink():
            raise RuntimeError('Unexpected compiled asset symlink')
    shutil.copytree(assets, target / 'public/assets', dirs_exist_ok=True)
    paths = {key: location(key) for key in ['ruby_binary', 'bundle_binary', 'gem_home', 'bundle_path']}
    libraries = [str((Path(p) if Path(p).is_absolute() else config_path.parent / p).resolve())
                 for p in config.get('native_library_dirs', [])]
    public_env = {'PATH': str(paths['ruby_binary'].parent) + ':' + str(paths['bundle_binary'].parent) + ':' + os.environ.get('PATH', ''),
                  'GEM_HOME': str(paths['gem_home']), 'GEM_PATH': str(paths['gem_home']),
                  'GEM_SPEC_CACHE': str(private / 'gem-spec-cache'), 'BUNDLE_USER_HOME': str(private / 'bundler-user'),
                  'BUNDLE_APP_CONFIG': str(private / 'bundle-config'), 'BUNDLE_PATH': str(paths['bundle_path']),
                  'BUNDLE_WITHOUT': 'development:test', 'BUNDLE_FROZEN': 'true', 'BUNDLE_DEPLOYMENT': 'true',
                  'LD_LIBRARY_PATH': ':'.join(libraries), 'XDG_CACHE_HOME': str(private / 'cache'),
                  'XDG_CONFIG_HOME': str(private / 'config'), 'TMPDIR': str(private / 'tmp')}
    for key in ['GEM_SPEC_CACHE', 'BUNDLE_USER_HOME', 'BUNDLE_APP_CONFIG', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'TMPDIR']:
        Path(public_env[key]).mkdir(mode=0o700, parents=True, exist_ok=True)
    return target, paths, public_env, len(manifest['files'])
