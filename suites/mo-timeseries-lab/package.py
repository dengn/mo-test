"""Freeze the complete unique master case set and evidence into a verified ZIP."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT.parent/'matrixone-timeseries-10000.zip'
def digest(source):
 h=hashlib.sha256()
 with source.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def included(p):
 rel=p.relative_to(ROOT)
 if not p.is_file() or any(x in rel.parts for x in ['__pycache__','mpl-cache','cache']):return False
 if rel.as_posix() in ['artifact-manifest.json','package-meta.json','package.log']:return False
 if len(rel.parts)==3 and rel.parts[:2]==('results','canonical') and rel.name.startswith('cases-'):return False
 return True
def main():
 report=json.loads((ROOT/'report.json').read_text())
 for name,sha in report['canonical']['code'].items():assert digest(ROOT/name)==sha,name
 assert json.loads((ROOT/'render-validation.json').read_text())['all_passed']
 files=sorted(p for p in ROOT.rglob('*') if included(p))
 provenance=[dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=digest(p)) for p in files]
 (ROOT/'artifact-manifest.json').write_text(json.dumps(provenance,indent=2))
 with zipfile.ZipFile(ARCHIVE,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for p in files+[ROOT/'artifact-manifest.json']:z.write(p,ROOT.name+'/'+p.relative_to(ROOT).as_posix())
 print('Archive written',ARCHIVE.stat().st_size,flush=True)
 with zipfile.ZipFile(ARCHIVE) as z:
  assert z.testzip() is None
  for entry in provenance:
   h=hashlib.sha256()
   with z.open(ROOT.name+'/'+entry['path']) as f:
    while b:=f.read(1024*1024):h.update(b)
   assert h.hexdigest()==entry['sha256'],entry['path']
  meta=dict(archive_name=ARCHIVE.name,archive_bytes=ARCHIVE.stat().st_size,archive_sha256=digest(ARCHIVE),zip_prefix=ROOT.name+'/',zip_entries=len(z.infolist()),uncompressed_bytes=sum(i.file_size for i in z.infolist()),source_files=len(provenance),canonical_cases=10000,canonical_statuses=report['counts'],canonical_members=[ROOT.name+'/cases.jsonl'])
 (ROOT/'package-meta.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta),flush=True)
if __name__=='__main__':main()
