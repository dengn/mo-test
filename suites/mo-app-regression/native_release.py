"""Copy only files of a digest-pinned official tar release into a new app directory."""
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

from native_common import digest, private_file


def php_literal(value):
    if isinstance(value, bool):return str(value).lower()
    if isinstance(value, int):return str(value)
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


def tar_release(provided, private, url, sha, prefix, count, fixture, max_bytes=100 * 1024**2, max_archive_bytes=16 * 1024**2, excluded_package_entries=()):
    archive = provided
    if not archive:
        archive = private / 'official.tar'
        with urllib.request.urlopen(url, timeout=90) as response:
            private_file(archive, response.read(max_archive_bytes + 1))
    if digest(archive) != sha:raise RuntimeError('Pinned release archive digest mismatch')
    app = private / 'app'; app.mkdir(mode=0o700); actual = 0; expanded = 0
    with tarfile.open(archive) as tar:
        for member in tar:
            if member.isdir():continue
            if member.isfile() and member.name in excluded_package_entries:continue
            if not member.isfile() or not member.name.startswith(prefix):raise RuntimeError('Unexpected release entry')
            relative = Path(member.name[len(prefix):])
            if relative.is_absolute() or '..' in relative.parts:raise RuntimeError('Unsafe release path')
            expanded += member.size
            if expanded > max_bytes:raise RuntimeError('Expanded release exceeds bound')
            path = app / relative; path.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(member) as source, path.open('xb') as target:shutil.copyfileobj(source,target)
            path.chmod(0o755 if member.mode & 0o111 else 0o644); actual += 1
    if actual != count:raise RuntimeError('Pinned release file count mismatch')
    manifest = json.loads((fixture/'adaptation-manifest.json').read_text())
    for entry in manifest['files']:
        source = app / entry['path']; adapted = fixture/'adapted'/entry['path']
        if (entry['original_sha256'] is None and source.exists()) or (entry['original_sha256'] is not None and digest(source) != entry['original_sha256']):
            raise RuntimeError('Pinned original adaptation source mismatch')
        if digest(adapted) != entry['adapted_sha256']:raise RuntimeError('Pinned adapted source mismatch')
        source.parent.mkdir(parents=True,exist_ok=True); source.write_bytes(adapted.read_bytes())
    return app,actual
