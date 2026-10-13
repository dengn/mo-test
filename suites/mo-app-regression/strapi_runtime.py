"""Verify a prepared Strapi SDK; create a fresh scaffold without old .env/state."""
import json
from pathlib import Path
import shutil

from native_common import digest

ROOT=Path(__file__).resolve().parent


def prepare(config_path: Path, private: Path) -> tuple[Path, Path, dict]:
    config_path=config_path.resolve();cfg=json.loads(config_path.read_text())
    def location(key: str) -> Path:
        p=Path(cfg[key]);return (p if p.is_absolute() else config_path.parent/p).resolve()
    node=location('node_binary');sdk=location('sdk_dir');fixture=ROOT/'fixtures/strapi'
    manifest=json.loads((fixture/'sdk-manifest.json').read_text())
    if digest(node)!=manifest['node_sha256']:raise RuntimeError('Pinned Node24.20 binary required')
    for f in manifest['files']:
        rel=Path(f['path']);p=sdk/rel
        if rel.is_absolute() or '..' in rel.parts or p.is_symlink() or p.stat().st_size!=f['bytes'] or digest(p)!=f['sha256']:
            raise RuntimeError('Prepared Strapi SDK differs: '+str(rel))
    for link in manifest['symlinks']:
        p=sdk/link['path']
        if not p.is_symlink() or str(p.readlink())!=link['target'] or not p.resolve().is_relative_to((sdk/'node_modules').resolve()):
            raise RuntimeError('Prepared Strapi dependency link differs')
    app=private/'app';app.mkdir(mode=0o700)
    scaffold=json.loads((fixture/'scaffold-manifest.json').read_text())
    for entry in scaffold['files']:
        rel=Path(entry['path']);source=fixture/'scaffold'/rel
        if source.stat().st_size!=entry['bytes'] or digest(source)!=entry['sha256']:raise RuntimeError('Pinned scaffold differs')
        target=app/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    for entry in scaffold['compiled_admin_assets']:
        rel=Path(entry['path']);source=sdk/rel
        if source.is_symlink() or source.stat().st_size!=entry['bytes'] or digest(source)!=entry['sha256']:raise RuntimeError('Pinned original admin build differs')
        target=app/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    (app/'public/uploads').mkdir(parents=True,mode=0o700)
    (app/'node_modules').symlink_to(sdk/'node_modules',target_is_directory=True)
    return node,app,{'version':manifest['version'],'dependency_files_verified':len(manifest['files']),
                    'dependency_links_verified':len(manifest['symlinks']),'scaffold_files_verified':len(scaffold['files']),
                    'admin_asset_files_verified':len(scaffold['compiled_admin_assets']),
                    'sdk_manifest_sha256':digest(fixture/'sdk-manifest.json'),'cold_install_verified':False}
