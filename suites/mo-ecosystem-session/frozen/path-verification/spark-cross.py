import json,traceback,datetime
from decimal import Decimal
from pathlib import Path
import pymysql
from pyspark.sql import SparkSession
from pyiceberg.catalog import load_catalog
out={'matrixone_sha':'652c643666428f1c434e03369834f2a9bead7c27','spark_version':'3.5.7','iceberg_version':'1.9.2','cases':[]}
spark=None;db=None

def norm(rows):
 return [[str(v) if v is not None else None for v in row] for row in rows]
def check(name,actual,expected):
 actual=norm(actual);expected=norm(expected)
 out['cases'].append({'name':name,'actual':actual,'expected':expected,'status':'passed' if actual==expected else 'failed'})
 assert actual==expected,(name,actual,expected)
try:
 spark=(SparkSession.builder.master('local[2]').appName('MatrixOne-Iceberg-Cross')
 .config('spark.driver.memory','512m').config('spark.ui.enabled','false')
 .config('spark.jars',','.join(str(p.resolve()) for p in [Path('jars/iceberg-spark-runtime.jar'),Path('jars/iceberg-aws-bundle.jar')]))
 .config('spark.sql.extensions','org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions')
 .config('spark.sql.catalog.lake','org.apache.iceberg.spark.SparkCatalog')
 .config('spark.sql.catalog.lake.type','rest').config('spark.sql.catalog.lake.uri','http://127.0.0.1:19120/iceberg')
 .config('spark.sql.catalog.lake.warehouse','s3://mo-iceberg/warehouse')
 .config('spark.sql.catalog.lake.io-impl','org.apache.iceberg.aws.s3.S3FileIO')
 .config('spark.sql.catalog.lake.s3.endpoint','http://127.0.0.1:9000')
 .config('spark.sql.catalog.lake.s3.path-style-access','true')
 .config('spark.sql.catalog.lake.s3.access-key-id','minio').config('spark.sql.catalog.lake.s3.secret-access-key','minio123')
 .config('spark.sql.catalog.lake.client.region','us-east-1').getOrCreate())
 spark.sparkContext.setLogLevel('WARN')
 spark.sql('CREATE NAMESPACE IF NOT EXISTS lake.mo_audit_cross')
 spark.sql('CREATE TABLE lake.mo_audit_cross.cross_rows(id BIGINT,label STRING,amount DECIMAL(18,2),event_date DATE) USING iceberg TBLPROPERTIES (\'format-version\'=\'2\')')
 spark.sql("INSERT INTO lake.mo_audit_cross.cross_rows VALUES (1,'Spark 中文',12.34,DATE '2026-10-10'),(2,NULL,56.78,DATE '2026-10-11')")
 db=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True)
 with db.cursor() as c:
  c.execute('CREATE DATABASE IF NOT EXISTS cross_audit')
  c.execute("CREATE ICEBERG CATALOG cross_catalog WITH ('type'='rest','uri'='http://127.0.0.1:19120/iceberg','warehouse'='s3://mo-iceberg/warehouse','auth_mode'='none')")
  c.execute("CALL iceberg_register_access('cross_catalog','scope=cluster,account_id=0,external_principal=ci-local,endpoint=localhost,region=us-east-1,bucket=mo-iceberg')")
  c.execute("CREATE EXTERNAL TABLE cross_audit.cross_rows(id BIGINT,label TEXT,amount DECIMAL(18,2),event_date DATE) ENGINE=ICEBERG WITH ('catalog'='cross_catalog','namespace'='mo_audit_cross','table'='cross_rows','ref'='main','read_mode'='append_only','write_mode'='append_only')")
  c.execute('SELECT * FROM cross_audit.cross_rows ORDER BY id')
  expected=[(1,'Spark 中文',Decimal('12.34'),datetime.date(2026,10,10)),(2,None,Decimal('56.78'),datetime.date(2026,10,11))]
  check('spark-write-mo-read',c.fetchall(),expected)
  c.execute("INSERT INTO cross_audit.cross_rows VALUES(3,'MO 中文',90.12,'2026-10-12')")
 expected.append((3,'MO 中文',Decimal('90.12'),datetime.date(2026,10,12)))
 spark.sql('REFRESH TABLE lake.mo_audit_cross.cross_rows')
 check('mo-write-spark-read',spark.sql('SELECT * FROM lake.mo_audit_cross.cross_rows ORDER BY id').collect(),expected)
 cat=load_catalog('lake',type='rest',uri='http://127.0.0.1:19120/iceberg',warehouse='s3://mo-iceberg/warehouse',**{'s3.endpoint':'http://127.0.0.1:9000','s3.access-key-id':'minio','s3.secret-access-key':'minio123','s3.region':'us-east-1'})
 tbl=cat.load_table(('mo_audit_cross','cross_rows'))
 rows=tbl.scan().to_arrow().sort_by('id').to_pylist()
 check('mo-spark-write-pyiceberg-arrow-read',[(r['id'],r['label'],r['amount'],r['event_date']) for r in rows],expected)
 out['status']='passed'
except Exception as e:
 out['status']='failed';out['error']=str(e);traceback.print_exc()
finally:
 if db:db.close()
 if spark:spark.stop()
 Path('spark-cross-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 print(json.dumps(out,ensure_ascii=False,indent=2))
if out['status']!='passed':raise SystemExit(1)
