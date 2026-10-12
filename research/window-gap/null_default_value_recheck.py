import sys,json,hashlib,datetime
from pathlib import Path
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import connect,read,plain
from probes import ch
ROOT=Path(__file__).resolve().parent
SOURCE='(SELECT 1 point,1 eid,CAST(1 AS DOUBLE) value UNION ALL SELECT 2,1,2 UNION ALL SELECT 3,2,3) f'
def sql_for(fn,default):
 args='value,1'+(','+default if default is not None else '')
 return f'SELECT point,eid,{fn}({args}) OVER(PARTITION BY eid ORDER BY point) result FROM {SOURCE} ORDER BY point'
c=connect();rows=[];pid=int(__import__('os').environ['MO_SERVER_PID']);before=psutil.Process(pid).create_time()
for repeat in range(3):
 for fn in ['LAG','LEAD']:
  for default in ['NULL','CAST(NULL AS DOUBLE)',None,'CAST(0 AS DOUBLE)']:
   d=0 if default=='CAST(0 AS DOUBLE)' else None
   gold=[d,1,d] if fn=='LAG' else [2,d,d]
   expected=[[1.,1.,gold[0]],[2.,1.,gold[1]],[3.,2.,gold[2]]]
   sql=sql_for(fn,default);r=dict(repeat=repeat+1,function=fn,default=default,sql=sql,expected=expected)
   try:
    a=read(c,sql);actual=plain(a.to_numpy(float));r.update(status='pass' if actual==expected else 'mismatch',actual=actual)
   except Exception as exc:r.update(status='error',error=str(exc))
   rows.append(r)
health=int(read(c,'SELECT 1 AS healthy').iloc[0,0]);c.close();same=psutil.Process(pid).create_time()==before
clickhouse=[]
for fn in ['LAG','LEAD']:
 for default in ['NULL','CAST(NULL AS DOUBLE)']:
  out=ch(sql_for(fn,default));clickhouse.append(dict(function=fn,default=default,**out))
result=dict(repeats=3,mo_records=rows,clickhouse_records=clickhouse,same_process_create_time=same,health_after=health)
(ROOT/'results/null-default-value-recheck.json').write_text(json.dumps(result,indent=2,allow_nan=False))
assert health==1 and same
for r in rows:
 assert r['status']==('error' if r['default']=='NULL' else 'mismatch' if r['default']=='CAST(NULL AS DOUBLE)' else 'pass'),r
 if r['status']=='error':assert '20101' in r['error'] and 'index out of range [2] with length 1' in r['error']
 if r['status']=='mismatch':assert r['actual'][-1]==[3.,2.,0.]
for r in clickhouse:
 assert r['status']=='executed';gold=[None,1,None] if r['function']=='LAG' else [2,None,None];assert [x['result'] for x in r['rows']]==gold
print(json.dumps(dict(repeats=3,panic=6,typed_null_wrong_zero=6,omitted_or_zero_pass=12,clickhouse_correct=4,same_process=True,health_after=1)))
