import json,traceback
from pathlib import Path
from pyiceberg.catalog import load_catalog
out={}
try:
 c=load_catalog('lake',type='rest',uri='http://127.0.0.1:19120/iceberg',warehouse='s3://mo-iceberg/warehouse',**{'s3.endpoint':'http://127.0.0.1:9000','s3.access-key-id':'minio','s3.secret-access-key':'minio123','s3.region':'us-east-1'})
 rows=c.load_table(('mo_audit_cross','cross_rows')).scan().to_arrow().sort_by('id').to_pylist()
 actual=[[str(v) if v is not None else None for v in r.values()] for r in rows]
 expected=[['1','Spark 中文','12.34','2026-10-10'],['2',None,'56.78','2026-10-11'],['3','MO 中文','90.12','2026-10-12']]
 out={'name':'mo-spark-write-pyiceberg-arrow-read','actual':actual,'expected':expected,'status':'passed' if actual==expected else 'failed'}
 assert actual==expected
except Exception as e:
 out['status']='failed';out['error']=str(e);traceback.print_exc()
Path('pyiceberg-read-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
if out['status']!='passed':raise SystemExit(1)
