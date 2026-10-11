"""Export deterministic oracle inputs, with content hashes verified against setup."""
import hashlib,json
from data import ROOT,tables
manifest=json.loads((ROOT/'dataset-manifest.json').read_text());out=ROOT/'inputs';out.mkdir(exist_ok=True)
for name,frame in tables().items():
 raw=frame.to_csv(index=False,float_format='%.12g').encode();assert hashlib.sha256(raw).hexdigest()==manifest['tables'][name]['sha256'],name
 frame.to_csv(out/(name+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
print('14 deterministic source tables exported and hashed')
