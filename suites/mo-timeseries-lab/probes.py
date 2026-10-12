"""64 small boundary probes separating GROUPS from EXCLUDE and NULL behavior."""
import json
import pandas as pd
from data import ROOT,connect,oracle,read,compare

FRAMES=[
 'ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW',
 'ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING',
 'ROWS BETWEEN 1 FOLLOWING AND 3 FOLLOWING',
 'ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING',
 'RANGE BETWEEN 2 PRECEDING AND CURRENT ROW',
 'GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW',
 'ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING EXCLUDE CURRENT ROW',
 'RANGE BETWEEN 2 PRECEDING AND CURRENT ROW EXCLUDE TIES',
]
def main():
 c=connect();rows=[];fixture=[]
 with c.cursor() as q:q.execute('CREATE TABLE IF NOT EXISTS ts_edge_probe(variant INT,entity INT,point INT,tick INT,value DOUBLE)');q.execute('SELECT COUNT(*) FROM ts_edge_probe');assert q.fetchone()[0]==0
 for variant in [0,1]:
  for entity in [1,2,3]:
   for point,tick in enumerate([0,0,2,3,3,7,8,8,12],1):fixture.append((variant,entity,point,tick,None if entity==3 or (point+variant)%4==0 else float((point*7+entity+variant)%11-4)))
 with c.cursor() as q:q.executemany('INSERT INTO ts_edge_probe VALUES(%s,%s,%s,%s,%s)',fixture)
 ref=oracle({'ts_edge_probe':pd.DataFrame(fixture,columns=['variant','entity','point','tick','value'])})
 try:
  for variant in [0,1]:
   for frame_id,frame in enumerate(FRAMES):
    for fn in ['SUM(value)','AVG(value)','LAST_VALUE(value)','NTH_VALUE(value,2)']:
     order='tick' if frame.startswith(('RANGE','GROUPS')) else 'tick,point';sql=f'SELECT entity,point,tick,{fn} OVER(PARTITION BY entity ORDER BY {order} {frame}) result FROM ts_edge_probe WHERE variant={variant} ORDER BY entity,point';r=dict(probe_id=len(rows),variant=variant,function=fn,frame=frame,sql=sql);g=ref.execute(sql).fetchdf();r['expected']=g.where(pd.notna(g),None).to_numpy().tolist()
     try:a=read(c,sql);compare(g,a);r['status']='pass';r['actual']=a.where(pd.notna(a),None).to_numpy().tolist()
     except Exception as exc:r.update(status='mismatch' if isinstance(exc,AssertionError) else 'sql_error',error=str(exc))
     rows.append(r);print(r['probe_id'],r['frame'],fn,r['status'],flush=True)
 finally:
  with c.cursor() as q:q.execute('DELETE FROM ts_edge_probe')
  c.close();ref.close()
 # JSON null, not non-standard NaN.
 from run import plain
 (ROOT/'boundary-probes.json').write_text(json.dumps(plain(rows),indent=2,allow_nan=False));assert len(rows)==64
if __name__=='__main__':main()
