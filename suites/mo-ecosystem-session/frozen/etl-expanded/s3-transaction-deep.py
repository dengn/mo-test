import pymysql,boto3,json,traceback
from pathlib import Path
B=Path(__file__).parent
out={'matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','scope':'raw S3 writable external tables, not Iceberg','cases':[]}
s=boto3.client('s3',endpoint_url='http://127.0.0.1:9000',aws_access_key_id='minio',aws_secret_access_key='minio123',region_name='us-east-1')
def connection():return pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='etl_batch',autocommit=True)
def objects(prefix):return [o['Key'] for o in s.list_objects_v2(Bucket='mo-test',Prefix=prefix).get('Contents',[])]
setup=connection()
with setup:
 with setup.cursor() as c:
  c.execute("CREATE STAGE IF NOT EXISTS etl_txn_deep URL='s3://mo-test/etl-expanded-txn-deep/' CREDENTIALS={'aws_key_id'='minio','aws_secret_key'='minio123','aws_region'='us-east-1','endpoint'='http://127.0.0.1:9000','provider'='minio'}")
  c.execute('DROP TABLE IF EXISTS txn_control');c.execute('CREATE TABLE txn_control(id BIGINT PRIMARY KEY,name VARCHAR(100))')
for mode,fmt in [('explicit_rollback_json','jsonline'),('connection_close_csv','csv')]:
 r={'name':mode};prefix='etl-expanded-txn-deep/'+mode
 for k in objects(prefix):s.delete_object(Bucket='mo-test',Key=k)
 writer=connection();observer=connection()
 try:
  with writer.cursor() as c:
   c.execute('DROP TABLE IF EXISTS '+mode)
   opts=f"'filepath'='stage://etl_txn_deep/{mode}_*.dat','format'='{fmt}','write_file_pattern'='stage://etl_txn_deep/{mode}_%U.dat'"+(",'jsondata'='object'" if fmt=='jsonline' else '')
   c.execute(f'CREATE EXTERNAL TABLE {mode}(id BIGINT,name VARCHAR(100)) INFILE {{{opts}}}'+(" FIELDS TERMINATED BY ','" if fmt=='csv' else ''))
   c.execute('BEGIN');c.execute("INSERT INTO txn_control VALUES(1,'native uncommitted')");c.execute(f"INSERT INTO {mode} VALUES(1,'external uncommitted')")
  with observer.cursor() as c:
   c.execute('SELECT count(*) FROM txn_control');r['observer_native_before_end']=c.fetchone()[0]
   c.execute('SELECT * FROM '+mode);r['observer_external_before_end']=c.fetchall()
  r['objects_before_end']=objects(prefix)
  if mode.startswith('explicit'):writer.rollback()
  writer.close()
  with observer.cursor() as c:
   c.execute('SELECT count(*) FROM txn_control');r['observer_native_after_end']=c.fetchone()[0]
   c.execute('SELECT * FROM '+mode);r['observer_external_after_end']=c.fetchall()
   c.execute('DROP TABLE '+mode)
  r['objects_after_end']=objects(prefix);r['contents']={k:s.get_object(Bucket='mo-test',Key=k)['Body'].read().decode() for k in r['objects_after_end']}
  assert r['observer_native_before_end']==0 and r['observer_native_after_end']==0,'native transaction control failed'
  assert not r['observer_external_before_end'] and not r['observer_external_after_end'],'external rows visible before commit and survive rollback'
  r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 finally:
  if writer.open:writer.rollback();writer.close()
  observer.close();out['cases'].append(r);print(json.dumps(r,ensure_ascii=False,default=str),flush=True)
setup=connection()
with setup:
 with setup.cursor() as c:c.execute('DROP STAGE etl_txn_deep')
(B/'s3-transaction-deep-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
