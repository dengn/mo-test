"""Native Airflow MySqlHook writer, intended to run inside the official DAG."""
import os,sys,json,threading
from pathlib import Path
import heavy as h
sys.path.append('/workspace/work/etl-orchestrators-10000/venv/lib/python3.12/site-packages')
original_load=h.load;CONNECTIONS={};LOAD_SLOTS=threading.BoundedSemaphore(2)
def load(route,p,target,rows,role,token,transform=None):
 if route!='airflow':return original_load(route,p,target,rows,role,token,transform)
 with LOAD_SLOTS:
  h.guard()
  return _load_airflow(p,target,rows,role,token,transform)
def _load_airflow(p,target,rows,role,token,transform=None):
 from airflow.providers.mysql.hooks.mysql import MySqlHook
 from airflow.sdk import Connection
 e=h.endpoint(role)
 connection=Connection(conn_id='heavy_'+str(role),conn_type='mysql',host=e['host'],port=e['port'],login=e['user'],password=e['password'],schema=e['database'],extra=json.dumps({'client':'mysql-connector-python','ssl_disabled':True}))
 hook=MySqlHook(mysql_conn_id=connection.conn_id,connection=connection);d=hook.get_conn();c=d.cursor()
 if transform is not None:rows=[[a,i,v,l+'→ETL'+str(transform),r+transform+1] for a,i,v,l,r in rows if i%2==transform%2]
 try:
  for i in range(0,len(rows),31):c.executemany('INSERT INTO '+target+'(case_id,id,v,label,rev) VALUES(%s,%s,%s,%s,%s)',rows[i:i+31])
  d.commit()
 except Exception:d.rollback();raise
 finally:c.close();d.close()
h.load=load
if 'airflow' not in h.ROUTES:h.ROUTES.append('airflow')
original_run=h.run_case
def run_case(route,*args,**kwargs):
 r=original_run(route,*args,**kwargs)
 if route=='airflow':
  r['native_API']='Airflow MySqlHook6.7.0/mysql-connector-python; DAG execution recorded separately'
  r['effect_scope']='Python fixture transform and explicitSQLeffects; notnativeETLtransform engine orEOS'
 return r
h.run_case=run_case
