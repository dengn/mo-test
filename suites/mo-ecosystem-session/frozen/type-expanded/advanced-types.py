import json,datetime,runpy,traceback,struct,csv
from decimal import Decimal
from pathlib import Path
import pymysql,pyarrow as pa,pyarrow.parquet as pq
B=Path(__file__).parent
m=runpy.run_path(str(B/'type-matrix.py'))
m['cases'].clear()
m['add']('decimal65_30','DECIMAL(65,30)',[Decimal('9'*35+'.'+'9'*30),Decimal('-'+'9'*35+'.'+'9'*30),Decimal('0.'+'0'*29+'1'),None],pa.decimal256(65,30))
m['add']('decimal76_0','DECIMAL(76,0)',[Decimal('9'*76),Decimal('-'+'9'*76),None],pa.decimal256(76,0))
m['add']('decimal76_76','DECIMAL(76,76)',[Decimal('0.'+'9'*76),Decimal('-0.'+'9'*76),Decimal('0.'+'0'*75+'1'),None],pa.decimal256(76,76))
matrix=m['run']();(B/'advanced-matrix-result.json').write_text(json.dumps(matrix,indent=2,default=str))
out={'cases':[]}
def check(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:250],flush=True)
def db(engine='matrixone'):
 return pymysql.connect(host='127.0.0.1',port=6001 if engine=='matrixone' else 13306,user='root',password='111' if engine=='matrixone' else 'types-local',database='type_matrix',autocommit=True)
def decimal_text_boundary():
 obs=[]
 with db() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS decimal38_parser');c.execute('CREATE TABLE decimal38_parser(id INT PRIMARY KEY,v DECIMAL(38,38))')
  variants=['0.'+'9'*38,'.'+'9'*38,'-0.'+'9'*38,'-.'+'9'*38,'0.1','0.'+'0'*37+'1']
  for i,v in enumerate(variants,1):
   r={'input':v}
   try:c.execute('INSERT INTO decimal38_parser VALUES(%s,%s)',(i,v));c.execute('SELECT v FROM decimal38_parser WHERE id=%s',(i,));got=c.fetchone()[0];r.update(accepted=True,value=str(got),exact=got==Decimal(v))
   except pymysql.MySQLError as e:r.update(accepted=False,error=str(e))
   obs.append(r)
  c.execute('INSERT INTO decimal38_parser SELECT id+100,v FROM decimal38_38_parquet');c.execute('SELECT v FROM decimal38_parser WHERE id=101');got=c.fetchone()[0];assert got==Decimal('0.'+'9'*38)
 return {'text_variants':obs,'typed_assignment_exact':str(got)}
check('decimal38_leading_zero_parser_counterexample',decimal_text_boundary)
def time_bounds(engine):
 obs=[]
 with db(engine) as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS time_contract');c.execute('CREATE TABLE time_contract(id INT PRIMARY KEY,v TIME(6))')
  for i,v in enumerate(['-00:00:00.000001','-24:00:00.123456','838:59:59.000000','838:59:59.999999','-838:59:59.999999','839:00:00.000000'],1):
   r={'input':v}
   try:c.execute('INSERT INTO time_contract VALUES(%s,%s)',(i,v));c.execute('SELECT v FROM time_contract WHERE id=%s',(i,));got=c.fetchone()[0];r.update(accepted=True,value=str(got),value_us=int(got.total_seconds()*1000000))
   except pymysql.MySQLError as e:r.update(accepted=False,error=str(e))
   obs.append(r)
  if engine=='matrixone':
   c.execute('SELECT v FROM duration_time_csv ORDER BY id');obs.append({'csv_values':[str(r[0]) for r in c.fetchall()]})
 return obs
for engine in ['matrixone','mysql']:check(engine+'_time_bound_contract',lambda engine=engine:time_bounds(engine))
def timezone(engine):
 with db(engine) as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS timezone_probe');c.execute('CREATE TABLE timezone_probe(id INT PRIMARY KEY,ts TIMESTAMP(6),dt DATETIME(6))');c.execute("SET time_zone='+08:00'")
  v='2026-10-11 08:15:00.123456';c.execute('INSERT INTO timezone_probe VALUES(1,%s,%s)',(v,v));c.execute("SET time_zone='+00:00'");c.execute('SELECT ts,dt FROM timezone_probe');a=c.fetchone();assert a==(datetime.datetime(2026,10,11,0,15,0,123456),datetime.datetime(2026,10,11,8,15,0,123456)),a
  c.execute("SET time_zone='-05:00'");c.execute('SELECT ts,dt FROM timezone_probe');z=c.fetchone();assert z==(datetime.datetime(2026,10,10,19,15,0,123456),a[1]),z
 return {'UTC':a,'UTC_minus_5':z,'datetime_contract':'wall clock unchanged','timestamp_contract':'instant preserved'}
