"""ZIP with all exact model binaries, hashes, inputs, code and result evidence."""
import hashlib,json,zipfile
from pathlib import Path
from data import ROOT
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 out=ROOT/'matrixone-deep-ml.zip';files=[]
 for p in sorted(ROOT.rglob('*')):
  if not p.is_file():continue
  rel=p.relative_to(ROOT);parts=rel.parts
  if any(x in ['__pycache__','mpl-cache'] for x in parts) or p==out or p.name in ['artifact-manifest.json','package-meta.json','packaging.log']:continue
  if p.name.startswith('main-worker-') and len(parts)==1:continue
  files.append(p)
 manifest={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=digest(p)) for p in files};(ROOT/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2));files.append(ROOT/'artifact-manifest.json')
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for p in files:z.write(p,p.relative_to(ROOT))
 with zipfile.ZipFile(out) as z:
  assert z.testzip() is None
  for rel,m in manifest.items():
   h=hashlib.sha256()
   with z.open(rel) as f:
    for b in iter(lambda:f.read(1048576),b''):h.update(b)
   assert h.hexdigest()==m['sha256'],rel
 meta=dict(path=str(out),bytes=out.stat().st_size,sha256=digest(out),entries=len(files),canonical_models=20000,crc_verified=True,all_manifest_hashes_verified=True);(ROOT/'package-meta.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta))
if __name__=='__main__':main()
