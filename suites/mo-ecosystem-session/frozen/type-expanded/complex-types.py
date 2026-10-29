import csv,json,traceback
from pathlib import Path
import pymysql,pyarrow as pa,pyarrow.parquet as pq
B=Path(__file__).parent;out={'cases':[]}
def conn():return pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='type_matrix',autocommit=True)
def save(t,p,fmt):
 if fmt=='parquet':pq.write_table(t,p)
 else:
  with pa.OSFile(str(p),'wb') as f:
   with pa.ipc.new_file(f,t.schema) as w:w.write_table(t)
def load(c,name,p,fmt):
 ext=",'jsondata'='object'" if fmt=='jsonline' else '';csvopts=" FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' ESCAPED BY ''" if fmt=='csv' else '';c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='{fmt}'{ext}}} INTO TABLE {name}{csvopts}")
def check(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:240],flush=True)
def spatial_files(fmt):
 vals=['POINT(1.25 -2.5)','LINESTRING(0 0,1 1,2 -1)',None];p=B/('spatial-file.'+fmt)
 if fmt=='csv':
  with p.open('w',newline='') as f:csv.writer(f,quoting=csv.QUOTE_ALL).writerows((i+1,v if v is not None else '\\N') for i,v in enumerate(vals))
 elif fmt=='jsonline':p.write_text(''.join(json.dumps({'id':i+1,'v':v})+'\n' for i,v in enumerate(vals)))
 else:save(pa.table({'id':pa.array([1,2,3],pa.int32()),'v':pa.array(vals,pa.string())}),p,fmt)
 name='spatial_'+fmt
 with conn() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS '+name);c.execute('CREATE TABLE '+name+'(id INT PRIMARY KEY,v GEOMETRY SRID 4326)');load(c,name,p,fmt);c.execute('SELECT id,ST_AsText(v),ST_SRID(v) FROM '+name+' ORDER BY id');a=c.fetchall();assert a==((1,vals[0],4326),(2,vals[1],4326),(3,None,None)),a
 return {'values':a,'SRID_preserved':True}
for fmt in ['csv','jsonline','parquet','arrow']:check('geometry_WKT_'+fmt,lambda fmt=fmt:spatial_files(fmt))
def spatial_binary_stage(fmt):
 with conn() as d,d.cursor() as c:
  c.execute('SELECT id,ST_AsWKB(v) FROM spatial_csv ORDER BY id');a=c.fetchall();t=pa.table({'id':pa.array([r[0] for r in a],pa.int32()),'v':pa.array([r[1] for r in a],pa.binary())});p=B/('spatial-WKB-stage.'+fmt);save(t,p,fmt)
  stage='spatial_binary_'+fmt;target='spatial_from_binary_'+fmt;c.execute('DROP TABLE IF EXISTS '+stage);c.execute('CREATE TABLE '+stage+'(id INT PRIMARY KEY,v VARBINARY(1000))');load(c,stage,p,fmt);c.execute('DROP TABLE IF EXISTS '+target);c.execute('CREATE TABLE '+target+'(id INT PRIMARY KEY,v GEOMETRY SRID 4326)');c.execute('INSERT INTO '+target+' SELECT id,ST_GeomFromWKB(v,4326) FROM '+stage);c.execute('SELECT id,ST_AsWKB(v),ST_SRID(v) FROM '+target+' ORDER BY id');z=c.fetchall();assert [r[:2] for r in z]==list(a),z;assert z[0][2]==4326
 return {'rows':z,'all_WKB_bytes_exact':True,'explicit_SRID':4326}
for fmt in ['parquet','arrow']:check(fmt+'_WKB_binary_staging_to_geometry',lambda fmt=fmt:spatial_binary_stage(fmt))
def nested_map(fmt):
 vals=[[('中文',9007199254740993),('empty',0)],None];ty=pa.map_(pa.string(),pa.int64());t=pa.table({'id':pa.array([1,2],pa.int32()),'v':pa.array(vals,ty)});p=B/('nested-map.'+fmt);save(t,p,fmt);name='nested_map_'+fmt
 with conn() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS '+name);c.execute('CREATE TABLE '+name+'(id INT PRIMARY KEY,v JSON)');load(c,name,p,fmt);c.execute('SELECT v FROM '+name+' ORDER BY id');a=[json.loads(r[0]) if r[0] is not None else None for r in c.fetchall()];assert a==[{'中文':9007199254740993,'empty':0},None],a
 return a
for fmt in ['parquet','arrow']:check(fmt+'_nested_map_to_JSON',lambda fmt=fmt:nested_map(fmt))
def arrow_dictionary():
 a=pa.array(['中文','',None,'中文']).dictionary_encode();t=pa.table({'id':pa.array([1,2,3,4],pa.int32()),'v':a});p=B/'dictionary.arrow';save(t,p,'arrow')
 with conn() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS arrow_dictionary');c.execute('CREATE TABLE arrow_dictionary(id INT PRIMARY KEY,v VARCHAR(100))');load(c,'arrow_dictionary',p,'arrow');c.execute('SELECT v FROM arrow_dictionary ORDER BY id');a=[r[0] for r in c.fetchall()];assert a==['中文','',None,'中文'],a
 return {'schema':str(t.schema),'values':a}
check('Arrow_dictionary_encoded_categorical_to_VARCHAR',arrow_dictionary)
(B/'complex-types-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)))
