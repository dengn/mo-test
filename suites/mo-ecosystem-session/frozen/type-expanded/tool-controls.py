import connectorx as cx,ibis,pymysql,json,traceback,pandas as pd,sqlalchemy as sa,pyarrow as pa
from decimal import Decimal
from pathlib import Path
B=Path(__file__).parent
out={'cases':[]}
want=Decimal('12345678901234567890.123456789012345678')
with pymysql.connect(host='127.0.0.1',port=13306,user='root',password='types-local',autocommit=True) as d:
 with d.cursor() as c:
  c.execute('CREATE DATABASE IF NOT EXISTS tool_types');c.execute('DROP TABLE IF EXISTS tool_types.typed_rows');c.execute('CREATE TABLE tool_types.typed_rows(id BIGINT PRIMARY KEY,large_signed BIGINT,large_unsigned BIGINT UNSIGNED,precise DECIMAL(38,18),payload VARBINARY(100),name VARCHAR(100),ts DATETIME(6),doc JSON)')
  c.execute("INSERT INTO tool_types.typed_rows VALUES(1,9007199254740993,18446744073709551615,12345678901234567890.123456789012345678,x'00ff80616263','中文 😀','2026-10-10 12:00:00.123456','{\"n\":9007199254740993}'),(2,-9223372036854775808,0,-12345678901234567890.123456789012345678,x'','','2026-10-11 00:00:00','[]'),(3,NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
def case(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:300],flush=True)
for engine,port,pw in [('matrixone',6001,'111'),('mysql',13306,'types-local')]:
 def cx_direct(port=port,pw=pw):
  t=cx.read_sql(f'mysql://root:{pw}@127.0.0.1:{port}/tool_types','SELECT * FROM typed_rows ORDER BY id',return_type='arrow');a=t.to_pylist();assert a[0]['precise']==want,(a[0],want);return a
 case(engine+'_connectorx_default_precision',cx_direct)
 def cx_adapted(port=port,pw=pw):
  q='SELECT id,large_signed,large_unsigned,CAST(precise AS CHAR) AS precise,payload,name,ts FROM typed_rows ORDER BY id'
  t=cx.read_sql(f'mysql://root:{pw}@127.0.0.1:{port}/tool_types',q,return_type='arrow');a=t.to_pylist();assert a[0]['large_signed']==9007199254740993 and a[0]['large_unsigned']==18446744073709551615;assert Decimal(a[0]['precise'])==want;assert a[0]['ts'].microsecond==123456;assert a[0]['payload']==b'\x00\xff\x80abc'
  return {'rows':a,'schema':str(t.schema),'adaptation':'cast decimal to text in source SQL; Decimal reconstruction verified'}
 case(engine+'_connectorx_decimal_text_adaptation',cx_adapted)
 def ibis_direct(port=port,pw=pw):
  con=ibis.mysql.connect(host='127.0.0.1',port=port,user='root',password=pw,database='tool_types')
  try:
   t=con.table('typed_rows');a=t.order_by('id').execute().to_dict(orient='records')
   # Return observed loss as a control receipt; exact preservation is asserted separately.
   return {'schema':str(t.schema()),'rows':a,'signed_exact':a[0]['large_signed']==9007199254740993,'unsigned_exact':a[0]['large_unsigned']==18446744073709551615,'decimal_exact':a[0]['precise']==want}
  finally:con.disconnect()
 case(engine+'_ibis_default_observation',ibis_direct)
 def ibis_adapted(port=port,pw=pw):
  con=ibis.mysql.connect(host='127.0.0.1',port=port,user='root',password=pw,database='tool_types')
  try:
   t=con.sql('SELECT id,CAST(large_signed AS CHAR) AS large_signed,CAST(large_unsigned AS CHAR) AS large_unsigned,CAST(precise AS CHAR) AS precise,payload,name,ts FROM typed_rows')
   a=t.order_by('id').execute().to_dict(orient='records');assert int(a[0]['large_signed'])==9007199254740993;assert int(a[0]['large_unsigned'])==18446744073709551615;assert Decimal(a[0]['precise'])==want;assert a[0]['ts'].microsecond==123456;return a
  finally:con.disconnect()
 case(engine+'_ibis_numeric_text_adaptation',ibis_adapted)
 def pandas_arrow(port=port,pw=pw):
  e=sa.create_engine(f'mysql+pymysql://root:{pw}@127.0.0.1:{port}/tool_types')
  try:
   f=pd.read_sql(sa.text('SELECT * FROM typed_rows ORDER BY id'),e,coerce_float=False,dtype_backend='pyarrow');a=f.to_dict(orient='records');assert a[0]['large_signed']==9007199254740993;assert a[0]['large_unsigned']==18446744073709551615;assert a[0]['precise']==want;return {'rows':a,'dtypes':str(f.dtypes)}
  finally:e.dispose()
 case(engine+'_pandas_arrow_nullable_integer_and_decimal',pandas_arrow)
(B/'tool-controls-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)))
