import pymysql,boto3,csv,io,json,datetime,traceback
from decimal import Decimal
from pathlib import Path
B=Path(__file__).parent
out={'cases':[]}
s3=boto3.client('s3',endpoint_url='http://127.0.0.1:9000',aws_access_key_id='minio',aws_secret_access_key='minio123',region_name='us-east-1')
d=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='etl_batch',autocommit=True);c=d.cursor()
c.execute("CREATE STAGE IF NOT EXISTS etl_out URL='s3://mo-test/etl-expanded-out/' CREDENTIALS={'aws_key_id'='minio','aws_secret_key'='minio123','aws_region'='us-east-1','endpoint'='http://127.0.0.1:9000','provider'='minio'}")
want=[(1,'中文 😀',Decimal('12.34'),datetime.datetime(2026,10,10,12,0,0,123456)),(2,'',Decimal('-56.78'),None),(3,None,None,datetime.datetime(2026,10,11))]
def case(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:200],flush=True)
def keys():return [o['Key'] for o in s3.list_objects_v2(Bucket='mo-test',Prefix='etl-expanded-out/').get('Contents',[])]
for k in keys():s3.delete_object(Bucket='mo-test',Key=k)
def csv_export():
 c.execute("SELECT * FROM s3_parquet ORDER BY id INTO OUTFILE 'stage://etl_out/rows.csv' FIELDS TERMINATED BY ',' ENCLOSED BY '\"' LINES TERMINATED BY '\\n' HEADER 'false'")
 files=[k for k in keys() if k.endswith('.csv')];assert files
 got=[]
 for k in files:
  raw=s3.get_object(Bucket='mo-test',Key=k)['Body'].read().decode();print('csv-export-bytes',repr(raw),flush=True)
  for r in csv.reader(io.StringIO(raw)):
   vals=[None if v=='\\N' else v for v in r];got.append((int(vals[0]),vals[1],Decimal(vals[2]) if vals[2] is not None else None,datetime.datetime.fromisoformat(vals[3]) if vals[3] is not None else None))
 assert got==want,(got,want);return {'objects':files,'rows':got,'consumer':'Python CSV + Decimal parser, exact typed comparison'}
case('mo_outfile_s3_csv_independent_read',csv_export)
def json_export():
 c.execute('DROP TABLE IF EXISTS json_sink');c.execute("CREATE EXTERNAL TABLE json_sink(id BIGINT,name VARCHAR(100),amount DECIMAL(18,2),ts DATETIME(6)) INFILE {'filepath'='stage://etl_out/rows_*.jsonl','format'='jsonline','jsondata'='object','write_file_pattern'='stage://etl_out/rows_%U.jsonl'}")
 c.execute('INSERT INTO json_sink SELECT * FROM s3_parquet')
 c.execute('SELECT * FROM json_sink ORDER BY id');got=list(c.fetchall());assert got==want,(got,want)
 files=[k for k in keys() if k.endswith('.jsonl')];raw=[]
 for k in files:raw.extend(json.loads(line,parse_float=Decimal) for line in s3.get_object(Bucket='mo-test',Key=k)['Body'].read().decode().splitlines())
 other=[(int(r['id']),r['name'],Decimal(str(r['amount'])) if r['amount'] is not None else None,datetime.datetime.fromisoformat(r['ts']) if r['ts'] is not None else None) for r in sorted(raw,key=lambda x:x['id'])]
 assert other==want,(other,want);return {'objects':files,'native_rows':got,'independent_json_rows':other}
case('mo_writable_external_s3_jsonline_independent_read',json_export)
c.execute('DROP STAGE etl_out');c.close();d.close();(B/'s3-outbound-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
