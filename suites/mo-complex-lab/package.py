import hashlib,json,zipfile
from pathlib import Path
from data import ROOT,tables
from scenarios import SQL,SCIENCE,sql_for,label
# Inspectable dataset extracts; complete binary data are reproducible from seed.
(ROOT/'datasets').mkdir(exist_ok=True)
for name,df in tables().items():df.to_csv(ROOT/'datasets'/f'{name}.csv.gz',index=False,compression='gzip',float_format='%.17g')
(ROOT/'scenario-catalog.json').write_text(json.dumps([{'family':f,'name':label(f)[0],'category':label(f)[1],'sql_parameter_0':sql_for(f,0),'parameter_count':1000,'compute_scope':'MO SQL only' if f<80 else 'MO feature SQL -> NumPy numerical/ML client computation'} for f in range(100)],indent=2))
manifest={}
for p in ROOT.rglob('*'):
 if p.is_file() and not any(x in p.parts for x in ['__pycache__','mpl-cache']) and p.suffix!='.zip':manifest[str(p.relative_to(ROOT))]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
(ROOT/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2))
zip_path=ROOT/'matrixone-complex-100000.zip'
with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in sorted(ROOT.rglob('*')):
  if p.is_file() and not any(x in p.parts for x in ['__pycache__','mpl-cache']) and p.suffix!='.zip':z.write(p,'mo-complex-lab/'+str(p.relative_to(ROOT)))
 for p in Path('/workspace/mo-ds-lab/jars').glob('*.jar'):z.write(p,'mo-complex-lab/jars/'+p.name)
 for name in ['spark-isolation.md','tanh.md','reproduce_spark_and_tanh.py','fresh-reproduction.json']:
  p=Path('/workspace/mo-ds-lab/issues')/name
  if p.exists():z.write(p,'mo-complex-lab/issues/'+name)
with zipfile.ZipFile(zip_path) as z:assert z.testzip() is None;count=len(z.namelist())
meta={'path':str(zip_path),'bytes':zip_path.stat().st_size,'files':count,'sha256':hashlib.sha256(zip_path.read_bytes()).hexdigest(),'crc':'pass'}
(ROOT/'package-meta.json').write_text(json.dumps(meta,indent=2));print(meta)
