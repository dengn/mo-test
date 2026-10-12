"""5000 native Iceberg query checks; supplemental, not a replacement for writer plans."""
import sys,pathlib,decimal,json,time,collections,concurrent.futures,hashlib,datetime,uuid
sys.path.append('/workspace/toolchains/python/lib/python3.12/site-packages')
from heavy import *
from pyiceberg.catalog import load_catalog
from pyiceberg.expressions import And,EqualTo,GreaterThanOrEqual,LessThan,In,IsNull,NotNull
ROOT=B/'iceberg-native-preflight';pre=json.loads((ROOT/'results.json').read_text());assert pre['counts']=={'passed':50}
OUT=B/'iceberg-read-supplement';OUT.mkdir(exist_ok=True)
CAT=lambda:load_catalog('heavy_preflight',type='sql',uri='sqlite:///'+str(ROOT/'catalog.db'),warehouse='file://'+str(ROOT/'warehouse'))
catalog=CAT();tables_by_key={};source={}
profiles={p['name']:p for p in PROFILES}
for row in pre['cases']:
 p=profiles[row['profile']];key=(p['name'],row['port']);tables_by_key[key]=catalog.load_table(tuple(row['identifier']))
 pi=PROFILES.index(p);source[key]=sql('SELECT case_id,id,v,label,rev FROM t_petl_'+p['name']+' WHERE case_id=%s ORDER BY id',(100000+caseid(pi,0,0),),port=row['port'])
scenes=['full_scan','id_range','id_membership','sql_nulls','non_nulls','projection','limit','arrow_batches','parallel_partitions','snapshot_reopen']
def decode(v,p):
 if v is None:return None
 if p['name']=='time6':return datetime.timedelta(microseconds=int(v))
 if p['name']=='set':return ','.join(v)
 if p['name']=='uuid_text':return str(v) if isinstance(v,uuid.UUID) else str(uuid.UUID(bytes=bytes(v)))
 return v
def execute(spec):
 decimal.getcontext().prec=100;p=profiles[spec['profile']];key=(p['name'],spec['port']);t=tables_by_key[key];seed=spec['seed'];scene=spec['scenario'];expected=list(source[key]);s=time.monotonic();r=dict(spec)
 try:
  filt=None;selected=None;limit=None
  if scene=='id_range':
   lo=seed;hi=seed+12;filt=And(GreaterThanOrEqual('id',lo),LessThan('id',hi));expected=[x for x in expected if lo<=x[1]<hi]
  elif scene=='id_membership':
   ids=[i for i in range(32) if i%5==seed%5];filt=In('id',ids);expected=[x for x in expected if x[1] in ids]
  elif scene=='sql_nulls':filt=IsNull('v');expected=[x for x in expected if x[2] is None]
  elif scene=='non_nulls':filt=NotNull('v');expected=[x for x in expected if x[2] is not None]
  elif scene=='projection':selected=('id','v','rev')
  elif scene=='limit':limit=seed+1
  if scene=='snapshot_reopen':
   local=CAT();t=local.load_table(tuple(next(x['identifier'] for x in pre['cases'] if x['profile']==p['name'] and x['port']==spec['port'])))
   scan=t.scan(snapshot_id=t.current_snapshot().snapshot_id)
  else:scan=t.scan(**({'row_filter':filt} if filt is not None else {}),**({'selected_fields':selected} if selected else {}),**({'limit':limit} if limit else {}))
  if scene=='parallel_partitions':
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    futures=[pool.submit(lambda expr:t.scan(row_filter=expr).to_arrow().to_pylist(),expr) for expr in [LessThan('id',16),GreaterThanOrEqual('id',16)]]
    records=[v for f in futures for v in f.result()]
  elif scene=='arrow_batches':
   reader=scan.to_arrow_batch_reader();records=[x for batch in reader for x in batch.to_pylist()]
  else:records=scan.to_arrow().to_pylist()
  if scene=='projection':
   actual=[[int(x['id']),norm_v(decode(x['v'],p),p),int(x['rev'])] for x in sorted(records,key=lambda x:x['id'])]
   e=[[int(x[1]),norm_v(x[2],p),int(x[4])] for x in expected]
  else:
   actual_rows=[[x['case_id'],x['id'],decode(x['v'],p),x['label'],x['rev']] for x in records]
   if scene=='limit':
    # File/scan order is unspecified: validate cardinality, uniqueness and full
    # values against the independent SQL source, not a presumed row order.
    byid={x[1]:x for x in expected};assert len(actual_rows)==limit and len({x[1] for x in actual_rows})==limit
    expected=[byid[x[1]] for x in actual_rows]
   actual=canon(actual_rows,p);e=canon(expected,p)
  r.update(status='passed' if actual==e else 'fidelity_failed',actual_rows=len(actual),expected_rows=len(e),actual_sha256=sha(actual),expected_sha256=sha(e))
  if actual!=e:r.update(actual_sample=actual[:1],expected_sample=e[:1])
 except Exception as e:r.update(status='execution_failed',error=repr(e))
 r['elapsed_s']=time.monotonic()-s;return r
plan=[{'id':f'iceberg_read_{p["name"]}_{scene}_{seed}_{role}','profile':p['name'],'scenario':scene,'seed':seed,'port':role,'scope':'Native Iceberg read-only supplemental; physical32-row typed sources; not main5000writer/EOS plan'} for p in PROFILES for scene in scenes for seed in range(10) for role in [6001,13306]]
dump(OUT/'plan.json',{'cases':plan,'planned':5000,'separate_from_main_heavy_plan':True})
file=OUT/'results.jsonl';done={json.loads(l)['id']:json.loads(l) for l in file.read_text().splitlines()} if file.exists() else {};counts=collections.Counter(x['status'] for x in done.values());start=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for pi,p in enumerate(PROFILES):
  jobs=[pool.submit(execute,s) for s in plan if s['profile']==p['name'] and s['id'] not in done]
  for f in concurrent.futures.as_completed(jobs):
   r=f.result();assert r['id'] not in done
   with file.open('a') as out:out.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
   done[r['id']]=r;counts[r['status']]+=1
   if r['status']!='passed':print('FAIL',r['id'],r.get('error',''),flush=True)
   if len(done)%100==0:print('ICEBERG_READ',len(done),dict(counts),flush=True)
dump(OUT/'completion.json',{'completed':len(done),'counts':dict(counts),'elapsed_s':time.monotonic()-start,'scope':'5000 supplementary real native typed Iceberg scans; does not reduce original pending heavy write/recovery cases','old_data_retained':True})
print('SUPPLEMENT_FINAL',len(done),dict(counts),flush=True)
