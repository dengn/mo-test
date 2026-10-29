import pathlib,sys,json,collections,datetime
B=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(B.parent/'etl-10000'));import matrix as m
plan=json.loads((B/'case-plan.json').read_text());fixtures={c['logical_case_id']:c for c in json.loads((B/'fixtures.json').read_text())};build=json.loads((B/'dbt-build-receipts.json').read_text());success={6001:build[0]['exit_code']==0,13306:build[1]['exit_code']==0};out=[]
for port in [6001,13306]:
 for p in m.PROFILES:
  rows=m.sql('SELECT case_id,id,v,label,rev FROM out_'+p['name']+' ORDER BY case_id,id',port=port,database='orchestrator10000');byid=collections.defaultdict(list)
  for r in rows:byid[int(r[0])].append(r)
  for spec in plan['cases']:
   if spec['component']!='dbt' or spec['port']!=port or spec['profile']!=p['name']:continue
   cid=spec['logical_case_id'];actual=m.canon(byid[cid],p);expected=fixtures[cid]['expected'];r=dict(spec,status='passed' if actual==expected and success[port] else 'fidelity_failed',expected_rows=len(expected),actual_rows=len(actual),expected_sha256=fixtures[cid]['expected_sha256'],actual_sha256=m.sha(actual),execution_evidence=f'dbt-build-{"mo" if port==6001 else "mysql"}.log',scope='Native dbt table models rebuild actual typed source tables; scenario assertions within20 models, not1000 independent model invocations')
   if actual!=expected:r['expected_sample']=expected[:3];r['actual_sample']=actual[:3]
   out.append(r)
(B/'results-dbt.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,default=str)+'\n' for r in out));print('DBT ORACLE',len(out),dict(collections.Counter(r['status'] for r in out)),flush=True)
# Re-read every target table independently, checking full contents of each completed first-matrix case.
initial=B.parent/'etl-10000';receipts=[json.loads(l) for l in (initial/'results.jsonl').read_text().splitlines()];ids=[r['id'] for r in receipts];assert len(ids)==len(set(ids))==10000;assert {r['id'] for r in m.plan()}==set(ids)
checks=[]
for route in m.ROUTES:
 for p in m.PROFILES:
  t,_=m.tables(route,p)
  for port in [6001,13306]:
   rows=m.sql('SELECT case_id,id,v,label,rev FROM '+t+' WHERE case_id<=5000 ORDER BY case_id,id',port=port);byid=collections.defaultdict(list)
   for row in rows:byid[int(row[0])].append(row)
   relevant=[r for r in receipts if r['route']==route and r['profile']==p['name'] and r['port']==port]
   for r in relevant:
    actual=m.canon(byid.pop(r['logical_case_id'],[]),p);checks.append({'id':r['id'],'status':'passed' if m.sha(actual)==r['expected_sha256'] and len(actual)==r['expected_rows'] else 'failed','actual_rows':len(actual),'actual_sha256':m.sha(actual)})
   assert not byid,('unexpected case ids',t,port,list(byid))
(initial/'final-readback-audit.json').write_text(json.dumps({'checked':len(checks),'counts':dict(collections.Counter(x['status'] for x in checks)),'rows':sum(c['actual_rows'] for c in checks),'scope':'Full-table independent readback per endpoint and route after all writes; compares persisted oracle hashes, checks case ID uniqueness and extra rows. Not additional cases.','UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':checks},ensure_ascii=False,indent=2));print('FIRST FINAL AUDIT',len(checks),dict(collections.Counter(x['status'] for x in checks)),flush=True)
