"""Actual native MO interval/sliding/fill probes, not inferred missing capabilities."""
import datetime,json
from common import connect,read,plain
from probes import ROOT
def main():
 c=connect();table='ts_gap_time_window';rows=[]
 with c.cursor() as q:
  q.execute(f'CREATE TABLE IF NOT EXISTS {table}(ts TIMESTAMP(6) PRIMARY KEY,value DOUBLE)');q.execute(f'SELECT COUNT(*) FROM {table}');assert q.fetchone()[0]==0
  values=[(datetime.datetime(2024,1,1)+datetime.timedelta(minutes=m),v) for m,v in [(0,1.),(1,2.),(3,6.),(5,None),(7,8.)]];q.executemany(f'INSERT INTO {table} VALUES(%s,%s)',values)
 try:
  for name,tail in [('tumble','interval(ts,2,minute)'),('sliding','interval(ts,3,minute) sliding(1,minute)'),('fill_prev','interval(ts,2,minute) fill(prev)'),('fill_next','interval(ts,2,minute) fill(next)'),('fill_linear','interval(ts,2,minute) fill(linear)'),('fill_constant','interval(ts,2,minute) fill(value,0)')]:
   sql=f"SELECT _wstart(ts) wstart,_wend(ts) wend,SUM(value) total,AVG(value) mean_value,COUNT(value) n FROM {table} WHERE ts>='2024-01-01 00:00:00' AND ts<'2024-01-01 00:08:00' {tail}";r=dict(name=name,sql=sql)
   try:
    a=read(c,sql);r.update(status='executed',columns=list(a),rows=[[v.isoformat() if isinstance(v,datetime.datetime) else plain(v) for v in row] for row in a.itertuples(index=False,name=None)])
    if name=='tumble':
     assert [v[2] for v in r['rows']]==[3.,6.,None,8.],r['rows'];assert [v[4] for v in r['rows']]==[2,1,0,1],r['rows'];r['independent_tumble_values_verified']=True
   except Exception as e:r.update(status='error',error=str(e))
   rows.append(r);print(name,r['status'],r.get('rows',r.get('error')),flush=True)
 finally:
  with c.cursor() as q:q.execute(f'DELETE FROM {table}')
  c.close()
 (ROOT/'results/native-mo-time-windows.json').write_text(json.dumps(plain(rows),indent=2,allow_nan=False))
if __name__=='__main__':main()
