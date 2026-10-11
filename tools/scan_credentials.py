#!/usr/bin/env python3
"""Check publishable files without printing possible credential material."""
import gzip,tarfile,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
patterns=[re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}')]
hits=[];scanned=0
def scan(data,path):
 global scanned
 scanned+=1
 if not any(n in data for n in [b'PRIVATE KEY-----',b'github_pat_',b'ghp_',b'gho_',b'ghu_',b'ghs_',b'ghr_']):return
 for i,p in enumerate(patterns):
  if p.search(data):hits.append({'path':path,'pattern_index':i})
for f in root.rglob('*'):
 if not f.is_file() or '.git' in f.parts:continue
 if f.name.endswith('.tar.gz'):
  with tarfile.open(f,'r:gz') as t:
   for m in t:
    if m.isfile() and Path(m.name).suffix in ['.py','.go','.sh','.sql','.md','.json','.jsonl','.txt','.toml']:
     scan(t.extractfile(m).read(),str(f.relative_to(root))+':'+m.name)
 elif f.suffix=='.gz':
  with gzip.open(f,'rb') as g:
   previous=b''
   for block in iter(lambda:g.read(2*1024*1024),b''):
    scan(previous+block,str(f.relative_to(root)));previous=block[-256:]
 elif f.suffix in ['.py','.go','.sh','.sql','.md','.json','.jsonl','.txt','.toml','.log']:
  scan(f.read_bytes(),str(f.relative_to(root)))
print({'scanned_text_units':scanned,'credential_pattern_hits':hits})
if hits:raise SystemExit(1)
