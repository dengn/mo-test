from common import *
from decimal import Decimal
import base64,datetime
A=B/'airbyte';A.mkdir(exist_ok=True);resume=os.environ.get('RT2_AIRBYTE_RESUME')=='1';out=json.loads((B/'airbyte-expanded-result.json').read_text()) if resume else {'runtime_ref':REF,'scope':'official source-mysql:3.53.7 connector process and source-only CDC states; no destination acknowledgement','phases':[]}
def save():dump(B/'airbyte-expanded-result.json',out)
if not resume:
 sql(13306,None,'CREATE DATABASE IF NOT EXISTS rt2_airbyte')
 sql(13306,'rt2_airbyte',"CREATE TABLE boundary(id INT PRIMARY KEY,u BIGINT UNSIGNED,s BIGINT,d DECIMAL(38,18),tiny DECIMAL(38,30),payload VARBINARY(40),txt VARCHAR(300),ts DATETIME(6),doc JSON,e ENUM('','红','blue'),tags SET('a','b'),tm TIME(6),dt DATE,u_text VARCHAR(20),d_text VARCHAR(80))")
unsigned=[0,2**53-1,2**53,2**63-1,2**63,2**63+1,2**64-2,2**64-1,None]
for i,u in ([] if resume else enumerate(unsigned,1)):
 s=-2**63 if i==1 else 2**63-1 if i==2 else 9007199254740993
 dec='12345678901234567890.123456789012345678' if i%2 else '-0.000000000000000001'
 sql(13306,'rt2_airbyte','INSERT INTO boundary VALUES('+','.join(['%s']*15)+')',(i,u,s,dec,'0.'+'0'*29+'1',[b'',b'\x00\xff\x80',None][i%3],'引号\" 单引号\' 换行\n 制表\t 😀', '2026-10-11 12:34:56.123456',json.dumps({'n':9007199254740993,'arr':[None,True,'中文'],'x':'1e-30'},ensure_ascii=False),'','a,b','12:34:56.123456','2000-02-29',None if u is None else str(u),dec))
cfg=json.loads((OLD/'airbyte/source-cdc.json').read_text());cfg['database']='rt2_airbyte';cfg['table_filters']=[{'database_name':'rt2_airbyte','table_name_patterns':['boundary']}];dump(A/'source.json',cfg)
def run(name,cmd):
 args=['docker','run','--rm','--memory=1024m','--name','rt2-airbyte-'+name,'--mount',f'type=bind,src={A},dst=/config,readonly','airbyte/source-mysql:3.53.7']+cmd
 print('AIRBYTE',name,'START',flush=True)
 with (A/(name+'.jsonl')).open('w') as f:r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=240)
 msgs=[]
 for line in (A/(name+'.jsonl')).read_text().splitlines():
  try:msgs.append(json.loads(line,parse_float=Decimal))
  except (ValueError,TypeError):pass
 traces=[m for m in msgs if m.get('type')=='TRACE' and m.get('trace',{}).get('type')=='ERROR']
 result={'name':name,'returncode':r.returncode,'record_count':sum(m.get('type')=='RECORD' for m in msgs),'state_count':sum(m.get('type')=='STATE' for m in msgs),'errors':traces}
 out['phases'].append(result);save();print('AIRBYTE',name,result['returncode'],result['record_count'],result['state_count'],'errors',len(traces),flush=True);return msgs,result
def catalog(discovered):
 stream=next(m['catalog']['streams'][0] for m in discovered if m.get('type')=='CATALOG')
 return {'streams':[{'stream':stream,'sync_mode':'incremental','destination_sync_mode':'append_dedup','cursor_field':stream.get('default_cursor_field',[]),'primary_key':stream.get('source_defined_primary_key',[])}]}
def state(msgs,name):
 # State must preserve protocol JSON types. Decimal-aware RECORD comparison must not stringify state statistics.
 raw=[json.loads(line) for line in (A/(out['phases'][-1]['name']+'.jsonl')).read_text().splitlines() if line.lstrip().startswith('{')]
 states=[m['state'] for m in raw if m.get('type')=='STATE'];assert states,'No source state';dump(A/name,[states[-1]])
