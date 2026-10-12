import csv,datetime,gzip,json,traceback,io
from decimal import Decimal
from pathlib import Path
import boto3,pymysql,pyarrow as pa,pyarrow.parquet as pq,pandas as pd,polars as pl,duckdb,sqlalchemy as sa

B=Path(__file__).parent
out={'matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','versions':{x:__import__(x).__version__ for x in ['pyarrow','pandas','polars','duckdb','sqlalchemy']},'cases':[]}
rows=[(1,'中文 😀',Decimal('12.34'),datetime.datetime(2026,10,10,12,0,0,123456)),(2,'',Decimal('-56.78'),None),(3,None,None,datetime.datetime(2026,10,11))]
expected=[[str(v) if v is not None else None for v in r] for r in rows]
t=pa.table({'id':pa.array([r[0] for r in rows],pa.int64()),'name':pa.array([r[1] for r in rows],pa.string()),'amount':pa.array([r[2] for r in rows],pa.decimal128(18,2)),'ts':pa.array([r[3] for r in rows],pa.timestamp('us'))})
pq.write_table(t,B/'rows.parquet',compression='snappy')
for mode in ['file','stream']:
 with pa.OSFile(str(B/f'rows-{mode}.arrow'),'wb') as f:
  with (pa.ipc.new_file if mode=='file' else pa.ipc.new_stream)(f,t.schema) as w:w.write_table(t)
objects=[dict(zip(['id','name','amount','ts'],[r[0],r[1],str(r[2]) if r[2] is not None else None,r[3].isoformat(' ') if r[3] else None])) for r in rows]
(B/'rows.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in objects))
with (B/'rows.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['id','name','amount','ts']);w.writerows([[r[0],r[1] if r[1] is not None else '\\N',r[2] if r[2] is not None else '\\N',r[3] if r[3] is not None else '\\N'] for r in rows])
for filename in ['rows.csv','rows.jsonl']:
 with gzip.open(B/(filename+'.gz'),'wb') as f:f.write((B/filename).read_bytes())
s3=boto3.client('s3',endpoint_url='http://127.0.0.1:9000',aws_access_key_id='minio',aws_secret_access_key='minio123',region_name='us-east-1')
for p in B.glob('rows.*'):s3.upload_file(str(p),'mo-test','etl-expanded/'+p.name)
for p in B.glob('rows-*.arrow'):s3.upload_file(str(p),'mo-test','etl-expanded/'+p.name)
d=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True)
c=d.cursor();c.execute('CREATE DATABASE IF NOT EXISTS etl_batch');c.execute('USE etl_batch')
schema='(id BIGINT PRIMARY KEY,name VARCHAR(100),amount DECIMAL(18,2),ts DATETIME(6))'
def check(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error',''),flush=True)
def actual(table):
 c.execute(f'SELECT * FROM {table} ORDER BY id');return [[str(v) if v is not None else None for v in r] for r in c.fetchall()]
def compare(table,want=expected):
 a=actual(table);assert a==want,(a,want);return a
c.execute("DROP STAGE IF EXISTS etl_s3")
c.execute("CREATE STAGE etl_s3 URL='s3://mo-test/etl-expanded/' CREDENTIALS={'aws_key_id'='minio','aws_secret_key'='minio123','aws_region'='us-east-1','endpoint'='http://127.0.0.1:9000','provider'='minio'}")
def load(table,file,fmt,local=False,gz=False):
 c.execute(f'DROP TABLE IF EXISTS {table}');c.execute(f'CREATE TABLE {table} {schema}')
 path=str(B/file) if local else 'stage://etl_s3/'+file
 opts=f"'filepath'='{path}','format'='{fmt}'"+(",'jsondata'='object'" if fmt=='jsonline' else '')
 tail=" FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' IGNORE 1 LINES" if fmt=='csv' else ''
 sql=f'LOAD DATA INFILE {{{opts}}} INTO TABLE {table}'+tail;c.execute(sql)
 return {'sql':sql,'rows':compare(table)}
for name,file,fmt,gz in [('s3_csv','rows.csv','csv',False),('s3_jsonl','rows.jsonl','jsonline',False),('s3_parquet','rows.parquet','parquet',False),('s3_arrow_file','rows-file.arrow','arrow',False),('s3_arrow_stream','rows-stream.arrow','arrow',False),('s3_csv_gzip','rows.csv.gz','csv',True),('s3_jsonl_gzip','rows.jsonl.gz','jsonline',True)]:
 check(name,lambda name=name,file=file,fmt=fmt,gz=gz:load(name,file,fmt,gz=gz))
def bad_load_recover():
 c.execute('CREATE TABLE IF NOT EXISTS bad_rows(id BIGINT PRIMARY KEY,name VARCHAR(100),amount DECIMAL(18,2),ts DATETIME(6))');c.execute('TRUNCATE TABLE bad_rows')
 p=B/'bad.csv';p.write_text('1,ok,1.00,2026-10-10 12:00:00\n2,bad,not_decimal,2026-10-10 12:00:00\n')
 try:c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='csv'}} INTO TABLE bad_rows FIELDS TERMINATED BY ','");raise AssertionError('malformed decimal accepted')
 except pymysql.MySQLError as e:error=str(e)
 c.execute('SELECT count(*) FROM bad_rows');assert c.fetchone()[0]==0,'partial batch committed'
 c.execute('INSERT INTO bad_rows VALUES(9,\'recovery\',9.99,NULL)');c.execute('SELECT amount FROM bad_rows');assert c.fetchone()[0]==Decimal('9.99')
 return {'rejected_error':error,'partial_rows':0,'next_statement':'passed'}
