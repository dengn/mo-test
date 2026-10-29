"""Actual PyIceberg append/scan bridge; explicit type and SQL effects adapters.

No service startup or catalog mutation on import. Native files are retained.
"""
import sys,uuid,json,datetime,decimal,threading,time,collections
from pathlib import Path
sys.path.append('/workspace/toolchains/python/lib/python3.12/site-packages')
import heavy as h
import pyarrow as pa,pyarrow.compute as pc
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField,LongType,IntegerType,DecimalType,FloatType,DoubleType,BooleanType,BinaryType,DateType,TimestampType,UUIDType,ListType,StringType
from pyiceberg.io.pyarrow import schema_to_pyarrow
from pyiceberg.expressions import EqualTo
import recycle_profile as recycle

ROOT=h.B/'iceberg-native';CAT=None;META_LOCK=threading.RLock();LOG_LOCK=threading.Lock();LOAD_SLOTS=threading.Semaphore(2);WINDOWS={};TABLES={}
def catalog():
 global CAT
 with META_LOCK:
  if CAT is None:
   ROOT.mkdir(exist_ok=True)
   CAT=load_catalog('heavy_bridge',type='sql',uri='sqlite:///'+str(ROOT/'catalog.db'),warehouse='file://'+str(ROOT/'warehouse'))
  return CAT
def mapping(p):
 n=p['name']
 if n in ['tinyint','smallint','int32']:return IntegerType(),'native_int32'
 if n=='int64':return LongType(),'native_int64'
 if n in ['uint64','bit64']:return DecimalType(20,0),'explicit_unsigned_to_native_decimal20'
 if n=='decimal38_18':return DecimalType(38,18),'native_decimal38_18'
 if n=='decimal20_0':return DecimalType(20,0),'native_decimal20_0'
 if n=='double':return DoubleType(),'native_float64'
 if n=='float32':return FloatType(),'native_float32_six_significant_digit_oracle'
 if n=='boolean':return BooleanType(),'native_boolean'
 if n in ['varbinary','blob']:return BinaryType(),'native_binary'
 if n=='date':return DateType(),'native_date'
 if n=='datetime6':return TimestampType(),'native_timestamp_us'
 if n=='time6':return LongType(),'explicit_duration_to_signed_microseconds'
 if n=='uuid_text':return UUIDType(),'explicit_SQL_UUID_text_to_native_UUID'
 if n=='set':return ListType(element_id=102,element=StringType(),element_required=False),'explicit_SQL_SET_to_native_list'
 if n=='decimal65_30':return StringType(),'explicit_decimal65_exact_string'
 if n.startswith('json'):return StringType(),'explicit_JSON_document_string'
 if n=='enum':return StringType(),'enum_value_string_without_domain_enforcement'
 return StringType(),'native_string'
def encode(v,p):
 if v is None:return None
 n=p['name']
 if n in ['uint64','bit64']:return decimal.Decimal(int.from_bytes(v,'big') if isinstance(v,bytes) else int(v))
 if n=='decimal65_30':return format(v,'f')
 if n=='time6':return (v.days*86400+v.seconds)*1000000+v.microseconds
 if n=='boolean':return bool(v)
 if n=='set':return sorted(v.split(',')) if v else []
 if n=='uuid_text':return uuid.UUID(v).bytes
 return v
def decode(v,p):
 if v is None:return None
 if p['name'] in ['uint64','bit64']:return int(v)
 if p['name']=='time6':return datetime.timedelta(microseconds=int(v))
 if p['name']=='set':return ','.join(v)
 if p['name']=='uuid_text':return str(v) if isinstance(v,uuid.UUID) else str(uuid.UUID(bytes=bytes(v)))
 return v
def get_table(p,target,role,added):
 with META_LOCK:
  cat=catalog();window=WINDOWS.get(p['name'])
  if window is None:
   window='w_'+p['name']+'_'+uuid.uuid4().hex[:10];cat.create_namespace(window);WINDOWS[p['name']]=window
  key=(window,target,role)
  if key not in TABLES:
   typ,_=mapping(p)
   schema=Schema(NestedField(1,'case_id',LongType(),required=True),NestedField(2,'id',LongType(),required=True),NestedField(3,'v',typ,required=False),NestedField(4,'label',StringType(),required=False),NestedField(5,'rev',LongType(),required=False),NestedField(6,'load_id',StringType(),required=True))
   TABLES[key]=cat.create_table((window,target+'_'+str(role)),schema=schema)
  table=TABLES[key]
  if added and 'added_tag' not in [f.name for f in table.schema().fields]:
   with table.update_schema() as change:change.add_column('added_tag',StringType())
  return cat,cat.load_table((window,target+'_'+str(role))),key
