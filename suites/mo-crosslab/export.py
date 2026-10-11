import hashlib,json
from data import ROOT,tables
from graphs import query,QUESTIONS,params
out=ROOT/'inputs';out.mkdir(exist_ok=True);manifest={}
for name,frame in tables().items():
    path=out/(name+'.csv.gz');frame.to_csv(path,index=False,float_format='%.17g',compression={'method':'gzip','mtime':0})
    manifest[path.name]={'rows':len(frame),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
(ROOT/'input-artifacts.json').write_text(json.dumps(manifest,indent=2))
out=ROOT/'examples';out.mkdir(exist_ok=True)
for d in ['customer','product']:(out/(d+'-multi-table.sql')).write_text(query(d,249))
(ROOT/'requirements-catalog.json').write_text(json.dumps([{'family':f,'domain':d,'key':k,'question':q,'parameters_per_requirement':500} for f,(d,k,q) in enumerate(QUESTIONS)],ensure_ascii=False,indent=2))
print('exported',len(manifest),'source tables')
