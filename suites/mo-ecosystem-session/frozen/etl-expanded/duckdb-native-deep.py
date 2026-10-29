import duckdb,pymysql,json,traceback,datetime
from decimal import Decimal
from pathlib import Path
B=Path(__file__).parent
out={'duckdb':duckdb.__version__,'cases':[]}
c=duckdb.connect();c.execute("SET extension_directory='/workspace/work/etl-expanded/duckdb-extensions'");c.execute('LOAD mysql');c.execute("ATTACH 'host=127.0.0.1 port=6001 user=root password=111 database=etl_batch' AS mo (TYPE mysql)")
d=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='etl_batch',autocommit=True)
want=[(1,'中文 😀',Decimal('12.34'),datetime.datetime(2026,10,10,12,0,0,123456)),(2,'',Decimal('-56.78'),None),(3,None,None,datetime.datetime(2026,10,11))]
def case(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:200],flush=True)
def read():
 rows=c.execute('SELECT * FROM mo.s3_parquet ORDER BY id').fetchall();assert rows==want,(rows,want)
 return {'schema':c.execute('DESCRIBE mo.s3_parquet').fetchall(),'rows':rows}
case('native_mysql_extension_exact_read',read)
def write():
 c.execute('DROP TABLE IF EXISTS mo.duckdb_native_rows');c.execute('CREATE TABLE mo.duckdb_native_rows AS SELECT * FROM read_parquet(?)',[str(B/'rows.parquet')])
 with d.cursor() as p:p.execute('SELECT * FROM duckdb_native_rows ORDER BY id');got=list(p.fetchall());assert got==want,(got,want)
 return got
case('native_mysql_extension_create_and_bulk_write',write)
def update():
 c.execute("UPDATE mo.duckdb_native_rows SET name='变更',amount=amount+1 WHERE id=1");c.execute('DELETE FROM mo.duckdb_native_rows WHERE id=2')
 with d.cursor() as p:p.execute('SELECT id,name,amount FROM duckdb_native_rows ORDER BY id');got=list(p.fetchall());assert got==[(1,'变更',Decimal('13.34')),(3,None,None)]
 return got
case('native_mysql_extension_update_delete',update)
c.close();d.close();(B/'duckdb-native-deep-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
