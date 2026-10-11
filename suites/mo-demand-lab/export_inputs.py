import hashlib,json
from data import ROOT,tables
out=ROOT/'inputs';out.mkdir(exist_ok=True);manifest=json.loads((ROOT/'dataset-manifest.json').read_text())
for name,frame in tables().items():
 assert hashlib.sha256(frame.to_csv(index=False,float_format='%.12g').encode()).hexdigest()==manifest['tables'][name]['sha256']
 frame.to_csv(out/(name+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
print('30 input tables exported; normalized setup hashes verified')