original_load=h.load
def load(route,p,target,rows,role,token,transform=None):
 if route!='pyiceberg':return original_load(route,p,target,rows,role,token,transform)
 decimal.getcontext().prec=100
 with LOAD_SLOTS:
  h.guard();columns={x[0] for x in h.sql('SHOW COLUMNS FROM '+target,port=role)};added='added_tag' in columns
  cat,t,key=get_table(p,target,role,added);uid=uuid.uuid4().hex;start=time.monotonic()
  data=[dict(zip(h.COLS,[r[0],r[1],encode(r[2],p),r[3],r[4]]),load_id=uid,**({'added_tag':'演进😀'} if added else {})) for r in rows]
  arrow=pa.Table.from_pylist(data,schema=schema_to_pyarrow(t.schema()))
  if transform is not None:
   arrow=arrow.filter(pc.equal(pc.bit_wise_and(arrow['id'],pa.scalar(1,pa.int64())),pa.scalar(transform%2,pa.int64())))
   arrow=arrow.set_column(arrow.schema.get_field_index('label'),'label',pc.binary_join_element_wise(arrow['label'],pa.scalar('→ETL'+str(transform)),pa.scalar('')))
   arrow=arrow.set_column(arrow.schema.get_field_index('rev'),'rev',pc.add(arrow['rev'],transform+1))
  result={'token':token,'role':role,'actual_endpoint':h.endpoint(role)['port'],'profile':p['name'],'SQL_target':target,'native_identifier':list(t.name()),'mapping':mapping(p)[1],'native_input_rows':len(rows),'native_transformed_rows':len(arrow),'native_PK_enforcement':'Iceberg append does not enforce SQL primary-key uniqueness; SQL sink integrity/rollback is explicit adapter','bridge_scope':'Native typed PyIceberg append+scan then explicit DBAPI SQL sink; SQL effect/replay/DDL adapters; not official native MO connector or native EOS','load_id':uid,'commit_retries':0}
  try:
   for attempt in range(8):
    try:t.append(arrow);break
    except Exception as e:
     # Retry only local catalog CAS/lock conflicts. A unique load_id detects
     # a successful commit whose acknowledgment failed before re-append.
     if not any(x in str(e).lower() for x in ['concurrent','commit failed','requirement failed','database is locked','table metadata','has changed']):raise
     result['commit_retries']+=1;t=cat.load_table(key[:1]+(target+'_'+str(role),));time.sleep(.05*(attempt+1))
     existing=t.scan(row_filter=EqualTo('load_id',uid)).to_arrow()
     if len(existing):break
   else:raise RuntimeError('PyIceberg catalog conflict retries exhausted')
   records=t.scan(row_filter=EqualTo('load_id',uid)).to_arrow().to_pylist()
   actual=[[r['case_id'],r['id'],decode(r['v'],p),r['label'],r['rev']] for r in records]
   expected=[[r['case_id'],r['id'],decode(r['v'],p),r['label'],r['rev']] for r in arrow.to_pylist()]
   assert h.canon(actual,p)==h.canon(expected,p),'Native Iceberg roundtrip changed full values or multiplicity'
   if added:assert all(r['added_tag']=='演进😀' for r in records)
   result.update(native_rows=len(actual),native_sha256=h.sha(h.canon(actual,p)),snapshot_id=t.current_snapshot().snapshot_id,schema_id=t.schema().schema_id)
   with h.db(role,autocommit=False) as d,d.cursor() as c:
    if added:
     c.executemany('INSERT INTO '+target+'(case_id,id,v,label,rev,added_tag) VALUES(%s,%s,%s,%s,%s,%s)',[r+['演进😀'] for r in actual])
    else:c.executemany('INSERT INTO '+target+'(case_id,id,v,label,rev) VALUES(%s,%s,%s,%s,%s)',actual)
    d.commit()
   result['status']='native_and_SQL_sink_completed'
  except Exception as e:result.update(status='exception_preserved',error=repr(e));raise
  finally:
   result['elapsed_s']=time.monotonic()-start
   with LOG_LOCK,(ROOT/'loads.jsonl').open('a') as f:f.write(json.dumps(result,ensure_ascii=False,default=str)+'\n')
h.load=load
original_run_case=h.run_case
def run_case(route,*args,**kwargs):
 r=original_run_case(route,*args,**kwargs)
 if route=='pyiceberg':
  r['path']='Native PyIceberg typed append/scan with explicit scalar mappings and DBAPI SQL sink; effects/replay/DDL are SQL adapters'
  r['scope']='File/catalog+SQL interoperability; not official MO connector, raw default type mapping or native cross-system EOS'
  if 'native_duplicate_rejection' in r:
   r['SQL_sink_duplicate_rejection']=r.pop('native_duplicate_rejection')
   r['native_duplicate_policy']='Iceberg append accepts duplicate identifiers; rejection and rollback verified at explicit SQL sink'
 return r
h.run_case=run_case
if 'pyiceberg' not in h.ROUTES:h.ROUTES.append('pyiceberg')
old_archive=recycle.archive_profile
def archive(route,profile,apply=False):
 result=old_archive(route,profile,apply)
 if route=='pyiceberg' and apply:
  with META_LOCK:
   window=WINDOWS.pop(profile,None)
   if window:
    for key in list(TABLES):
     if key[0]==window:del TABLES[key]
  result['native_Iceberg_files_retained']=True
 return result
recycle.archive_profile=archive
