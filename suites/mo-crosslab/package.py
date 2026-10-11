import hashlib,json,zipfile
from pathlib import Path
from data import ROOT
path=ROOT/'matrixone-cross-domain-complex.zip';excluded={'artifact-manifest.json','package-meta.json'}
files={}
for file in sorted(ROOT.rglob('*')):
    if not file.is_file() or any(v in file.parts for v in ['__pycache__','mpl-cache']) or file.suffix=='.zip' or file.name in excluded:continue
    if file.parent==ROOT/'results/canonical' and file.name.startswith('cases-'):continue
    files[str(file.relative_to(ROOT))]=file
jar=Path('/workspace/mo-ds-lab/jars/mysql-connector-j-8.0.33.jar');files['jars/'+jar.name]=jar
manifest={name:{'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()} for name,file in files.items()}
(ROOT/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2));files['artifact-manifest.json']=ROOT/'artifact-manifest.json'
with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,file in files.items():z.write(file,'mo-crosslab/'+name)
with zipfile.ZipFile(path) as z:
    assert z.testzip() is None
    for name,entry in manifest.items():assert hashlib.sha256(z.read('mo-crosslab/'+name)).hexdigest()==entry['sha256'],name
meta={'path':str(path),'bytes':path.stat().st_size,'files':len(files),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'crc':'pass','file_sha256':'pass','master_main_payload':'cases.jsonl (worker duplicates excluded)'}
(ROOT/'package-meta.json').write_text(json.dumps(meta,indent=2));print(meta)
