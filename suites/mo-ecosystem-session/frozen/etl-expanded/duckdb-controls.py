import duckdb,pymysql,json,traceback
from pathlib import Path
B=Path(__file__).parent
out={'cases':[]}
dd=duckdb.connect();dd.execute("SET extension_directory='/workspace/work/etl-expanded/duckdb-extensions'");dd.execute('LOAD mysql')
for name,port,pw,db in [('matrixone',6001,'111','etl_batch'),('mysql',13306,'etl-local','etl_source')]:
 d=pymysql.connect(host='127.0.0.1',port=port,user='root',password=pw,database=db,autocommit=True)
 dd.execute(f"ATTACH 'host=127.0.0.1 port={port} user=root password={pw} database={db}' AS {name} (TYPE mysql)")
 for mode in ['ctas_inferred','precreated_types']:
  r={'engine':name,'case':mode}
  try:
   with d.cursor() as c:
    c.execute('DROP TABLE IF EXISTS duck_precision')
    if mode=='precreated_types':c.execute('CREATE TABLE duck_precision(id BIGINT,name VARCHAR(100),amount DECIMAL(18,2),ts DATETIME(6))')
   sql=(f'CREATE TABLE {name}.duck_precision AS SELECT * FROM read_parquet(?)' if mode=='ctas_inferred' else f'INSERT INTO {name}.duck_precision SELECT * FROM read_parquet(?)');dd.execute(sql,[str(B/'rows.parquet')])
   with d.cursor() as c:
    c.execute('SHOW CREATE TABLE duck_precision');r['ddl']=c.fetchone()[1]
    c.execute('SELECT * FROM duck_precision ORDER BY id');rows=c.fetchall();r['rows']=rows;r['microseconds']=rows[0][3].microsecond
    if mode=='precreated_types':assert rows[0][3].microsecond==123456
   r['status']='passed'
  except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
  out['cases'].append(r);print(name,mode,r['status'],r.get('microseconds'),flush=True)
 with d.cursor() as c:
  r={'engine':name,'case':'rename_view_control'}
  try:
   c.execute('DROP VIEW IF EXISTS view_probe');c.execute('DROP VIEW IF EXISTS view_probe_renamed');c.execute('CREATE VIEW view_probe AS SELECT 1 AS id');c.execute('RENAME TABLE view_probe TO view_probe_renamed');c.execute('SELECT * FROM view_probe_renamed');assert c.fetchone()==(1,);r['status']='passed'
  except Exception as e:r.update(status='failed',error=str(e))
  out['cases'].append(r)
 d.close();dd.execute(f'DETACH {name}')
dd.close();(B/'duckdb-controls-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
