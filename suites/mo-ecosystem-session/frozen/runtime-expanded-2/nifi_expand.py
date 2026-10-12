from common import *
I=json.loads((OLD/'nifi-ids.json').read_text());P=I['processors'];N='runtime_ecosystem';BASE='http://127.0.0.1:10088/nifi-api'
out={'runtime_ref':REF,'profile':'NiFi 2.4.0, explicit MySQL trigger SQL outbox, seq checkpoint; not default PutDatabaseRecord or automatic schema evolution','cases':[],'faults':[]}
def save():dump(B/'nifi-expanded-result.json',out)
def ni(m,path,data=None):return api(m,path,data,BASE)
def run(name,state):
 e=ni('GET','/processors/'+P[name]);ni('PUT','/processors/'+P[name]+'/run-status',{'revision':e['revision'],'state':state})
 poll(lambda:ni('GET','/processors/'+P[name])['component']['state']==state,20)
def queue():
 return {name:ni('GET','/connections/'+id)['status']['aggregateSnapshot']['flowFilesQueued'] for name,id in I['connections'].items() if name!='native'}
def checkpoint():return ni('GET','/processors/'+P['QueryDatabaseTableRecord']+'/state')['componentState']
def rows(port,tag='added_tag',name='name'):
 table='nifi_source' if port==13306 else 'nifi_outbox_target'
 r=sql(port,N,'SELECT id,s,u,CAST(d AS CHAR),HEX(payload),'+name+',CAST(ts AS CHAR),doc,updated'+(','+tag if tag else '')+' FROM '+table+' ORDER BY id')
 return [tuple(x[:7])+(json.loads(x[7]) if x[7] is not None else None,)+tuple(x[8:]) for x in r]
def wait(label,tag='added_tag',name='name',timeout=70):
 end=time.monotonic()+timeout;expected=rows(13306,tag,name);actual=None
 while time.monotonic()<end:
  actual=rows(6001,tag,name)
  if actual==expected and sum(queue().values())==0:break
  time.sleep(1)
 case={'name':label,'status':'passed' if actual==expected else 'failed','source':expected,'sink':actual,'queue':queue(),'checkpoint':checkpoint(),'source_max_seq':sql(13306,N,'SELECT MAX(seq) FROM nifi_outbox')[0][0]};out['cases'].append(case);save();print(label,case['status'],flush=True);return case['status']=='passed'
wait('baseline')
run('PutSQL','STOPPED')
# Persist failures into a stopped processor instead of discarding them.
e=ni('POST','/process-groups/'+I['group']+'/processors',{'revision':{'version':0},'component':{'name':'rt2 retained rejects','type':'org.apache.nifi.processors.standard.LogAttribute','position':{'x':1000,'y':600},'config':{'autoTerminatedRelationships':['success']}}});reject_id=e['id']
e=ni('GET','/processors/'+P['PutSQL']);ni('PUT','/processors/'+P['PutSQL'],{'revision':e['revision'],'component':{'id':P['PutSQL'],'config':{'autoTerminatedRelationships':['success']}}})
e=ni('POST','/process-groups/'+I['group']+'/connections',{'revision':{'version':0},'component':{'source':{'id':P['PutSQL'],'groupId':I['group'],'type':'PROCESSOR'},'destination':{'id':reject_id,'groupId':I['group'],'type':'PROCESSOR'},'selectedRelationships':['failure','retry']}});I['connections']['retained-rejects']=e['id'];dump(B/'nifi-ids.json',I)
for i in range(200,230):
 sql(13306,N,'INSERT INTO nifi_source(id,s,u,d,payload,name,ts,doc,updated,added_tag) VALUES('+','.join(['%s']*10)+')',(i,-2**63,2**64-1,'0.123456789012345678',b'\x00\xff\x80','持久队列😀','2026-10-11 18:30:00.000001','{"n":9007199254740993}',i,'queue'))
sql(13306,N,"UPDATE nifi_source SET name='强制中断前😀',updated=400 WHERE id=1");sql(13306,N,'DELETE FROM nifi_source WHERE id=8')
maxseq=sql(13306,N,'SELECT MAX(seq) FROM nifi_outbox')[0][0]
def staged():
 state=checkpoint();items=state['localState']['state'];watermark=next((int(x['value']) for x in items if x['key']=='nifi_outbox@!@seq'),0)
 return watermark>=maxseq and queue()['ReplaceText-PutSQL']>=32
