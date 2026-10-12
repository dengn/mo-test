import pymysql,boto3,json,traceback
from pathlib import Path
B=Path(__file__).parent
r={'case':'native_and_raw_s3_external_write_rollback_boundary','matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','scope':'raw S3 writable external table, not Iceberg'}
s=boto3.client('s3',endpoint_url='http://127.0.0.1:9000',aws_access_key_id='minio',aws_secret_access_key='minio123',region_name='us-east-1')
def objects():
 return [o['Key'] for o in s.list_objects_v2(Bucket='mo-test',Prefix='etl-expanded-txn/').get('Contents',[])]
for k in objects():s.delete_object(Bucket='mo-test',Key=k)
d=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='etl_batch',autocommit=True)
try:
 with d.cursor() as c:
  c.execute("CREATE STAGE IF NOT EXISTS etl_txn URL='s3://mo-test/etl-expanded-txn/' CREDENTIALS={'aws_key_id'='minio','aws_secret_key'='minio123','aws_region'='us-east-1','endpoint'='http://127.0.0.1:9000','provider'='minio'}")
  c.execute('DROP TABLE IF EXISTS txn_native');c.execute('CREATE TABLE txn_native(id BIGINT PRIMARY KEY,name VARCHAR(100))')
  c.execute('DROP TABLE IF EXISTS txn_external');c.execute("CREATE EXTERNAL TABLE txn_external(id BIGINT,name VARCHAR(100)) INFILE {'filepath'='stage://etl_txn/txn_*.jsonl','format'='jsonline','jsondata'='object','write_file_pattern'='stage://etl_txn/txn_%U.jsonl'}")
  c.execute('BEGIN');c.execute("INSERT INTO txn_native VALUES(1,'should rollback')")
  try:c.execute("INSERT INTO txn_external VALUES(1,'should rollback')");r['external_statement']='accepted'
  except pymysql.MySQLError as e:r.update(external_statement='rejected',rejection=str(e))
  r['objects_before_rollback']=objects();d.rollback();c.execute('SELECT count(*) FROM txn_native');r['native_rows_after_rollback']=c.fetchone()[0]
  r['objects_after_rollback']=objects();r['external_object_contents']={k:s.get_object(Bucket='mo-test',Key=k)['Body'].read().decode() for k in r['objects_after_rollback']}
  c.execute('SELECT * FROM txn_external');r['external_rows_after_rollback']=c.fetchall()
  assert r['native_rows_after_rollback']==0,r
  assert not r['objects_after_rollback'] and not r['external_rows_after_rollback'],'external side effect survived native rollback'
  r['status']='passed'
except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
finally:
 d.rollback()
 with d.cursor() as c:c.execute('DROP TABLE IF EXISTS txn_external');c.execute('DROP STAGE IF EXISTS etl_txn')
 d.close();(B/'s3-transaction-result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,default=str));print(json.dumps(r,ensure_ascii=False,indent=2,default=str))
