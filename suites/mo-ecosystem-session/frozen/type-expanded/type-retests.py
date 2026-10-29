import json,runpy,datetime,csv,traceback
from decimal import Decimal
from pathlib import Path
import pymysql,pyarrow as pa,pyarrow.parquet as pq
B=Path(__file__).parent
m=runpy.run_path(str(B/'type-matrix.py'));cases={c['name']:c for c in m['cases']}
out={'cases':[]};d=pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='type_matrix',autocommit=True)
def check(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:220],flush=True)
def create(c,name):
 with d.cursor() as cur:cur.execute('DROP TABLE IF EXISTS '+name);cur.execute(f'CREATE TABLE {name}(id INT PRIMARY KEY,v {c["ddl"]})')
def csv_escape():
 c=cases['utf8_control'];name='csv_rfc4180';create(c,name)
 p=B/'utf8_control.csv'
 with d.cursor() as cur:cur.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='csv'}} INTO TABLE {name} FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' ESCAPED BY '' LINES TERMINATED BY '\\r\\n'")
 return m['oracle'](d,name,c)
check('csv_rfc4180_explicit_escape_and_line_options',csv_escape)
def timedelta_text():
 c=cases['duration_time'];name='duration_text_binding';create(c,name)
 with d.cursor() as cur:cur.executemany('INSERT INTO '+name+' VALUES(%s,%s)',[(i+1,m['text'](v,'time')) for i,v in enumerate(c['values'])])
 return m['oracle'](d,name,c)
check('negative_duration_explicit_string_binding',timedelta_text)
def vector_json_string():
 c=cases['vector64'];name='vec_json_string';create(c,name);p=B/'vec-json-string.jsonl'
 p.write_text(''.join(json.dumps({'id':i+1,'v':json.dumps(v) if v is not None else None})+'\n' for i,v in enumerate(c['values'])))
 with d.cursor() as cur:cur.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='jsonline','jsondata'='object'}} INTO TABLE {name}")
 return m['oracle'](d,name,c)
check('json_vector_serialized_array_string',vector_json_string)
def arrow_stage(cname,cast_expr=None):
 c=cases[cname];name=cname+'_stage';create({'ddl':'VARCHAR(500)'},name);vals=[m['text'](v,c['family']) for v in c['values']]
 t=pa.table({'id':pa.array(range(1,len(vals)+1),pa.int32()),'v':pa.array(vals,pa.string())});p=B/(name+'.arrow')
 with pa.OSFile(str(p),'wb') as f:
  with pa.ipc.new_file(f,t.schema) as w:w.write_table(t)
 with d.cursor() as cur:cur.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='arrow'}} INTO TABLE {name}")
 target=cname+'_from_stage';create(c,target)
 with d.cursor() as cur:cur.execute(f'INSERT INTO {target} SELECT id,{cast_expr or "v"} FROM {name}')
 return m['oracle'](d,target,c)
for cname in ['json_rich','uuid_type','enum_type','set_type','vector64']:
 check(cname+'_arrow_text_staging',lambda cname=cname:arrow_stage(cname))
def bit_stage():
 c=cases['bit64'];target='bit_from_arrow_stage';create(c,target)
 with d.cursor() as cur:cur.execute('INSERT INTO '+target+' SELECT id,v FROM big_unsigned_arrow')
 return m['oracle'](d,target,c)
check('bit64_arrow_uint64_staging_assignment',bit_stage)
def binary_envelope():
 c=cases['bytes_raw'];name='binary_hex_stage';create({'ddl':'VARCHAR(100)'},name);p=B/'binary-envelope.jsonl'
 p.write_text(''.join(json.dumps({'id':i+1,'v':v.hex() if v is not None else None})+'\n' for i,v in enumerate(c['values'])))
 with d.cursor() as cur:cur.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='jsonline','jsondata'='object'}} INTO TABLE {name}")
 target='binary_decoded';create(c,target)
 with d.cursor() as cur:cur.execute('INSERT INTO '+target+' SELECT id,UNHEX(v) FROM '+name)
 return m['oracle'](d,target,c)
check('json_binary_hex_envelope_decode',binary_envelope)
def nested_arrow(fmt):
 vals=[{'n':9007199254740993,'labels':['中文','',None]},None]
 ty=pa.struct([('n',pa.int64()),('labels',pa.list_(pa.string()))]);t=pa.table({'id':pa.array([1,2],pa.int32()),'v':pa.array(vals,ty)});p=B/('nested.'+fmt)
 if fmt=='parquet':pq.write_table(t,p)
 else:
  with pa.OSFile(str(p),'wb') as f:
   with pa.ipc.new_file(f,t.schema) as w:w.write_table(t)
 target='nested_'+fmt;create({'ddl':'JSON'},target)
 with d.cursor() as cur:cur.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='{fmt}'}} INTO TABLE {target}");cur.execute('SELECT v FROM '+target+' ORDER BY id');got=[json.loads(r[0]) if r[0] is not None else None for r in cur.fetchall()]
 assert got==vals,(got,vals);return got
check('parquet_nested_struct_list_to_json',lambda:nested_arrow('parquet'));check('arrow_nested_struct_list_to_json',lambda:nested_arrow('arrow'))
def reject_vector_shape():
 c=cases['vector64'];name='vec_reject';create(c,name);p=B/'bad-vector.jsonl';p.write_text('{"id":1,"v":"[1,2,3]"}\n{"id":2,"v":"[1,2]"}\n')
 try:
  with d.cursor() as cur:cur.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='jsonline','jsondata'='object'}} INTO TABLE {name}")
  raise AssertionError('wrong vector shape accepted')
 except pymysql.MySQLError as e:error=str(e)
 with d.cursor() as cur:cur.execute('SELECT count(*) FROM '+name);count=cur.fetchone()[0];assert count==0;cur.execute('INSERT INTO '+name+" VALUES(3,'[1,2,3]')")
 return {'rejection':error,'partial_rows':count,'next_write':'passed'}
check('vector_wrong_shape_atomic_rejection_and_recovery',reject_vector_shape)
d.close();(B/'type-retest-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
