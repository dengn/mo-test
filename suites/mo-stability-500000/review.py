import sys,json,time,concurrent.futures
from pathlib import Path
sys.path.insert(0,'/workspace/mo-cases-50000');import runner as b
P=Path('/workspace/mo-stability-500000');records=[]
def run(sql,params=None):
 c=b.connect('mo',timeout=90)
 try:r={'sql':sql,'params':params,'rows':b.norm(b.query(c,sql,params)),'error':None}
 except Exception as e:r={'sql':sql,'params':params,'error':str(e)}
 finally:c.close()
 records.append(r);return r
run('show create table race_h');run('show index from race_h')
run('insert into race_h values (%s,%s,%s)',[99000002,297000006,json.dumps([1.0]*64)])
run('alter table race_h alter reindex ann hnsw force_sync')
for trial in range(3):
 t=f'index_repro_{trial}'
 run(f'create table {t}(id bigint primary key,n bigint,v vecf32(64))')
 run(f'insert into {t} values(%s,%s,%s)',[1,3,json.dumps([1.0]*64)])
 run(f"create index ann using hnsw on {t}(v) op_type 'vector_l2_ops'")
 run(f'create index extra on {t}(n)');run(f'drop index extra on {t}')
 run(f'show create table {t}');run(f'insert into {t} values(%s,%s,%s)',[2,6,json.dumps([2.0]*64)])
 run(f'alter table {t} alter reindex ann hnsw force_sync')
(P/'index-fresh-session-recheck.json').write_text(json.dumps(records,indent=2,ensure_ascii=False))
ids={r['id'] for r in map(json.loads,open('/workspace/mo-cases-50000/results.jsonl')) if r['family']=='ddl.truncate' and r['status']!='pass'}
with (P/'truncate-serial-recheck.jsonl').open('w') as f:
 for case in map(json.loads,open('/workspace/mo-cases-50000/cases.jsonl')):
  if case['id'] in ids:
   r=b.runone(case);f.write(json.dumps(r,ensure_ascii=False)+'\n');print(r['id'],r['status'],flush=True)
print('INDEX_REVIEW',json.dumps([r for r in records if r.get('error')],ensure_ascii=False),flush=True)
