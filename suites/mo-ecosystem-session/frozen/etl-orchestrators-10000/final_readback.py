import pathlib,sys,json,collections,pymysql,datetime
B=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(B));from codec import canon,sha
fixtures={c['logical_case_id']:c for c in json.loads((B/'fixtures.json').read_text())};out=[]
for component in ['airflow','dolphinscheduler']:
 for port,password in [(6001,'111'),(13306,'types-local')]:
  d=pymysql.connect(host='127.0.0.1',port=port,user='root',password=password,database='orchestrator10000',charset='utf8mb4',autocommit=True,read_timeout=90)
  with d.cursor() as cur:
   for p in {c['profile'] for c in fixtures.values()}:
    cur.execute('SELECT case_id,id,v,label,rev FROM '+component+'_'+p+' ORDER BY case_id,id');rows=cur.fetchall();bycase=collections.defaultdict(list)
    for r in rows:bycase[r[0]].append(r)
    for c in fixtures.values():
     if c['profile']!=p:continue
     actual=canon(bycase.pop(c['logical_case_id'],[]),p);out.append({'id':f'{component}_{p}_{c["scenario"]}_{c["seed"]}_{port}','status':'passed' if sha(actual)==c['expected_sha256'] and len(actual)==len(c['expected']) else 'failed','actual_rows':len(actual),'actual_sha256':sha(actual)})
    assert not bycase,('extra case ids',component,port,p,list(bycase))
  d.close()
assert len(out)==4000 and all(r['status']=='passed' for r in out);(B/'final-readback-audit.json').write_text(json.dumps({'checked':4000,'counts':dict(collections.Counter(r['status'] for r in out)),'rows':sum(r['actual_rows'] for r in out),'scope':'Independent PyMySQL full-table readback of final Airflow and DolphinScheduler outputs after native task completion; other6000cases audited from complete dbt tables,SDKDuckDBwarehouse,Airbyte raw stream/typed SQL adapter tables; extra case IDs checked','UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':out},ensure_ascii=False,indent=2));print('FINAL',len(out),dict(collections.Counter(r['status'] for r in out)),flush=True)
