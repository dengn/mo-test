import sys,json,pathlib,datetime,decimal,base64
B=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(B.parent/'etl-10000'))
import matrix as m

def enc(v):
 if isinstance(v,decimal.Decimal):return {'kind':'decimal','value':str(v)}
 if isinstance(v,datetime.datetime):return {'kind':'datetime','value':v.isoformat()}
 if isinstance(v,datetime.date):return {'kind':'date','value':v.isoformat()}
 if isinstance(v,datetime.timedelta):return {'kind':'duration','value':(v.days*86400+v.seconds)*1000000+v.microseconds}
 if isinstance(v,bytes):return {'kind':'bytes','value':v.hex()}
 return v
cases=[]
for pi,p in enumerate(m.PROFILES):
 for si,sc in enumerate(m.SCENARIOS):
  for seed in range(10):
   cid=1+(pi*5+si)*10+seed;rows=m.base_rows(cid,p,seed);expected=[r.copy() for r in rows];changes=[];dead=[]
   if sc=='native_transform':expected=[[a,i,v,l+'→ETL'+str(seed),r+seed+1] for a,i,v,l,r in rows if i%2==seed%2]
   if sc=='staging_merge':
    extra=m.values(p,seed+11);changes=[[cid,1,extra[0],'更新😀'+str(seed),1],[cid,3,extra[1],'更新😀'+str(seed),1],[cid,len(rows),extra[2],'新增😀'+str(seed),1]];byid={x[1]:x for x in rows};byid.update({x[1]:x for x in changes});expected=list(byid.values())
   if sc=='tombstone_delete':dead=[1,len(rows)-2];expected=[r for r in rows if r[1] not in dead]
   cases.append({'logical_case_id':cid,'profile':p['name'],'ddl':p['ddl'],'scenario':sc,'seed':seed,'rows':[[enc(v) for v in r] for r in rows],'changes':[[enc(v) for v in r] for r in changes],'dead':dead,'expected':m.canon(expected,p),'expected_sha256':m.sha(m.canon(expected,p))})
(B/'fixtures.json').write_text(json.dumps(cases,ensure_ascii=False,separators=(',',':')))
plan=[{'id':f'{comp}_{c["profile"]}_{c["scenario"]}_{c["seed"]}_{port}','component':comp,'port':port,'logical_case_id':c['logical_case_id'],'profile':c['profile'],'scenario':c['scenario'],'seed':c['seed']} for comp in ['airflow','dolphinscheduler','dbt','airbyte','fivetran'] for c in cases for port in [6001,13306]]
(B/'case-plan.json').write_text(json.dumps({'planned':10000,'definition':'5 real component routes x20 original SQL type profiles x5 scenarios x10 deterministic seeds x2 endpoints. Case = one scenario and datatype oracle, not a separate DAG run or failure injection. First10k cases excluded. Fivetran endpoints are sources, local DuckDB tester is destination. Airbyte string envelope outbox to native raw destination; no CDC delete certification.','cases':plan},ensure_ascii=False,indent=2))
for port in [6001,13306]:
 m.sql('CREATE DATABASE IF NOT EXISTS orchestrator10000',port=port,database=None)
 for comp in ['airflow','dolphinscheduler','dbt','fivetran']:
  for p in m.PROFILES:
   t=comp+'_'+p['name'];m.sql('CREATE TABLE IF NOT EXISTS '+t+'(case_id BIGINT,id BIGINT,v '+p['ddl']+',label VARCHAR(256),rev BIGINT,PRIMARY KEY(case_id,id))',port=port,database='orchestrator10000')
   if comp in ['dbt','fivetran']:
    rows=[]
    for c in cases:
     if c['profile']!=p['name']:continue
     for r in c['rows']:rows.append([decode if False else r[0],r[1],r[2],r[3],r[4]])
    # Native source tables for these components start from the actual typed boundary fixtures.
    rows=[m.base_rows(c['logical_case_id'],p,c['seed']) for c in cases if c['profile']==p['name']];rows=[r for group in rows for r in group]
    with m.db(port,'orchestrator10000',autocommit=False) as d,d.cursor() as cur:
     cur.execute('DELETE FROM '+t);cur.executemany('INSERT INTO '+t+' VALUES(%s,%s,%s,%s,%s)',rows);d.commit()
print('GENERATED',len(cases),'logical cases',len(plan),'endpoint assertions',flush=True)
