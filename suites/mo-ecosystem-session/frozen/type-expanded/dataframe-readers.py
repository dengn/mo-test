import connectorx as cx,ibis,pymysql,json,traceback,datetime
from decimal import Decimal
from pathlib import Path
B=Path(__file__).parent
out={'connectorx':cx.__version__,'ibis':ibis.__version__,'cases':[]}
d=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',autocommit=True)
with d:
 with d.cursor() as c:
  c.execute('CREATE DATABASE IF NOT EXISTS tool_types');c.execute('DROP TABLE IF EXISTS tool_types.typed_rows');c.execute('CREATE TABLE tool_types.typed_rows(id BIGINT PRIMARY KEY,large_signed BIGINT,large_unsigned BIGINT UNSIGNED,precise DECIMAL(38,18),payload VARBINARY(100),name VARCHAR(100),ts DATETIME(6),doc JSON)')
  c.execute("INSERT INTO tool_types.typed_rows VALUES(1,9007199254740993,18446744073709551615,12345678901234567890.123456789012345678,x'00ff80616263','中文 😀','2026-10-10 12:00:00.123456','{\"n\":9007199254740993}'),(2,-9223372036854775808,0,-12345678901234567890.123456789012345678,x'','','2026-10-11 00:00:00','[]'),(3,NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
def case(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:300],flush=True)
def connectorx_read():
 t=cx.read_sql('mysql://root:111@127.0.0.1:6001/tool_types','SELECT * FROM typed_rows ORDER BY id',return_type='arrow')
 a=t.to_pylist();assert a[0]['large_signed']==9007199254740993;assert a[0]['large_unsigned']==18446744073709551615;assert a[0]['precise']==Decimal('12345678901234567890.123456789012345678'),a[0];assert a[0]['payload']==b'\x00\xff\x80abc';assert a[0]['ts'].microsecond==123456
 assert a[1]['name']=='' and a[1]['payload']==b'' and a[2]['name'] is None
 return {'rows':a,'schema':str(t.schema)}
case('connectorx_arrow_exact_types',connectorx_read)
def connectorx_partition():
 t=cx.read_sql('mysql://root:111@127.0.0.1:6001/tool_types','SELECT id,name,large_signed FROM typed_rows',return_type='arrow',partition_on='id',partition_num=2)
 a=sorted(t.to_pylist(),key=lambda x:x['id']);assert len(a)==3 and a[0]['large_signed']==9007199254740993;return a
case('connectorx_partitioned_arrow_read',connectorx_partition)
con=None
try:
 con=ibis.mysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='tool_types')
 def ibis_read():
  t=con.table('typed_rows');df=t.order_by('id').execute();a=df.to_dict(orient='records');assert a[0]['large_signed']==9007199254740993;assert a[0]['large_unsigned']==18446744073709551615;assert a[0]['precise']==Decimal('12345678901234567890.123456789012345678');assert a[0]['ts'].microsecond==123456
  return {'rows':a,'schema':str(t.schema())}
 case('ibis_mysql_exact_types',ibis_read)
 def ibis_transform():
  t=con.table('typed_rows');e=t.filter(t.id<3).select(t.id,t.name,t.precise);a=e.execute().to_dict(orient='records');assert len(a)==2 and a[0]['precise']==Decimal('12345678901234567890.123456789012345678');return {'sql':ibis.to_sql(e),'rows':a}
 case('ibis_mysql_filter_projection',ibis_transform)
except Exception as e:out['cases'].append({'name':'ibis_mysql_connect','status':'failed','error':str(e)});traceback.print_exc()
finally:
 if con is not None:con.disconnect()
(B/'dataframe-readers-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)))
