"""Recreate deterministic real Iceberg data in an existing local REST catalog."""
import os,json,sys
from pathlib import Path
import pyarrow as pa
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField,LongType,StringType
import pymysql
os.environ.pop('AWS_PROFILE',None);os.environ.pop('AWS_DEFAULT_PROFILE',None)
P=Path(__file__).resolve().parent
c=load_catalog('local',type='rest',uri='http://127.0.0.1:19120/iceberg',warehouse='s3://mo-iceberg/warehouse',**{'s3.endpoint':'http://127.0.0.1:9000','s3.access-key-id':'minio','s3.secret-access-key':'minio123','s3.region':'us-east-1','s3.force-virtual-addressing':'false'})
c.create_namespace_if_not_exists('cornerbulk')
try:t=c.load_table('cornerbulk.events')
except Exception:t=c.create_table('cornerbulk.events',schema=Schema(NestedField(1,'id',LongType(),required=False),NestedField(2,'grp',LongType(),required=False),NestedField(3,'v',LongType(),required=False),NestedField(4,'label',StringType(),required=False)))
a=pa.table({'id':list(range(1000)),'grp':[i%17 for i in range(1000)],'v':[i*13-700 for i in range(1000)],'label':['alpha' if i%2==0 else '中文😀' for i in range(1000)]})
if not t.current_snapshot():t.append(a)
actual=t.scan().to_arrow().sort_by('id')
if not actual.equals(a):raise RuntimeError('Existing external table differs from deterministic fixture')
(P/'iceberg-fixture.json').write_text(json.dumps({'snapshot':t.current_snapshot().snapshot_id,'metadata':t.metadata_location,'rows':a.to_pylist()},ensure_ascii=False,indent=2))
m=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='corners50',autocommit=True,ssl_disabled=True,read_timeout=60)
with m.cursor() as q:
 q.execute("create iceberg catalog if not exists bulkice with ('type'='rest','uri'='http://127.0.0.1:19122/iceberg','warehouse'='s3://mo-iceberg/warehouse','auth_mode'='none')")
 q.execute("call iceberg_register_access('bulkice','scope=cluster,account_id=0,external_principal=ci-local,endpoint=localhost,region=us-east-1,bucket=mo-iceberg')")
 q.execute("create external table if not exists ice_events(id bigint,grp bigint,v bigint,label text) engine=iceberg with ('catalog'='bulkice','namespace'='cornerbulk','table'='events','read_mode'='append_only','write_mode'='append_only')")
 q.execute('select count(*),sum(v) from ice_events');print('MO fixture',q.fetchall())