def compare(msgs,result):
 records=[m['record']['data'] for m in msgs if m.get('type')=='RECORD'];result['records']=records
 expected={r[0]:r[1:] for r in sql(13306,'rt2_airbyte','SELECT id,u,s,CAST(d AS CHAR),CAST(tiny AS CHAR),HEX(payload),txt,CAST(ts AS CHAR),doc,e,tags,CAST(tm AS CHAR),CAST(dt AS CHAR),u_text,d_text FROM boundary ORDER BY id')}
 diffs=[];checked=0
 for rec in records:
  if rec.get('_ab_cdc_deleted_at') is not None:continue
  fields=['u','s','d','tiny','payload','txt','ts','doc','e','tags','tm','dt','u_text','d_text'];exp=dict(zip(fields,expected[int(rec['id'])]))
  for field in fields:
   a=rec.get(field);e=exp[field]
   if field in ('d','tiny'):a=Decimal(str(a)) if a is not None else None;e=Decimal(str(e)) if e is not None else None
   elif field=='payload':a=base64.b64decode(a).hex().upper() if a is not None else None
   elif field=='ts':a=a.replace('T',' ') if a is not None else None
   elif field=='doc':a=json.loads(a) if a is not None else None;e=json.loads(e) if e is not None else None
   checked+=1
   if a!=e:diffs.append({'id':int(rec['id']),'field':field,'source':str(e),'protocol':str(a)})
 result['assertions']=checked;result['differences']=diffs;save()
if not resume:
 msgs,_=run('discover',['discover','--config','/config/source.json']);dump(A/'catalog.json',catalog(msgs))
 msgs,r=run('snapshot',['read','--config','/config/source.json','--catalog','/config/catalog.json']);compare(msgs,r);state(msgs,'state1.json')
 sql(13306,'rt2_airbyte',"UPDATE boundary SET txt=CONCAT(txt,' CDC'),ts='2026-10-11 12:34:56.000001'")
else:
 for phase in out['phases']:
  if phase['name']=='incremental':phase['excluded_from_valid_results']='harness serialized Decimal sourceStats.recordCount as string; not connector or database defect'
  if phase['name']=='incremental-valid':phase['excluded_from_valid_results']='harness omitted indented STATE lines and supplied empty state, causing a new snapshot; not valid CDC coverage'
 raw=[json.loads(line) for line in (A/'snapshot.jsonl').read_text().splitlines() if line.lstrip().startswith('{')]
 dump(A/'state1.json',[m['state'] for m in raw if m.get('type')=='STATE'][-1:]);save()
msgs,r=run('incremental-from-original-state',['read','--config','/config/source.json','--catalog','/config/catalog.json','--state','/config/state1.json']);compare(msgs,r);state(msgs,'state2.json')
sql(13306,'rt2_airbyte','ALTER TABLE boundary RENAME COLUMN txt TO renamed_txt')
sql(13306,'rt2_airbyte','ALTER TABLE boundary DROP COLUMN tags')
sql(13306,'rt2_airbyte','ALTER TABLE boundary MODIFY COLUMN u_text VARCHAR(100)')
sql(13306,'rt2_airbyte',"UPDATE boundary SET renamed_txt='重命名后 😀',u_text=CONCAT(IFNULL(u_text,'NULL'),'-widened') WHERE id=8")
sql(13306,'rt2_airbyte','DELETE FROM boundary WHERE id=2')
msgs,_=run('rediscover',['discover','--config','/config/source.json']);dump(A/'evolved-catalog.json',catalog(msgs))
msgs,r=run('schema-resume',['read','--config','/config/source.json','--catalog','/config/evolved-catalog.json','--state','/config/state2.json'])
r['records']=[m['record']['data'] for m in msgs if m.get('type')=='RECORD'];r['rename_drop_widen_delete_checks']={'renamed_update_present':any(x.get('id')==8 and x.get('renamed_txt')=='重命名后 😀' for x in r['records']),'dropped_field_absent':all('tags' not in x for x in r['records']),'delete_present':any(x.get('id')==2 and x.get('_ab_cdc_deleted_at') for x in r['records']),'widened_text_present':any(x.get('id')==8 and x.get('u_text')==str(2**64-1)+'-widened' for x in r['records'])};save()
print('AIRBYTE DONE',flush=True)
