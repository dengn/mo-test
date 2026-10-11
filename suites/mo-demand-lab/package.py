import hashlib,json,zipfile
from pathlib import Path
from data import ROOT
from catalog import catalog
(ROOT/'business-scenario-catalog.json').write_text(json.dumps(catalog(),ensure_ascii=False,indent=2))
manifest={}
for p in ROOT.rglob('*'):
 if p.parent==ROOT/'results/canonical' and p.name.startswith('cases-'):continue
 if p.is_file() and not any(s in p.parts for s in ['__pycache__','mpl-cache']) and p.suffix!='.zip' and p.name not in ['artifact-manifest.json','package-meta.json']:manifest[str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
for p in Path('/workspace/mo-ds-lab/jars').glob('*.jar'):manifest['jars/'+p.name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(ROOT/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2))
zip_path=ROOT/'matrixone-demand-10000.zip'
with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted(ROOT.rglob('*')):
  if p.is_file() and not any(s in p.parts for s in ['__pycache__','mpl-cache']) and p.suffix!='.zip' and p.name!='package-meta.json':
   # cases.jsonl has the full canonical payload; worker shards are a duplicate.
   if p.parent==ROOT/'results/canonical' and p.name.startswith('cases-'):continue
   z.write(p,'mo-demand-lab/'+str(p.relative_to(ROOT)))
 for p in Path('/workspace/mo-ds-lab/jars').glob('*.jar'):z.write(p,'mo-demand-lab/jars/'+p.name)
with zipfile.ZipFile(zip_path) as z:
 assert z.testzip() is None;files=len(z.namelist())
 for name,entry in manifest.items():assert hashlib.sha256(z.read('mo-demand-lab/'+name)).hexdigest()==entry['sha256'],name
meta={'path':str(zip_path),'bytes':zip_path.stat().st_size,'files':files,'sha256':hashlib.sha256(zip_path.read_bytes()).hexdigest(),'crc':'pass','canonical_payload':'cases.jsonl; duplicate worker shards excluded from zip'}
(ROOT/'package-meta.json').write_text(json.dumps(meta,indent=2));print(meta)