check('malformed_decimal_atomic_failure_and_recovery',bad_load_recover)
eng=sa.create_engine('mysql+pymysql://root:111@127.0.0.1:6001/etl_batch')
def pandas_roundtrip(method):
 table='pandas_'+(method or 'default');c.execute(f'DROP TABLE IF EXISTS {table}');c.execute(f'CREATE TABLE {table} {schema}')
 pd.DataFrame(rows,columns=['id','name','amount','ts']).to_sql(table,eng,if_exists='append',index=False,chunksize=2,method=method)
 compare(table);df=pd.read_sql(sa.text(f'SELECT * FROM {table} ORDER BY id'),eng,coerce_float=False);assert df['amount'][0]==Decimal('12.34');assert df['name'].iloc[0]=='中文 😀' and df['name'].iloc[1]=='' and pd.isna(df['name'].iloc[2])
 return {'rows':actual(table),'read_decimal_type':type(df['amount'][0]).__name__}
check('pandas_sqlalchemy_default',lambda:pandas_roundtrip(None));check('pandas_sqlalchemy_multi',lambda:pandas_roundtrip('multi'))
def polars_to_mo():
 df=pl.read_parquet(B/'rows.parquet');df.write_database('polars_typed',eng,if_table_exists='replace',engine_options={'dtype':{'amount':sa.DECIMAL(18,2),'ts':sa.dialects.mysql.DATETIME(fsp=6)}});return {'rows':compare('polars_typed')}
check('polars_explicit_dtype_write_database',polars_to_mo)
def duckdb_transform():
 dd=duckdb.connect()
 try:
  result=dd.execute("SELECT id, upper(name) AS name, amount::DECIMAL(18,2) AS amount, ts FROM read_parquet(?) ORDER BY id",[str(B/'rows.parquet')]).fetchall()
  c.execute('DROP TABLE IF EXISTS duckdb_rows');c.execute('CREATE TABLE duckdb_rows '+schema);c.executemany('INSERT INTO duckdb_rows VALUES(%s,%s,%s,%s)',result)
  return {'rows':compare('duckdb_rows'),'transport':'DuckDB transform + DBAPI prepared batch, not MySQL extension'}
 finally:dd.close()
check('duckdb_transform_dbapi_sink',duckdb_transform)
eng.dispose();c.execute('DROP STAGE etl_s3');c.close();d.close()
(B/'batch-retest-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
print(json.dumps({'passed':sum(r['status']=='passed' for r in out['cases']),'failed':sum(r['status']=='failed' for r in out['cases'])}))
