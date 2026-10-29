import json,pathlib,hashlib
from fivetran_connector_sdk import Connector,Operations as op
B=pathlib.Path(__file__).resolve().parent
def schema(configuration):
 cols={'endpoint':'INT','case_id':'LONG','row_id':'LONG','profile':'STRING','scenario':'STRING','payload':'STRING','rev':'LONG'}
 if configuration.get('phase')=='evolve':cols['schema_epoch']='STRING'
 return [{'table':'ecosystem_sdk_preflight','primary_key':['endpoint','case_id','row_id'],'columns':cols}]
def data(c,r):return {'endpoint':c['endpoint'],'case_id':c['case_id'],'row_id':r[1],'profile':c['profile'],'scenario':c['scenario'],'payload':json.dumps(r,ensure_ascii=False,separators=(',',':')),'rev':r[4]}
def expected(c):
 rows={r[1]:r.copy() for r in c['source_rows']}
 if c['scenario']=='sparse_update':
  for i,r in rows.items():
   if i%3==0:r[3]+='→SDK更新';r[4]+=10
 if c['scenario']=='delete_reinsert':
  for i in list(rows):
   if i%2:
    if i%4==1:rows[i][3]+='→删除后重插';rows[i][4]+=2
    else:del rows[i]
 return [rows[i] for i in sorted(rows)]
def update(configuration,state):
 jobs=json.loads((B/'fixtures.json').read_text());phase=configuration['phase'];start=int(state.get('next_case',0))
 with (B/f'operations-{phase}.jsonl').open('a') as log:
  for idx,c in enumerate(jobs):
   if idx<start:continue
   if phase=='evolve':
    for r in expected(c):
     d=data(c,r);op.update(table='ecosystem_sdk_preflight',modified={'endpoint':d['endpoint'],'case_id':d['case_id'],'row_id':d['row_id'],'schema_epoch':'v2'})
   else:
    for n,r in enumerate(c['source_rows']):
     op.upsert(table='ecosystem_sdk_preflight',data=data(c,r))
     if idx==13 and n==7 and configuration.get('inject')=='true':raise RuntimeError('Injected after8 upserts of uncheckpointed case14; fresh process must resume durable checkpoint')
    if c['scenario']=='upsert_replay':
     for r in c['source_rows']:op.upsert(table='ecosystem_sdk_preflight',data=data(c,r))
    elif c['scenario']=='sparse_update':
     for r in expected(c):
      if r[1]%3==0:
       d=data(c,r);op.update(table='ecosystem_sdk_preflight',modified={k:d[k] for k in ['endpoint','case_id','row_id','payload','rev']})
    elif c['scenario']=='delete_reinsert':
     for r in c['source_rows']:
      if r[1]%2:op.delete(table='ecosystem_sdk_preflight',keys={'endpoint':c['endpoint'],'case_id':c['case_id'],'row_id':r[1]})
     for r in expected(c):
      if r[1]%4==1:op.upsert(table='ecosystem_sdk_preflight',data=data(c,r))
   log.write(json.dumps({'id':c['id'],'case_id':c['case_id'],'phase':phase,'expected_rows':len(expected(c))})+'\n');log.flush()
   if (idx+1)%10==0 or idx+1==len(jobs):op.checkpoint(state={'next_case':idx+1,'phase':phase})
connector=Connector(update=update,schema=schema)
