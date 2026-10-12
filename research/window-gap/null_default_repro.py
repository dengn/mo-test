"""Three rows/two partitions: untyped NULL LAG/LEAD defaults vs typed NULL controls."""
import json,time
from common import connect,read,plain
from probes import ROOT,ch
SOURCE='(SELECT 1 point,1 eid,CAST(1 AS DOUBLE) value UNION ALL SELECT 2,1,2 UNION ALL SELECT 3,2,3) f'
def main():
 c=connect();rows=[]
 for fn in ['LAG','LEAD']:
  for default in ['NULL','CAST(NULL AS DOUBLE)','CAST(0 AS DOUBLE)']:
   sql=f'SELECT point,eid,{fn}(value,1,{default}) OVER(PARTITION BY eid ORDER BY point) result FROM {SOURCE} ORDER BY point';r=dict(function=fn,default=default,sql=sql,start_epoch=time.time(),clickhouse=ch(sql))
   try:a=read(c,sql);r.update(status='executed',rows=plain(a.to_numpy(float)))
   except Exception as e:r.update(status='error',error=str(e))
   rows.append(r);print(fn,default,r['status'],flush=True)
 c.close();(ROOT/'results/null-default-repro.json').write_text(json.dumps(rows,indent=2,allow_nan=False))
 assert sum(r['status']=='error' for r in rows)==2
 assert all(r['clickhouse']['status']=='executed' for r in rows)
if __name__=='__main__':main()
