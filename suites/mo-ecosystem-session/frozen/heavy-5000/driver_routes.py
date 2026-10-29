import sys
sys.path.append('/workspace/toolchains/python/lib/python3.12/site-packages')
import heavy as h
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
original=h.load
# Real driver/dataframe routes; effect/schema/failure scenarios are shared, explicitly tagged SQL adapters.
def load(route,p,table,rows,port,token,transform=None):
 if route in h.ROUTES:return original(route,p,table,rows,port,token,transform)
 suffix='→ETL'+str(transform) if transform is not None else None
 if transform is not None:rows=[[a,i,v,l+suffix,r+transform+1] for a,i,v,l,r in rows if i%2==transform%2]
 if route=='pandas':
  frame=h.frame(rows);frame.to_sql(table,h.engine(port),if_exists='append',index=False,chunksize=31,dtype=h.dtypes(p))
 elif route=='sqlalchemy':
  meta=sa.MetaData();t=sa.Table(table,meta,sa.Column('case_id',sa.BigInteger()),sa.Column('id',sa.BigInteger()),sa.Column('v',p['bind']),sa.Column('label',sa.String(8192)),sa.Column('rev',sa.BigInteger()))
  with h.engine(port).begin() as c:
   for i in range(0,len(rows),31):c.execute(t.insert(),[dict(zip(h.COLS,r)) for r in rows[i:i+31]])
 elif route=='pymysql':
  with h.db(port,autocommit=False) as d,d.cursor() as c:
   for i in range(0,len(rows),31):c.executemany('INSERT INTO '+table+' VALUES(%s,%s,%s,%s,%s)',rows[i:i+31])
   d.commit()
 elif route=='mysql_connector':
  import mysql.connector
  d=mysql.connector.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='heavy5000',charset='utf8mb4',collation='utf8mb4_bin',ssl_disabled=True);c=d.cursor()
  try:
   for i in range(0,len(rows),31):c.executemany('INSERT INTO '+table+'(case_id,id,v,label,rev) VALUES(%s,%s,%s,%s,%s)',rows[i:i+31])
   d.commit()
  finally:c.close();d.close()
 else:raise ValueError(route)
h.load=load
