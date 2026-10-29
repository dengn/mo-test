import sys,pathlib,json,pymysql,decimal
B=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(B))
from codec import canon
from fivetran_connector_sdk import Connector,Operations as op

def schema(configuration):return [{'table':'matrixone_cases','primary_key':['endpoint','case_id','row_id'],'columns':{'endpoint':'INT','case_id':'LONG','row_id':'LONG','profile':'STRING','payload':'STRING'}}]
def emit(port,c,r):return {'endpoint':port,'case_id':c['logical_case_id'],'row_id':r[1],'profile':c['profile'],'payload':json.dumps(r,ensure_ascii=False,separators=(',',':'))}
def update(configuration,state):
 decimal.getcontext().prec=80
 cs=json.loads((B/'fixtures.json').read_text());jobs=[(port,c) for port in [6001,13306] for c in cs];start=int(state.get('next_case',0));cons={}
 try:
  for idx,(port,c) in enumerate(jobs):
   if idx<start:continue
   if port not in cons:cons[port]=pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='orchestrator10000',charset='utf8mb4',autocommit=True,read_timeout=90)
   with cons[port].cursor() as cur:
    cur.execute('SELECT case_id,id,v,label,rev FROM fivetran_'+c['profile']+' WHERE case_id=%s ORDER BY id',(c['logical_case_id'],));rows=canon(cur.fetchall(),c['profile'])
    if c['scenario']=='native_transform':rows=[[r[0],r[1],r[2],r[3]+'→ETL'+str(c['seed']),r[4]+c['seed']+1] for r in rows if r[1]%2==c['seed']%2]
    for r in rows:op.upsert(table='matrixone_cases',data=emit(port,c,r))
    # An uncheckpointed, completed upsert is deliberately replayed on resume.
    flag=B/'fivetran-retry-injected'
    if idx==125 and configuration.get('inject_once')=='true' and not flag.exists():flag.write_text(str(idx));raise RuntimeError('Deliberate uncheckpointed SDK failure; resume must replay idempotently')
    if idx==250 and not (B/'fivetran-precision-retry-injected').exists():
     (B/'fivetran-precision-retry-injected').write_text(str(idx));raise RuntimeError('Deliberate uncheckpointed full-precision Decimal upsert replay')
    if c['scenario']=='staging_merge':
     cur.execute('SELECT case_id,id,v,label,rev FROM fivetran_delta_'+c['profile']+' WHERE case_id=%s ORDER BY id',(c['logical_case_id'],));changes=canon(cur.fetchall(),c['profile']);existing={r[1] for r in rows}
     for r in changes:
      if r[1] in existing:op.update(table='matrixone_cases',modified=emit(port,c,r))
      else:op.upsert(table='matrixone_cases',data=emit(port,c,r))
    if c['scenario']=='tombstone_delete':
     for rid in c['dead']:op.delete(table='matrixone_cases',keys={'endpoint':port,'case_id':c['logical_case_id'],'row_id':rid})
   if (idx+1)%25==0 or idx+1==len(jobs):op.checkpoint(state={'next_case':idx+1})
 finally:
  for d in cons.values():d.close()
connector=Connector(update=update,schema=schema)
