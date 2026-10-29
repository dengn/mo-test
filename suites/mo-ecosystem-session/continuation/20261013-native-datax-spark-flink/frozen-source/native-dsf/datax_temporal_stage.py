import os,sys,json,time,collections
from pathlib import Path
D=Path(__file__).parent;B=D.parent
sys.path.insert(0,'/workspace/toolchains/python/lib/python3.12/site-packages');sys.path.insert(0,str(B/'windowed'));sys.path.insert(0,str(D))
import guard_6g;guard_6g.install()
import heavy as h,native_batch as nb
from recycle_profile import register,archive_profile
nb.h=h;inv=json.loads((D/'java-runtime-inventory.json').read_text());home=inv['jre8']['home'];os.environ['JAVA_HOME']=home;os.environ['PATH']=home+'/bin:'+os.environ['PATH']
route='dataxstage';out=D/'datax-temporal-stage-results.jsonl';assert not out.exists();records=[]
for pi,name in enumerate(['datetime6','time6']):
 p=next(x for x in h.PROFILES if x['name']==name);cid=100100+pi;rows=h.base_rows(cid,p,0);expected=h.canon(rows,p)
 t,s=h.tables(route,p);source='e_'+route+'_'+name
 for role in [6001,13306]:
  for table,ddl in [(t,p['ddl']),(s,'VARCHAR(128)'),(source,p['ddl'])]:
   h.sql('CREATE TABLE '+table+'(case_id BIGINT,id BIGINT,v '+ddl+',label VARCHAR(8192),rev BIGINT,PRIMARY KEY(case_id,id))',port=role);register(role,table,route,name)
 with h.db(13306,autocommit=False) as db,db.cursor() as c:c.executemany('INSERT INTO '+source+' VALUES(%s,%s,%s,%s,%s)',rows);db.commit()
 assert h.canon(h.sql('SELECT * FROM '+source+' ORDER BY case_id,id',port=13306),p)==expected
 query='SELECT case_id,id,CAST(v AS CHAR) AS v,label,rev FROM '+source
 os.environ['MO_DATAX_ACTUAL_QUERY']=query;os.environ.pop('MO_DATAX_RAW_READ',None)
 for role in [6001,13306]:
  h.guard();start=time.monotonic();r={'id':f'dataxstage_{name}_{role}','tool':'dataxstage','profile':name,'role':role,'rows':len(rows),'expected_sha256':h.sha(expected),'path':'DataX real mysqlreader -> VARCHAR staging mysqlwriter -> explicit SQL temporal CAST -> target'}
  try:
   nb.datax_load(p,s,rows,role,r['id'],None)
   stage=h.sql('SELECT * FROM '+s+' ORDER BY case_id,id',port=role)
   src=h.sql('SELECT case_id,id,CAST(v AS CHAR),label,rev FROM '+source+' ORDER BY case_id,id',port=13306)
   assert stage==src,'Native staging text changed'
   r['stage_text_oracle']='passed'
   h.sql('INSERT INTO '+t+' SELECT case_id,id,CAST(v AS '+p['ddl']+'),label,rev FROM '+s,port=role)
   a=h.canon(h.sql('SELECT * FROM '+t+' ORDER BY case_id,id',port=role),p)
   r.update(status='passed' if a==expected else 'fidelity_failed',actual_rows=len(a),actual_sha256=h.sha(a))
   r['fresh_readback_sha256']=h.sha(h.canon(h.sql('SELECT * FROM '+t+' ORDER BY case_id,id',port=role),p))
   assert r['actual_sha256']==r['fresh_readback_sha256']
  except Exception as ex:r.update(status='execution_failed',error=nb.scrub(str(ex))[-2000:])
  r['elapsed_s']=time.monotonic()-start;records.append(r)
  with out.open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
  print('DATAX_TEMPORAL_STAGE',r['id'],r['status'],flush=True)
 receipt=archive_profile(route,name,apply=True);receipt['case_ids']=[r['id'] for r in records if r['profile']==name];h.dump(Path(receipt['archive']).with_suffix('.receipt.json'),receipt)
h.dump(D/'datax-temporal-stage-summary.json',{'cases':len(records),'counts':dict(collections.Counter(r['status'] for r in records)),'native_staging_then_explicit_sql_cast':True})
