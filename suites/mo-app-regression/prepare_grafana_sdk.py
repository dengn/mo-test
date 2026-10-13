"""Stream and verify the fixed official OSS release into a new, owned SDK directory."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

from native_common import digest

ROOT = Path(__file__).resolve().parent


def verify_release(directory):
    manifest=json.loads((ROOT/'fixtures/grafana/release-manifest.json').read_text())
    for entry in manifest['files']:
        relative=Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:raise RuntimeError('Unsafe release manifest path')
        source=directory/relative
        if source.is_symlink() or source.stat().st_size!=entry['bytes'] or digest(source)!=entry['sha256']:
            raise RuntimeError('Fixed official Grafana release differs: '+entry['path'])
    return manifest


def prepare(directory):
    manifest=json.loads((ROOT/'fixtures/grafana/release-manifest.json').read_text())
    directory.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if directory.exists():raise RuntimeError('SDK destination must be new')
    expected={e['path']:e for e in manifest['files']}; expanded=sum(e['bytes'] for e in expected.values())
    if shutil.disk_usage(directory.parent).free<expanded+2048*1024**2:raise RuntimeError('Release SDK requires full size plus 2 GiB reserve')
    directory.mkdir(mode=0o700);sha=hashlib.sha256();count=0;seen=set()
    class Reader(io.RawIOBase):
        def readable(self):return True
        def read(self,n=-1):
            nonlocal count
            data=self.source.read(n);sha.update(data);count+=len(data);return data
    try:
        with urllib.request.urlopen(manifest['official_release_url'],timeout=90) as response:
            reader=Reader();reader.source=response
            with tarfile.open(fileobj=reader,mode='r|gz') as tar:
                for member in tar:
                    if member.isdir():continue
                    prefix='grafana-13.2.3/'
                    if not member.isfile() or not member.name.startswith(prefix):raise RuntimeError('Unexpected official release entry')
                    relative=member.name[len(prefix):];entry=expected.get(relative)
                    if entry is None or relative in seen or member.size!=entry['bytes']:raise RuntimeError('Official release manifest differs')
                    if shutil.disk_usage(directory).free-member.size<2048*1024**2:raise RuntimeError('SDK disk reserve reached')
                    path=directory/relative;path.parent.mkdir(parents=True,exist_ok=True)
                    with tar.extractfile(member) as source,path.open('xb') as target:shutil.copyfileobj(source,target)
                    if digest(path)!=entry['sha256']:raise RuntimeError('Official release file digest mismatch')
                    path.chmod(0o755 if member.mode&0o111 else 0o644);seen.add(relative)
            while reader.read(1024**2):pass
        if count!=460956549 or sha.hexdigest()!=manifest['original_archive_sha256'] or set(expected)!=seen:
            raise RuntimeError('Complete official archive stream digest mismatch')
    except BaseException:
        # Preserve this owned incomplete SDK as evidence; it cannot pass verify_release.
        raise
    record={'repo':manifest['repo'],'version':manifest['native_release_version'],'commit':manifest['commit'],
            'archive_sha256':sha.hexdigest(),'stream_bytes':count,'verified_files':len(seen),'expanded_bytes':expanded,'passed':True}
    (directory/'sdk-preparation.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record));return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    prepare(parser.parse_args().out.resolve())