for engine in ['matrixone','mysql']:check(engine+'_session_timezone_timestamp_datetime',lambda engine=engine:timezone(engine))
def arrow_timezone(fmt):
 vals=[datetime.datetime(2026,10,11,8,15,0,123456,tzinfo=datetime.timezone(datetime.timedelta(hours=8))),None]
 t=pa.table({'id':pa.array([1,2],pa.int32()),'v':pa.array(vals,pa.timestamp('us',tz='Asia/Shanghai'))});p=B/('timezone-aware.'+fmt)
 if fmt=='parquet':pq.write_table(t,p)
 else:
  with pa.OSFile(str(p),'wb') as f:
   with pa.ipc.new_file(f,t.schema) as w:w.write_table(t)
 with db() as d,d.cursor() as c:
  c.execute("SET time_zone='+00:00'");c.execute('DROP TABLE IF EXISTS timezone_'+fmt);c.execute('CREATE TABLE timezone_'+fmt+'(id INT PRIMARY KEY,v TIMESTAMP(6))');c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='{fmt}'}} INTO TABLE timezone_{fmt}");c.execute('SELECT v FROM timezone_'+fmt+' ORDER BY id');got=[r[0] for r in c.fetchall()];want=[datetime.datetime(2026,10,11,0,15,0,123456),None];assert got==want,(got,want)
 return {'arrow_schema':str(t.schema),'values_in_UTC':got}
for fmt in ['parquet','arrow']:check(fmt+'_timezone_aware_timestamp_to_native',lambda fmt=fmt:arrow_timezone(fmt))
def rejection(ddl,valid,invalid,fmt):
 table='reject_'+ddl.lower().replace('(','_').replace(')','').replace(',','_')+'_'+fmt
 p=B/(table+'.'+fmt)
 if fmt=='csv':
  with p.open('w',newline='') as f:csv.writer(f).writerows([(1,valid),(2,invalid)])
 else:p.write_text(''.join(json.dumps({'id':i,'v':v})+'\n' for i,v in [(1,valid),(2,invalid)]))
 with db() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS '+table);c.execute(f'CREATE TABLE {table}(id INT PRIMARY KEY,v {ddl})')
  opts=" FIELDS TERMINATED BY ','" if fmt=='csv' else ''
  extra=",'jsondata'='object'" if fmt=='jsonline' else ''
  try:c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='{fmt}'{extra}}} INTO TABLE {table}{opts}");raise AssertionError('invalid input accepted')
  except pymysql.MySQLError as e:error=str(e)
  c.execute('SELECT COUNT(*) FROM '+table);count=c.fetchone()[0];assert count==0,count;c.execute('INSERT INTO '+table+' VALUES(3,%s)',(valid,));c.execute('SELECT count(*) FROM '+table);assert c.fetchone()[0]==1
 return {'error':error,'rows_after_rejected_load':count,'next_valid_write':'passed'}
for ddl,valid,invalid in [('TINYINT','127','128'),('DECIMAL(39,0)','9'*39,'1'+'0'*39),('JSON','{}','{invalid')]:
 for fmt in ['csv','jsonline']:check(ddl+'_'+fmt+'_reject_atomic_recovery',lambda ddl=ddl,valid=valid,invalid=invalid,fmt=fmt:rejection(ddl,valid,invalid,fmt))
def spatial(engine):
 with db(engine) as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS spatial_wkb');c.execute('CREATE TABLE spatial_wkb(id INT PRIMARY KEY,g GEOMETRY)')
  vals=['POINT(1.25 -2.5)','LINESTRING(0 0,1 1,2 -1)','POLYGON((0 0,0 2,2 2,2 0,0 0))']
  c.executemany('INSERT INTO spatial_wkb VALUES(%s,ST_GeomFromText(%s,4326))',list(enumerate(vals,1)));c.execute('INSERT INTO spatial_wkb VALUES(4,NULL)')
  c.execute('SELECT id,ST_AsWKB(g),ST_SRID(g),ST_AsGeoJSON(g) FROM spatial_wkb ORDER BY id');rows=c.fetchall();assert rows[0][2]==4326
  c.execute('DROP TABLE IF EXISTS spatial_wkb_roundtrip');c.execute('CREATE TABLE spatial_wkb_roundtrip(id INT PRIMARY KEY,g GEOMETRY)')
  c.executemany('INSERT INTO spatial_wkb_roundtrip VALUES(%s,ST_GeomFromWKB(%s,4326))',[(r[0],r[1]) for r in rows]);c.execute('SELECT id,ST_AsWKB(g),ST_SRID(g),ST_AsGeoJSON(g) FROM spatial_wkb_roundtrip ORDER BY id');a=c.fetchall();assert rows==a,(rows,a)
 return {'geometry_count':3,'null_count':1,'SRID':4326,'rows':rows,'WKB_roundtrip':'exact'}
for engine in ['matrixone','mysql']:check(engine+'_geometry_WKB_SRID_roundtrip',lambda engine=engine:spatial(engine))
(B/'advanced-probes-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)))
