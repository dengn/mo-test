import sys,json,uuid,datetime,decimal,hashlib
from pathlib import Path
sys.path.insert(0,'/workspace/work/heavy-5000');sys.path.append('/workspace/toolchains/python/lib/python3.12/site-packages')
from heavy import PROFILES,canon,sha
from pyiceberg.catalog import load_catalog
decimal.getcontext().prec=100
B=Path(__file__).resolve().parent;P=B/'fivetran-project';P.mkdir(exist_ok=True)
R=Path('/workspace/work/heavy-5000/iceberg-native-preflight');pre=json.loads((R/'results.json').read_text());assert pre['counts']=={'passed':50}
catalog=load_catalog('heavy_preflight',type='sql',uri='sqlite:///'+str(R/'catalog.db'),warehouse='file://'+str(R/'warehouse'));profiles={p['name']:p for p in PROFILES}
jobs=[];sources=[]
for spec in pre['cases']:
 table=catalog.load_table(tuple(spec['identifier']));raw=table.scan().to_arrow().to_pylist();p=profiles[spec['profile']];rows=[]
 for r in raw:
  v=r['v']
  if v is not None:
   if p['name']=='time6':v=datetime.timedelta(microseconds=int(v))
   elif p['name']=='set':v=','.join(v)
   elif p['name']=='uuid_text':v=str(v) if isinstance(v,uuid.UUID) else str(uuid.UUID(bytes=bytes(v)))
  rows.append([r['case_id'],r['id'],v,r['label'],r['rev']])
 rows=canon(rows,p);assert sha(rows)==spec['expected_sha256']
 sources.append({'profile':p['name'],'endpoint':spec['port'],'rows':len(rows),'sha256':sha(rows),'source':'Preserved native Iceberg snapshot, previously full-value compared with SQL source; no live MO query this preflight'})
 for scene in ['upsert_replay','sparse_update','delete_reinsert','checkpoint_resume']:
  jobs.append({'case_id':len(jobs)+1,'id':f'sdk_preflight_{p["name"]}_{scene}_{spec["port"]}','profile':p['name'],'endpoint':spec['port'],'scenario':scene,'source_rows':rows})
(P/'fixtures.json').write_text(json.dumps(jobs,ensure_ascii=False)+'\n');(B/'source-verification.json').write_text(json.dumps({'verified':len(sources),'sources':sources,'scope':'Archived source only; original heavy plan remains pending'},ensure_ascii=False,indent=2)+'\n')
(P/'requirements.txt').write_text('fivetran-connector-sdk==2.12.1\n')
print('PREPARED',len(jobs),'native SDK local preflight cases;50 archived source hashes verified')
