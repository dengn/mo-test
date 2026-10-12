import json,runpy,traceback,datetime,csv,struct
from decimal import Decimal
from pathlib import Path
import pymysql,pyarrow as pa,pyarrow.parquet as pq,pandas as pd,sqlalchemy as sa
B=Path(__file__).parent;m=runpy.run_path(str(B/'type-matrix.py'));m['cases'].clear()
m['add']('decimal38_minimal','DECIMAL(38,38)',[Decimal('0.'+'0'*37+'1'),Decimal('-0.'+'0'*37+'1'),None],pa.decimal128(38,38))
m['add']('decimal65_integer','DECIMAL(65,0)',[Decimal('9'*65),Decimal('-'+'9'*65),None],pa.decimal256(65,0))
m['add']('decimal65_fraction','DECIMAL(65,65)',[Decimal('0.'+'9'*65),Decimal('-0.'+'9'*65),Decimal('0.'+'0'*64+'1'),None],pa.decimal256(65,65))
x=m['run']();(B/'semantic-matrix-result.json').write_text(json.dumps(x,indent=2,default=str))
out={'cases':[]}
def check(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:260],flush=True)
def conn(port=6001,database='type_matrix'):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database=database,autocommit=True)
def decimal_adapt():
 variants=['.'+'0'*37+'1','-.'+'0'*37+'1','.'+'9'*38,'-.'+'9'*38]
 with conn() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS decimal_text_adapter');c.execute('CREATE TABLE decimal_text_adapter(id INT PRIMARY KEY,v DECIMAL(38,38))');c.executemany('INSERT INTO decimal_text_adapter VALUES(%s,%s)',list(enumerate(variants,1)));c.execute('SELECT v FROM decimal_text_adapter ORDER BY id');got=[r[0] for r in c.fetchall()];assert got==[Decimal(v) for v in variants],got
 return {'input':variants,'output':got,'diagnostic_workaround':'omit leading zero before decimal point, full precision preserved'}
check('decimal38_text_adapter_all_boundaries',decimal_adapt)
def json_contract():
 with conn() as d,d.cursor() as c:
  c.execute('SELECT id,v FROM reject_json_jsonline ORDER BY id');a=[(r[0],json.loads(r[1])) for r in c.fetchall()];assert a==[(1,'{}'),(2,'{invalid')],a
  p=B/'actually-invalid-jsonline.jsonl';p.write_text('{"id":1,"v":{}}\n{"id":2,"v":{invalid}\n')
  c.execute('DROP TABLE IF EXISTS json_syntax_reject');c.execute('CREATE TABLE json_syntax_reject(id INT PRIMARY KEY,v JSON)')
  try:c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='jsonline','jsondata'='object'}} INTO TABLE json_syntax_reject");raise AssertionError('malformed JSON line accepted')
  except pymysql.MySQLError as e:error=str(e)
  c.execute('SELECT count(*) FROM json_syntax_reject');n=c.fetchone()[0];assert n==0,n;c.execute("INSERT INTO json_syntax_reject VALUES(3,'{}')")
 return {'quoted_strings_are_valid_JSON_values':a,'malformed_line_error':error,'rows_after_failed_batch':n,'next_valid_write':'passed','initial_probe_failure':'incorrect oracle expected a quoted JSON string to be rejected'}
check('JSON_string_vs_document_and_actual_syntax_rejection',json_contract)
def spatial_typemod(engine):
 port=6001 if engine=='matrixone' else 13306
 with conn(port) as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS spatial_srid_explicit');c.execute('CREATE TABLE spatial_srid_explicit(id INT PRIMARY KEY,g GEOMETRY SRID 4326)')
  wkt='POINT(1.25 -2.5)';c.execute('INSERT INTO spatial_srid_explicit VALUES(1,ST_GeomFromText(%s,4326))',(wkt,));c.execute('INSERT INTO spatial_srid_explicit VALUES(2,NULL)');c.execute('SELECT id,ST_AsWKB(g),ST_SRID(g),ST_AsText(g) FROM spatial_srid_explicit ORDER BY id');rs=c.fetchall();assert rs[0][2]==4326,rs
  c.execute('UPDATE spatial_srid_explicit SET g=ST_GeomFromWKB(%s,4326) WHERE id=1',(rs[0][1],));c.execute('SELECT id,ST_AsWKB(g),ST_SRID(g),ST_AsText(g) FROM spatial_srid_explicit ORDER BY id');z=c.fetchall();assert rs==z
 return {'explicit_column_SRID':4326,'values':rs,'WKB_roundtrip':'exact','generic_GEOMETRY_SRID_behavior':'MatrixOne SRID is stored in SQL type metadata; generic column defaults to 0, MySQL preserves per-value SRID'}
for engine in ['matrixone','mysql']:check(engine+'_explicit_geometry_SRID_roundtrip',lambda engine=engine:spatial_typemod(engine))
for engine,port,pw in [('matrixone',6001,'111'),('mysql',13306,'types-local')]:
 def pandas_no_binary(port=port,pw=pw):
  e=sa.create_engine(f'mysql+pymysql://root:{pw}@127.0.0.1:{port}/tool_types')
  try:
   f=pd.read_sql(sa.text('SELECT id,large_signed,large_unsigned,precise,name,ts FROM typed_rows ORDER BY id'),e,coerce_float=False,dtype_backend='pyarrow');rs=f.to_dict('records')
   return {'dtypes':str(f.dtypes),'rows':rs,'signed_exact':rs[0]['large_signed']==9007199254740993,'unsigned_exact':rs[0]['large_unsigned']==18446744073709551615,'decimal_exact':rs[0]['precise']==Decimal('12345678901234567890.123456789012345678')}
  finally:e.dispose()
 check(engine+'_pandas_Arrow_without_binary_observation',pandas_no_binary)
 def pandas_adapter(port=port,pw=pw):
  e=sa.create_engine(f'mysql+pymysql://root:{pw}@127.0.0.1:{port}/tool_types')
  try:
   q='SELECT id,CAST(large_signed AS CHAR) AS large_signed,CAST(large_unsigned AS CHAR) AS large_unsigned,CAST(precise AS CHAR) AS precise,HEX(payload) AS payload,name,ts FROM typed_rows ORDER BY id';f=pd.read_sql(sa.text(q),e,coerce_float=False,dtype_backend='pyarrow');r=f.to_dict('records')[0];assert int(r['large_signed'])==9007199254740993 and int(r['large_unsigned'])==18446744073709551615 and Decimal(r['precise'])==Decimal('12345678901234567890.123456789012345678') and bytes.fromhex(r['payload'])==b'\x00\xff\x80abc' and r['ts'].microsecond==123456
   return {'dtypes':str(f.dtypes),'rows':f.to_dict('records'),'adaptation':'explicit text integer/decimal and HEX binary in source SQL; validated decoded values'}
  finally:e.dispose()
 check(engine+'_pandas_Arrow_numeric_and_binary_envelope_adapter',pandas_adapter)
(B/'semantic-retest-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)))
