"""Real PyIceberg typed append/read preflight; separate from 5000-case completion."""
import sys,pathlib,json,uuid,decimal,datetime,hashlib,traceback,collections
sys.path.append('/workspace/toolchains/python/lib/python3.12/site-packages')
from heavy import *
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import *
from pyiceberg.io.pyarrow import schema_to_pyarrow

decimal.getcontext().prec=100
ROOT=B/'iceberg-native-preflight';ROOT.mkdir(exist_ok=True)
cat=load_catalog('heavy_preflight',type='sql',uri='sqlite:///'+str(ROOT/'catalog.db'),warehouse='file://'+str(ROOT/'warehouse'))
namespace='phase_'+uuid.uuid4().hex[:8];cat.create_namespace(namespace);out=[]
def mapping(p):
 n=p['name']
 if n in ['tinyint','smallint','int32']:return IntegerType(),'native_int32'
 if n=='int64':return LongType(),'native_int64'
 if n in ['uint64','bit64']:return DecimalType(20,0),'explicit_unsigned_to_native_decimal20'
 if n=='decimal38_18':return DecimalType(38,18),'native_decimal38_18'
 if n=='decimal20_0':return DecimalType(20,0),'native_decimal20_0'
 if n=='double':return DoubleType(),'native_float64'
 if n=='float32':return FloatType(),'native_float32'
 if n=='boolean':return BooleanType(),'native_boolean'
 if n in ['varbinary','blob']:return BinaryType(),'native_binary'
 if n=='date':return DateType(),'native_date'
 if n=='datetime6':return TimestampType(),'native_timestamp_us'
 if n=='time6':return LongType(),'explicit_SQL_duration_to_signed_microseconds'
 if n=='uuid_text':return UUIDType(),'native_UUID_from_SQL_CHAR36'
 if n=='set':return ListType(element_id=102,element=StringType(),element_required=False),'explicit_SQL_SET_to_native_string_list'
 if n=='decimal65_30':return StringType(),'explicit_decimal65_exact_text'
 if n.startswith('json'):return StringType(),'explicit_SQL_JSON_document_string'
 if n=='enum':return StringType(),'enum_value_string_without_domain_constraint'
 return StringType(),'native_string'
def encode_value(v,p):
 if v is None:return None
 n=p['name']
 if n in ['uint64','bit64']:return decimal.Decimal(int.from_bytes(v,'big') if isinstance(v,bytes) else int(v))
 if n=='decimal65_30':return format(v,'f')
 if n=='time6':return (v.days*86400+v.seconds)*1000000+v.microseconds
 if n=='boolean':return bool(v)
 if n=='set':return sorted(v.split(',')) if v else []
 if n=='uuid_text':return uuid.UUID(v).bytes
 return v
def decode_value(v,p):
 if v is None:return None
 if p['name']=='time6':return datetime.timedelta(microseconds=int(v))
 if p['name']=='set':return ','.join(v)
 if p['name']=='uuid_text':return str(v) if isinstance(v,uuid.UUID) else str(uuid.UUID(bytes=bytes(v)))
 return v
for pi,p in enumerate(PROFILES):
 for port in [6001,13306]:
  row={'profile':p['name'],'port':port,'stage':'source','case_kind':'native_preflight_not_main_5000','status':'running'}
  try:
   source=sql('SELECT case_id,id,v,label,rev FROM t_petl_'+p['name']+' WHERE case_id=%s ORDER BY id',(100000+caseid(pi,0,0),),port=port)
   assert len(source)==32
   typ,contract=mapping(p);row.update(mapping=contract,iceberg_type=str(typ),stage='schema')
   schema=Schema(NestedField(1,'case_id',LongType(),required=False),NestedField(2,'id',LongType(),required=False),NestedField(3,'v',typ,required=False),NestedField(4,'label',StringType(),required=False),NestedField(5,'rev',LongType(),required=False))
   identifier=(namespace,p['name']+'_'+str(port));table=cat.create_table(identifier,schema=schema);row.update(identifier=list(identifier),location=table.location(),stage='native_append')
   data=pa.Table.from_pylist([dict(zip(COLS,[r[0],r[1],encode_value(r[2],p),r[3],r[4]])) for r in source],schema=schema_to_pyarrow(table.schema()))
   table.append(data);row['stage']='native_scan';scan=table.scan().to_arrow()
   actual=[[r['case_id'],r['id'],decode_value(r['v'],p),r['label'],r['rev']] for r in scan.to_pylist()]
   e=canon(source,p);a=canon(actual,p);row.update(status='passed' if a==e else 'fidelity_failed',expected_sha256=sha(e),actual_sha256=sha(a),rows=len(actual),snapshot_id=table.current_snapshot().snapshot_id)
   if a!=e:row.update(expected_sample=e[:1],actual_sample=a[:1])
  except Exception as e:row.update(status='execution_failed',error=repr(e),traceback=traceback.format_exc()[-2500:])
  out.append(row);dump(ROOT/'results.json',{'namespace':namespace,'counts':dict(collections.Counter(r['status'] for r in out)),'cases':out,'scope':'Real native typed SQL source to native Iceberg Parquet table via declared type adapters; no EOS/5000 completion claim; all created files retained'})
  print('ICEBERG_PREFLIGHT',p['name'],port,row['status'],row.get('error','')[:180],flush=True)
print('FINAL',dict(collections.Counter(r['status'] for r in out)),flush=True)
