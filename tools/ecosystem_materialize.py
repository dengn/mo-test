#!/usr/bin/env python3
"""Verify/restore this session separately from existing mo-test manifests."""
import argparse,collections,gzip,hashlib,json,shutil,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
SUITE=ROOT/'suites/mo-ecosystem-session'
def sha_file(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def safe_member(name):
 p=PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts or '\\' in name or not p.parts:raise ValueError('Unsafe archive member path')
 return p
def verify():
 manifest=json.loads((SUITE/'artifact-manifest.json').read_text())
 for e in manifest['files']:
  p=ROOT/e['path']
  if p.stat().st_size!=e['bytes'] or sha_file(p)!=e['sha256']:raise ValueError('Artifact digest mismatch: '+e['path'])
 m=json.loads((SUITE/'source-manifest.json').read_text())
 a=json.loads((SUITE/'archive-manifest.json').read_text())['archives']
 by_archive=collections.defaultdict(dict)
 for e in m['members']:by_archive[e['archive']][e['member']]=e
 # Retain main-group source receipts for an independent index/line audit.
 source_paths={e['source_member'] for e in read_catalog('executed-main.jsonl.gz')}
 original={}
 for archive in a:
  p=SUITE/archive['path']
  if sha_file(p)!=archive['sha256']:raise ValueError('Archive digest mismatch')
  expected=by_archive[archive['path']]
  with zipfile.ZipFile(p) as z:
   names=z.namelist()
   if len(names)!=len(set(names)) or set(names)!=set(expected):raise ValueError('Unexpected or duplicate archive members')
   for info in z.infolist():
    safe_member(info.filename)
    if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Archive symlink rejected')
    data=z.read(info) # also validates CRC
    if hashlib.sha256(data).hexdigest()!=expected[info.filename]['published_sha256']:raise ValueError('Member digest mismatch')
    if info.filename in source_paths:original[info.filename]=[json.loads(l) for l in data.decode().splitlines()]
    e=expected[info.filename]
    if 'browse_path' in e and (SUITE/e['browse_path']).read_bytes()!=data:raise ValueError('Frozen source differs from archive')
 main_seen=set();group_counts=collections.Counter()
 for e in read_catalog('executed-main.jsonl.gz'):
  key=(e['batch'],e['id'])
  if key in main_seen:raise ValueError('Duplicate main case ID')
  main_seen.add(key)
  row=original[e['source_member']][e['source_line']-1]
  for field in ['id','status','profile','scenario','seed']:
   if row.get(field)!=e.get(field):raise ValueError('Catalog/source field mismatch: '+field)
  group_counts[e['batch']]+=1
 if dict(group_counts)!={'etl-10000':10000,'etl-orchestrators-10000':10000,'heavy-5000':27559}:raise ValueError('Main case count mismatch')
 planned=collections.Counter();plan_seen=set()
 for e in read_catalog('heavy-planned.jsonl.gz'):
  key=(e['tool'],e['id'])
  if key in plan_seen:raise ValueError('Duplicate planned ID')
  plan_seen.add(key);planned[e['tool']]+=1
 if len(planned)!=32 or set(planned.values())!={5000}:raise ValueError('Heavy plan count mismatch')
 print(json.dumps({'verified_files':len(manifest['files']),'archive_members':len(m['members']),
  'executed_main':dict(group_counts),'heavy_planned':sum(planned.values()),'status':'verified'},ensure_ascii=False))
 return a
def read_catalog(name):
 with gzip.open(SUITE/'catalog'/name,'rt') as f:
  for line in f:yield json.loads(line)
def restore(archives,output,batch):
 output=output.resolve()
 # Preflight every selected destination before writing any archive member.
 selected=[e for e in archives if batch is None or e['batch']==batch]
 if not selected:raise ValueError('Unknown batch')
 for e in selected:
  if (output/e['batch']).exists():raise ValueError('Refusing to overwrite existing batch: '+e['batch'])
 output.mkdir(parents=True,exist_ok=True)
 for e in selected:
  with zipfile.ZipFile(SUITE/e['path']) as z:
   for info in z.infolist():
    rel=safe_member(info.filename);dst=output.joinpath(*rel.parts)
    # No archive directories or symlinks are accepted by the packer/verifier.
    dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.resolve().is_relative_to(output) is False:raise ValueError('Extraction path escaped output')
    with z.open(info) as src,dst.open('xb') as out:shutil.copyfileobj(src,out)
 print('Restored',len(selected),'batches; no test code or service lifecycle executed')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--verify-only',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--batch')
 a=p.parse_args()
 if not a.verify_only and a.output is None:p.error('provide --output or --verify-only')
 archives=verify()
 if not a.verify_only:restore(archives,a.output,a.batch)
if __name__=='__main__':main()
