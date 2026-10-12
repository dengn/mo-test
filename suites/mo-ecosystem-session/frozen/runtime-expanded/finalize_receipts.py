import requests,pymysql,json,time,datetime,hashlib
from decimal import Decimal
from pathlib import Path
B=Path(__file__).parent;A=B/'airbyte';ids=json.loads((B/'nifi-ids.json').read_text());API='http://127.0.0.1:10088/nifi-api'
def read(name):return json.loads((B/name).read_text())
def db(port):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='runtime_ecosystem',autocommit=True)
wm=read('nifi-replay-watermark.json');start=time.monotonic();receipt={}
while time.monotonic()-start<30:
 q=requests.get(API+'/processors/'+ids['processors']['QueryDatabaseTableRecord']+'/state').json()
 vals=q['componentState']['localState'].get('state',[]);seq=max((int(x['value']) for x in vals if x['key'].endswith('@!@seq')),default=0)
 queues={k:requests.get(API+'/connections/'+v).json().get('status',{}).get('aggregateSnapshot',{}).get('flowFilesQueued',0) for k,v in ids['connections'].items()}
 sink=requests.get(API+'/processors/'+ids['processors']['PutSQL']).json()
 if seq>=wm['after'] and all(v==0 for v in queues.values()) and not sink.get('bulletins'):break
 time.sleep(1)
result=[]
for port,table in [(13306,'nifi_source'),(6001,'nifi_outbox_target')]:
 with db(port) as d,d.cursor() as c:
  c.execute('SELECT id,s,u,CAST(d AS CHAR),HEX(payload),name,CAST(ts AS CHAR),doc,updated,added_tag FROM '+table+' ORDER BY id')
  result.append([list(r[:7])+[json.loads(r[7]) if r[7] is not None else None]+list(r[8:]) for r in c.fetchall()])
nifi=read('nifi-runtime-result.json');nifi['cases'].append({'name':'replay-delivered-watermark-and-empty-queues-with-full-final-values','status':'passed' if seq>=wm['after'] and all(v==0 for v in queues.values()) and result[0]==result[1] and not sink.get('bulletins') else 'failed','outbox_watermark':wm,'nifi_checkpoint':seq,'queued_flowfiles':queues,'source':result[0],'sink':result[1]});(B/'nifi-runtime-result.json').write_text(json.dumps(nifi,ensure_ascii=False,indent=2,default=str));print('NiFi delivery receipt',nifi['cases'][-1]['status'],seq,queues,flush=True)
air={'versions':{'source_mysql':'3.53.7','destination_mysql':'1.1.1'},'runtime_scope':'official Docker source/destination and local Airbyte protocol runner; no Airbyte Kubernetes control plane or scheduler deployed','cases':[]}
for f in ['standard-read-1.jsonl','cdc-read-valid1.jsonl','cdc-read-valid2.jsonl','cdc-read-evolved3.jsonl']:
 records=[];states=[];errors=[];complete=False
 for l in (A/f).read_text().splitlines():
  try:
   x=json.loads(l,parse_float=Decimal)
   if x.get('type')=='RECORD':records.append(x['record']['data'])
   if x.get('type')=='STATE':states.append(x['state'])
   if x.get('type')=='TRACE':
    if x['trace']['type']=='ERROR':errors.append(x['trace'])
    if x['trace']['type']=='STREAM_STATUS' and x['trace']['stream_status']['status']=='COMPLETE':complete=True
  except ValueError:pass
 air['cases'].append({'name':f,'record_count':len(records),'state_count':len(states),'error_count':len(errors),'stream_complete':complete,'records':records,'errors':errors})
for engine in ['mo','mysql']:
 states=[];errors=[]
 for l in (A/f'isolated-standard-write-{engine}-1.jsonl').read_text().splitlines():
  try:
   x=json.loads(l)
   if x.get('type')=='STATE':states.append(x['state'])
   if x.get('type')=='TRACE' and x['trace']['type']=='ERROR':errors.append(x['trace'].get('error',{}).get('internal_message'))
  except ValueError:pass
 air['cases'].append({'name':'official-destination-write-'+engine,'state_ack_count':len(states),'errors':errors,'status':'blocked' if errors else 'completed_needs_value_validation','typed_control_note':'MySQL completed but default unsigned->signed and NUMBER->decimal38,9 mapping loses values; exact source Decimal JSON protocol preserved, local receipt parsing uses Decimal.'})
air['unsigned_CDC_loss']={'expected':18446744073709551615,'snapshot_value':air['cases'][1]['records'][0]['u'],'incremental_value':next(x['u'] for x in air['cases'][2]['records'] if x['id']==1),'owner':'upstream Airbyte source binlog mapping before MatrixOne destination'}
air['checkpoint_policy']='Saved source-only states for isolated source verification. No production checkpoint advance claimed for failed MO destination (no destination STATE acknowledgement).'
air['invalidated_trials']=['Initial MySQL destination namespace overlapped source runtime_ecosystem.records; excluded; corrected target namespaces airbyte_mo/airbyte_mysql and recreated source.', 'First CDC read used STANDARD-discovered catalog and got missing cursor configuration error; excluded; CDC-discovered catalog used for valid1/valid2/evolved3.', 'First NiFi JSONPath expected array but SplitRecord produced object; adapter corrected to $.sqltext; completed profile retested.']
(B/'airbyte-runtime-result.json').write_text(json.dumps(air,ensure_ascii=False,indent=2,default=str));print('Airbyte receipts',[(x['name'],x.get('record_count'),x.get('stream_complete'),x.get('status')) for x in air['cases']],flush=True)
inventory=[]
for name in ['kafka-runtime-result.json','nifi-runtime-result.json','airbyte-runtime-result.json','runtime-minimal-sql-result.json','pk-upsert-retest-result.json']:
 p=B/name;inventory.append({'file':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
out={'created_UTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtime_ref':'652c643666428f1c434e03369834f2a9bead7c27','scope':'Full local NiFi and Kafka/Connect processes; official Airbyte connectors with protocol runner, not Airbyte full platform','inventory':inventory,'limitations':['Airbyte native MatrixOne destination blocked at LOAD SET user-variable NULLIF','Airbyte CDC UInt64 incremental -1 is upstream loss; no full preservation pass','NiFi default UPSERT blocked; successful profile is explicit transactional trigger SQL outbox','NiFi added column needs target + profile adaptation','Kafka auto-evolution parenthesized ADD blocked; recovery used explicit DDL adaptation','Graceful stop/restart only; no hard crash, broker data loss, network partition, throughput, long soak or exactly-once certification','Rename/drop-column/type changes not certified'],'source_tree_modified':False}
(B/'runtime-expanded-summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
