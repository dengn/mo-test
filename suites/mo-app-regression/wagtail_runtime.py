"""Verify a prepared Wagtail wheel SDK and install a fresh isolated fixture."""
import json
from pathlib import Path

from native_common import digest

ROOT = Path(__file__).resolve().parent


def prepare(config_path: Path, private: Path) -> tuple[Path, Path, dict]:
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text())
    python = Path(config['python_binary'])
    python = (python if python.is_absolute() else config_path.parent / python).absolute()
    sdk = python.parent.parent.resolve()
    fixture = ROOT / 'fixtures/wagtail'
    manifest = json.loads((fixture / 'sdk-manifest.json').read_text())
    if digest(python.resolve()) != manifest['python_sha256']:
        raise RuntimeError('Prepared Wagtail interpreter differs')
    for entry in manifest['files']:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Unsafe Wagtail SDK manifest path')
        path = sdk / relative
        if path.is_symlink() or path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            raise RuntimeError('Prepared Wagtail SDK differs: ' + str(relative))
    migration = sdk / 'lib/python3.12/site-packages/wagtail/migrations/0086_populate_grouppagepermission_permission.py'
    if migration.read_bytes() != (fixture / 'migration-0086-adapted.py').read_bytes():
        raise RuntimeError('Prepared Wagtail migration differs from reviewable adaptation')
    app = private / 'app'
    app.mkdir(mode=0o700)
    for entry in json.loads((fixture / 'project-manifest.json').read_text())['files']:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Unsafe Wagtail fixture path')
        source = fixture / 'project' / relative
        if source.is_symlink() or digest(source) != entry['sha256']:
            raise RuntimeError('Wagtail fixture differs: ' + str(relative))
        target = app / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    return python, app, {
        'version': manifest['version'], 'source_commit': manifest['source_commit'],
        'dependency_packages_verified': len(manifest['packages']),
        'dependency_files_verified': len(manifest['files']),
        'official_wheel_sha256': manifest['official_wheel_sha256'],
        'official_wheel_files_audited': manifest['official_wheel_files_audited'],
        'modified_wheel_files': manifest['modified_wheel_files'],
        'sdk_manifest_sha256': digest(fixture / 'sdk-manifest.json'),
        'project_manifest_sha256': digest(fixture / 'project-manifest.json'),
        'cold_install_verified': False,
    }