poll(staged,60);out['staged_before_crash']={'queue':queue(),'checkpoint':checkpoint(),'source_max_seq':maxseq};save()
out['faults'].append(kill_owned('nifi','org.apache.nifi.NiFi'));save();time.sleep(1)
# Generate more events with NiFi completely absent.
sql(13306,N,"UPDATE nifi_source SET name='强制中断后😀',updated=401 WHERE id=1");sql(13306,N,'DELETE FROM nifi_source WHERE id=201');sql(13306,N,"INSERT INTO nifi_source(id,name,updated) VALUES(230,'停机事件😀',402)")
start('nifi');poll(lambda:ni('GET','/flow/process-groups/root'),120)
out['persisted_after_restart']={'queue':queue(),'checkpoint':checkpoint(),'putsql_state':ni('GET','/processors/'+P['PutSQL'])['component']['state']};save()
run('PutSQL','RUNNING');wait('SIGKILL-persistent-pending-queue-plus-offline-events')
# A trigger that emits only the NEW key cannot remove the old primary key.
sql(13306,N,'UPDATE nifi_source SET id=1230,updated=403 WHERE id=230');time.sleep(5)
out['cases'].append({'name':'unadapted-trigger-primary-key-change','status':'profile_gap','source_ids':sql(13306,N,'SELECT id FROM nifi_source WHERE id IN (230,1230)'),'sink_ids':sql(6001,N,'SELECT id FROM nifi_outbox_target WHERE id IN (230,1230)'),'note':'adapter UPDATE trigger emits NEW-key upsert only, not a MatrixOne defect'});save()
cols=['id','s','u','d','payload','name','ts','doc','updated','added_tag']
def expr(prefix):
 args=[]
 for col in cols:
  x=prefix+'.'+col
  part=f"IF({x} IS NULL,'NULL',CONCAT(\"X'\",HEX({x}),\"'\"))" if col=='payload' else f"IF({x} IS NULL,'NULL',QUOTE(CAST({x} AS CHAR)))"
  if args:args.append("','")
  args.append(part)
 return 'CONCAT('+','.join(["'INSERT INTO nifi_outbox_target("+','.join(cols)+") VALUES('"]+args+["') ON DUPLICATE KEY UPDATE "+','.join(x+'=VALUES('+x+')' for x in cols if x!='id')+"'"])+')'
def triggers():
 for op in ['INSERT','UPDATE']:
  sql(13306,N,'DROP TRIGGER nifi_'+op.lower())
  body='INSERT INTO nifi_outbox(sqltext) VALUES('+expr('NEW')+');'
  if op=='UPDATE':body="IF OLD.id<>NEW.id THEN INSERT INTO nifi_outbox(sqltext) VALUES(CONCAT('DELETE FROM nifi_outbox_target WHERE id=',CAST(OLD.id AS CHAR))); END IF; "+body
  sql(13306,N,f'CREATE TRIGGER nifi_{op.lower()} AFTER {op} ON nifi_source FOR EACH ROW BEGIN '+body+' END')
triggers();sql(13306,N,"INSERT INTO nifi_outbox(sqltext) VALUES('DELETE FROM nifi_outbox_target WHERE id=230')");sql(13306,N,'UPDATE nifi_source SET id=2230,updated=404 WHERE id=1230');wait('adapted-primary-key-change-delete-old-key')
# Versioned, coordinated rename/drop/widen: stop source polling for profile migration.
run('QueryDatabaseTableRecord','STOPPED')
for port,table in [(13306,'nifi_source'),(6001,'nifi_outbox_target')]:
 sql(port,N,'ALTER TABLE '+table+' RENAME COLUMN added_tag TO tag_v2')
 sql(port,N,'ALTER TABLE '+table+' MODIFY COLUMN name VARCHAR(300)')
cols[-1]='tag_v2';triggers();run('QueryDatabaseTableRecord','RUNNING')
sql(13306,N,'UPDATE nifi_source SET name=%s,tag_v2=%s,updated=405 WHERE id=1',('长文本😀'*40,'重命名字段'))
wait('explicit-adapter-column-rename-and-string-widen','tag_v2')
run('QueryDatabaseTableRecord','STOPPED')
for port,table in [(13306,'nifi_source'),(6001,'nifi_outbox_target')]:sql(port,N,'ALTER TABLE '+table+' DROP COLUMN tag_v2')
cols.pop();triggers();run('QueryDatabaseTableRecord','RUNNING');sql(13306,N,"UPDATE nifi_source SET name='删列后😀',updated=406 WHERE id=1");wait('explicit-adapter-column-drop',None)
out['retained_rejects']=queue()['retained-rejects'];out['dedup']=sql(6001,N,'SELECT COUNT(*),COUNT(DISTINCT id) FROM nifi_outbox_target');save();print('NIFI DONE',flush=True)
