"""Prepare verified Superset wheel dependencies and a private pinned core copy."""
import json
from pathlib import Path

from native_common import copy_pinned_source, digest

ROOT = Path(__file__).resolve().parent


def prepare(config_path: Path, private: Path) -> tuple[Path, Path, dict]:
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text())
    def location(key: str) -> Path:
        path = Path(config[key])
        # Preserve a venv's executable path instead of resolving its Python symlink.
        return (path if path.is_absolute() else config_path.parent / path).absolute()
    python = location('python_binary')
    sdk = python.parent.parent.resolve()
    source = location('source_tree')
    manifest = json.loads((ROOT / 'fixtures/superset/sdk-manifest.json').read_text())
    for entry in manifest['files']:
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Unsafe Superset SDK manifest path')
        path = sdk / relative
        if path.is_symlink() or path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            raise RuntimeError('Prepared Superset SDK differs: ' + str(relative))
    selector = sdk / 'lib/python3.12/site-packages' / manifest['editable_core_selector']
    if selector.read_text().strip() != str(source.resolve()/'superset-core/src'):
        raise RuntimeError('Editable core SDK selector does not match pinned source input')
    core = json.loads((ROOT / 'fixtures/superset/core-source-manifest.json').read_text())
    count = copy_pinned_source(source, private/'source', core)
    adapter = ROOT/'fixtures/superset/matrixone_adapter.py'
    (private/'matrixone_adapter.py').write_bytes(adapter.read_bytes())
    return python, private/'source/superset-core/src', {
        'app_version': manifest['version'], 'dependency_packages_verified': len(manifest['packages']),
        'dependency_files_verified': len(manifest['files']), 'core_git_blobs_verified': count,
        'core_commit': core['commit'], 'adapter_sha256': digest(adapter),
        'sdk_manifest_sha256': digest(ROOT/'fixtures/superset/sdk-manifest.json'),
        'cold_install_verified': False,
    }
