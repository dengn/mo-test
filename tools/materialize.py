#!/usr/bin/env python3
"""Verify checksums, expand all materialized cases, and restore support files."""
import argparse,gzip,hashlib,json,shutil,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--verify-only',action='store_true');a=ap.parse_args()
m=json.loads((ROOT/'manifest.json').read_text())
for entry in m['files']:
 p=ROOT/entry['path'];h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 if h.hexdigest()!=entry['sha256']:raise SystemExit('Checksum mismatch: '+entry['path'])
print('All checksums verified')
if a.verify_only:raise SystemExit(0)
a.output.mkdir(parents=True,exist_ok=True)
for pack in sorted((ROOT/'suites').iterdir()):
 dst=a.output/pack.name
 if dst.exists():raise SystemExit('Refusing to overwrite existing path: '+str(dst))
 dst.mkdir()
 for f in pack.rglob('*'):
  if not f.is_file() or any(x in ['cases','results','artifacts'] for x in f.relative_to(pack).parts[:-1]):continue
  rel=f.relative_to(pack);out=dst/rel;out.parent.mkdir(parents=True,exist_ok=True)
  if f.suffix=='.gz':
   out=out.with_suffix('')
   with gzip.open(f,'rb') as inp,out.open('wb') as dest:shutil.copyfileobj(inp,dest)
  else:shutil.copy2(f,out)
 for kind in ['cases','results']:
  files=sorted((pack/kind).glob('*.jsonl.gz'))
  if files:
   with (dst/(kind+'.jsonl')).open('wb') as out:
    for f in files:
     with gzip.open(f,'rb') as inp:shutil.copyfileobj(inp,out)
 for f in sorted((pack/'artifacts').glob('*.tar.gz')):
  sub=dst/('.' if f.name=='numpy-fixtures.tar.gz' else f.name[:-7]);sub.mkdir(parents=True,exist_ok=True)
  with tarfile.open(f,'r:gz') as tar:tar.extractall(sub,filter='data')
 for first in sorted((pack/'artifacts').glob('*.tar.gz.part0000')):
  prefix=first.name[:-9];sub=dst/('.' if prefix=='numpy-fixtures.tar.gz' else prefix[:-7]);sub.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryFile() as joined:
   for part in sorted(first.parent.glob(prefix+'.part*')):
    with part.open('rb') as data:shutil.copyfileobj(data,joined)
   joined.seek(0)
   with tarfile.open(fileobj=joined,mode='r:gz') as tar:tar.extractall(sub,filter='data')
 if pack.name in m['packs']:
  h=hashlib.sha256((dst/'cases.jsonl').read_bytes()).hexdigest()
  if h!=m['packs'][pack.name]['cases']['uncompressed_sha256']:raise SystemExit('Reassembled case digest mismatch: '+pack.name)
print('Restored',m['main_case_count'],'main cases into',a.output)
