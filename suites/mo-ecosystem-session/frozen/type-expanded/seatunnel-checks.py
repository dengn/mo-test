import json,subprocess,traceback,hashlib
from decimal import Decimal
from pathlib import Path
import pymysql
B=Path(__file__).parent;out={'tool':'Apache SeaTunnel 2.3.12','cases':[],'delivery_semantics':'JDBC primary-key upsert, is_exactly_once=false'}
def conn(port=6001):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='tool_types',autocommit=True)
def rows(table,port=6001,cols='id,large_signed,large_unsigned,precise,payload,name,ts'):
 with conn(port) as d,d.cursor() as c:c.execute('SELECT '+cols+' FROM '+table+' ORDER BY id');return c.fetchall()
def job(name,source_table,sink_table,source_port=6001,cols='id,large_signed,large_unsigned,precise,payload,name,ts'):
 s=(B/'seatunnel.conf').read_text();s=s.replace('FROM typed_rows','FROM '+source_table).replace('table = "seatunnel_rows"','table = "'+sink_table+'"');s=s.replace('SELECT id,large_signed,large_unsigned,precise,payload,name,ts','SELECT '+cols)
 if source_port!=6001:
  # Change source block only. The sink is always the tested MatrixOne process.
  a,z=s.split('sink {',1);a=a.replace(':6001/',':13306/').replace('password = "111"','password = "types-local"');s=a+'sink {'+z
 p=B/(name+'.conf');p.write_text(s)
 with (B/(name+'.log')).open('w') as f:r=subprocess.run([str(B/'apache-seatunnel-2.3.12/bin/seatunnel.sh'),'--config',str(p),'--deploy-mode','local'],stdout=f,stderr=subprocess.STDOUT,timeout=180)
 log=(B/(name+'.log')).read_text();return {'returncode':r.returncode,'job_finished':'FINISHED' in log,'error_tail':log[-3500:] if r.returncode or 'FINISHED' not in log else None}
def case(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:300],flush=True);(B/'seatunnel-result.json').write_text(json.dumps(out,indent=2,default=lambda v:v.hex() if isinstance(v,bytes) else str(v)))
def initial():
 a=rows('typed_rows');z=rows('seatunnel_rows');assert a==z,(a,z);assert a[0][2]==18446744073709551615 and a[0][3]==Decimal('12345678901234567890.123456789012345678');assert a[0][6].microsecond==123456
 return {'source_rows':a,'sink_rows':z,'original_job_log':'seatunnel-run.log','all_fields_exact':True}
case('original_MatrixOne_to_MatrixOne_wide_types',initial)
with conn() as d,d.cursor() as c:
 for t in ['st_evo_source','st_evo_sink','st_mysql_sink']:c.execute('DROP TABLE IF EXISTS '+t)
 c.execute('CREATE TABLE st_evo_source LIKE typed_rows');c.execute('INSERT INTO st_evo_source SELECT * FROM typed_rows');c.execute('CREATE TABLE st_evo_sink LIKE typed_rows')
 c.execute("UPDATE st_evo_source SET large_signed=9007199254740995,name='更新 😀',ts='2026-10-11 12:34:56.987654' WHERE id=1")
 c.execute('INSERT INTO st_evo_source(id) VALUES(4)')
def roundtrip():
 r=job('seatunnel-repeat','st_evo_source','st_evo_sink');assert r['returncode']==0 and r['job_finished'],r;a=rows('st_evo_source');z=rows('st_evo_sink');assert a==z,(a,z)
 return {'job':r,'rows':z,'all_fields_exact':True}
case('updated_values_and_new_NULL_row',roundtrip)
case('primary_key_upsert_replay_no_duplicate',roundtrip)
with conn() as d,d.cursor() as c:c.execute('ALTER TABLE st_evo_source ADD COLUMN added_tag VARCHAR(100)');c.execute("UPDATE st_evo_source SET added_tag='模式变化 中文' WHERE id=1")
cols='id,large_signed,large_unsigned,precise,payload,name,ts,added_tag'
def schema_reject():
 before=rows('st_evo_sink');r=job('seatunnel-schema-unadapted','st_evo_source','st_evo_sink',cols=cols);after=rows('st_evo_sink');assert r['returncode']!=0 or not r['job_finished'],r;assert after==before
 return {'job':r,'expected_rejection':True,'sink_unchanged':True}
case('new_source_column_requires_sink_schema_adaptation',schema_reject)
with conn() as d,d.cursor() as c:c.execute('ALTER TABLE st_evo_sink ADD COLUMN added_tag VARCHAR(100)')
def schema_adapted():
 r=job('seatunnel-schema-adapted','st_evo_source','st_evo_sink',cols=cols);assert r['returncode']==0 and r['job_finished'],r;a=rows('st_evo_source',cols=cols);z=rows('st_evo_sink',cols=cols);assert a==z,(a,z);return {'job':r,'rows':z,'all_fields_exact':True}
case('adapted_schema_and_unicode_added_column',schema_adapted)
with conn() as d,d.cursor() as c:c.execute('CREATE TABLE st_mysql_sink LIKE typed_rows')
def mysql_cross():
 cols='id,large_signed,large_unsigned,precise,payload,name,ts,doc';r=job('seatunnel-mysql-cross','typed_rows','st_mysql_sink',source_port=13306,cols=cols);assert r['returncode']==0 and r['job_finished'],r
 a=rows('typed_rows',port=13306,cols=cols);z=rows('st_mysql_sink',cols=cols)
 def canonical(rs):return [tuple(row[:-1])+(json.loads(row[-1]) if row[-1] is not None else None,) for row in rs]
 assert canonical(a)==canonical(z),(a,z);return {'job':r,'rows':z,'all_fields_exact':True,'JSON_compared_semantically':True}
case('real_MySQL_to_MatrixOne_JSON_and_wide_scalar_types',mysql_cross)
