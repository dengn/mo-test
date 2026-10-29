import subprocess,json,traceback,datetime
from decimal import Decimal,localcontext
from pathlib import Path
import pymysql
B=Path(__file__).parent;out={'tool':'pipelinewise-tap-mysql 1.6.0','cases':[],'target':'Singer messages only; no community target implementation claimed'}
def conn(port):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='tool_types',autocommit=True)
def cli(engine,name,args,adapted=True):
 cmd=[str(B/'singer311/bin/python'),str(B/'tap-utf8-adapter.py')]
 if engine=='matrixone':cmd+=['--matrixone-diagnostic']
 cmd+=args
 with (B/(name+'.jsonl')).open('w') as f,(B/(name+'.log')).open('w') as log:r=subprocess.run(cmd,stdout=f,stderr=log,timeout=90)
 assert r.returncode==0,{'returncode':r.returncode,'log':(B/(name+'.log')).read_text()[-4000:]}
 raw=(B/(name+'.jsonl')).read_text()
 if '--discover' in args:return [json.loads(raw,parse_float=Decimal)]
 return [json.loads(x,parse_float=Decimal) for x in raw.splitlines()]
def case(name,fn):
 r={'name':name}
 try:r['evidence']=fn();r['status']='passed'
 except Exception as e:r.update(status='failed',error=str(e));traceback.print_exc()
 out['cases'].append(r);print(name,r['status'],r.get('error','')[:250],flush=True);(B/'singer-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
def select_catalog(cat,name,method='FULL_TABLE'):
 s=next(s for s in cat['streams'] if s['stream']==name)
 for md in s['metadata']:
  if md['breadcrumb']==[]:
   md['metadata'].update(selected=True,**{'replication-method':method})
   if method=='INCREMENTAL':md['metadata']['replication-key']='updated_seq'
  elif len(md['breadcrumb'])==2:md['metadata']['selected']=True
 return {'streams':[s]}
for engine,port in [('matrixone',6001),('mysql',13306)]:
 config=B/('tap-mo-adapted.json' if engine=='matrixone' else 'tap-mysql.json')
 def wide(engine=engine,config=config):
  catalog=B/('tap-mo-diagnostic-selected.json' if engine=='matrixone' else 'tap-mysql-selected.json');msgs=cli(engine,'singer-'+engine+'-wide',['-c',str(config),'--catalog',str(catalog)])
  rs=sorted([x['record'] for x in msgs if x['type']=='RECORD'],key=lambda x:x['id']);assert len(rs)==3;assert rs[0]['large_signed']==9007199254740993 and rs[0]['large_unsigned']==18446744073709551615;assert rs[0]['precise']==Decimal('12345678901234567890.123456789012345678');assert bytes.fromhex(rs[0]['payload'])==b'\x00\xff\x80abc';assert rs[0]['name']=='中文 😀';assert rs[0]['ts']=='2026-10-10T12:00:00.123456+00:00';assert all(v is None for k,v in rs[2].items() if k!='id')
  schema=next(x['schema'] for x in msgs if x['type']=='SCHEMA');doc_type=schema['properties']['doc']['type']
  return {'rows':rs,'large_numeric_lexemes_exact':True,'binary_hex_exact':True,'utf8mb4_adapter':True,'doc_declared_type':doc_type,'doc_actual_python_type':type(rs[0]['doc']).__name__,'JSON_schema_matches_records':False,'JSON_semantic_decode':json.loads(rs[0]['doc'])}
 case(engine+'_adapted_full_snapshot_exact_fields_and_JSON_schema_observation',wide)
 with conn(port) as d,d.cursor() as c:
  c.execute('DROP TABLE IF EXISTS tap_incr');c.execute('CREATE TABLE tap_incr(id BIGINT PRIMARY KEY,updated_seq BIGINT,v VARCHAR(100))');c.execute("INSERT INTO tap_incr VALUES(1,10,'中文 😀'),(2,20,''),(3,30,NULL)")
 catmsgs=cli(engine,'singer-'+engine+'-discover',['-c',str(config),'--discover']);cat=catmsgs[0];sel=select_catalog(cat,'tap_incr','INCREMENTAL');selected=B/('singer-'+engine+'-incremental-selected.json');selected.write_text(json.dumps(sel));state_path=B/('singer-'+engine+'-state.json')
 def first(engine=engine,config=config,selected=selected,state_path=state_path):
  msgs=cli(engine,'singer-'+engine+'-incremental-1',['-c',str(config),'--catalog',str(selected)]);rs=sorted([x['record'] for x in msgs if x['type']=='RECORD'],key=lambda x:x['id']);assert rs==[{'id':1,'updated_seq':10,'v':'中文 😀'},{'id':2,'updated_seq':20,'v':''},{'id':3,'updated_seq':30,'v':None}],rs
  states=[x['value'] for x in msgs if x['type']=='STATE'];assert states;state_path.write_text(json.dumps(states[-1]));return {'records':rs,'state':states[-1]}
 case(engine+'_incremental_initial_snapshot',first)
 with conn(port) as d,d.cursor() as c:c.execute("UPDATE tap_incr SET updated_seq=40,v='更新 😀' WHERE id=1");c.execute('INSERT INTO tap_incr VALUES(4,50,NULL)')
 def resumed(engine=engine,config=config,selected=selected,state_path=state_path):
  msgs=cli(engine,'singer-'+engine+'-incremental-2',['-c',str(config),'--catalog',str(selected),'--state',str(state_path)]);rs=sorted([x['record'] for x in msgs if x['type']=='RECORD'],key=lambda x:x['id']);byid={r['id']:r for r in rs};assert byid[1]=={'id':1,'updated_seq':40,'v':'更新 😀'} and byid[4]=={'id':4,'updated_seq':50,'v':None};assert 2 not in byid
  states=[x['value'] for x in msgs if x['type']=='STATE'];return {'records':rs,'state':states[-1],'inclusive_bookmark_row_replay_allowed':3 in byid,'semantics':'SELECT-based incremental cursor; no binlog CDC claim'}
 case(engine+'_incremental_resume_updated_row_and_new_NULL',resumed)
