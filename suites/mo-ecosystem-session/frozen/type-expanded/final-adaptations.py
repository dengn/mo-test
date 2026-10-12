import json,csv,traceback
from pathlib import Path
from decimal import Decimal
import pymysql,pyarrow as pa
B=Path(__file__).parent;out={'cases':[]}
def conn():return pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='type_matrix',autocommit=True)
def ipc(name,values):
 t=pa.table({'id':pa.array(range(1,len(values)+1),pa.int32()),'v':pa.array(values,pa.string())});p=B/(name+'.arrow')
 with pa.OSFile(str(p),'wb') as f:
  with pa.ipc.new_file(f,t.schema) as w:w.write_table(t)
 return p
def check(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:240],flush=True)
def decimal65():
 vals=['9'*35+'.'+'9'*30,'-'+'9'*35+'.'+'9'*30,None];p=ipc('arrow-decimal256-text-adapter',vals)
 with conn() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS arrow_decimal65_stage');c.execute('CREATE TABLE arrow_decimal65_stage(id INT PRIMARY KEY,v VARCHAR(100))');c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='arrow'}} INTO TABLE arrow_decimal65_stage");c.execute('DROP TABLE IF EXISTS arrow_decimal65_target');c.execute('CREATE TABLE arrow_decimal65_target(id INT PRIMARY KEY,v DECIMAL(65,30))');c.execute('INSERT INTO arrow_decimal65_target SELECT id,CAST(v AS DECIMAL(65,30)) FROM arrow_decimal65_stage');c.execute('SELECT v FROM arrow_decimal65_target ORDER BY id');a=[r[0] for r in c.fetchall()];assert a==[Decimal(v) if v is not None else None for v in vals],a
 return a
check('Arrow_Decimal256_via_text_stage_exact',decimal65)
def nested():
 vals=[{'中文':9007199254740993,'empty':0},None];p=ipc('arrow-nested-map-text-adapter',[json.dumps(v,ensure_ascii=False) if v is not None else None for v in vals])
 with conn() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS arrow_nested_map_stage');c.execute('CREATE TABLE arrow_nested_map_stage(id INT PRIMARY KEY,v VARCHAR(500))');c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='arrow'}} INTO TABLE arrow_nested_map_stage");c.execute('DROP TABLE IF EXISTS arrow_nested_map_target');c.execute('CREATE TABLE arrow_nested_map_target(id INT PRIMARY KEY,v JSON)');c.execute('INSERT INTO arrow_nested_map_target SELECT id,CAST(v AS JSON) FROM arrow_nested_map_stage');c.execute('SELECT v FROM arrow_nested_map_target ORDER BY id');a=[json.loads(r[0]) if r[0] is not None else None for r in c.fetchall()];assert a==vals,a
 return a
check('Arrow_nested_map_via_JSON_text_stage_exact',nested)
def enums(fmt,kind):
 vals=['red','中文','',None] if kind=='enum' else ['','a','a,中文',None];ddl="ENUM('red','中文','')" if kind=='enum' else "SET('a','中文')";name=kind+'_'+fmt+'_safe';stage=name+'_stage';p=B/(name+'.'+fmt)
 if fmt=='csv':
  with p.open('w',newline='') as f:csv.writer(f,quoting=csv.QUOTE_ALL).writerows((i+1,v if v is not None else '\\N') for i,v in enumerate(vals))
 else:p.write_text(''.join(json.dumps({'id':i+1,'v':v},ensure_ascii=False)+'\n' for i,v in enumerate(vals)))
 with conn() as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS '+stage);c.execute('CREATE TABLE '+stage+'(id INT PRIMARY KEY,v VARCHAR(100))');opts=" FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '\"' ESCAPED BY ''" if fmt=='csv' else '';js=",'jsondata'='object'" if fmt=='jsonline' else '';c.execute(f"LOAD DATA INFILE {{'filepath'='{p}','format'='{fmt}'{js}}} INTO TABLE {stage}{opts}");c.execute('DROP TABLE IF EXISTS '+name);c.execute('CREATE TABLE '+name+'(id INT PRIMARY KEY,v '+ddl+')');c.execute('INSERT INTO '+name+' SELECT id,v FROM '+stage);c.execute('SELECT v,v IS NULL FROM '+name+' ORDER BY id');a=c.fetchall();assert [r[0] for r in a]==vals,a
 return {'values':a,'NULL_and_empty_distinct':True}
for fmt in ['csv','jsonline']:
 for kind in ['enum','set']:check(kind+'_'+fmt+'_VARCHAR_stage_preserves_empty_vs_NULL',lambda fmt=fmt,kind=kind:enums(fmt,kind))
(B/'final-adaptations-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
