import requests,json
from pathlib import Path
B=Path(__file__).parent;API='http://127.0.0.1:10088/nifi-api';ids=json.loads((B/'nifi-ids.json').read_text());g=ids['group']
def api(m,p,d=None):
 r=requests.request(m,API+p,json=d,timeout=20);r.raise_for_status();return r.json()
q=ids['processors']['QueryDatabaseTableRecord'];old=ids['processors']['PutDatabaseRecord']
for id in [q,old]:
 e=api('GET','/processors/'+id);api('PUT','/processors/'+id+'/run-status',{'revision':e['revision'],'state':'STOPPED'})
props={
 'SplitRecord':{'Record Reader':ids['services']['AvroReader'],'Record Writer':ids['services']['JsonRecordSetWriter'],'Records Per Split':'1'},
 'EvaluateJsonPath':{'Destination':'flowfile-attribute','sqltext':'$[0].sqltext'},
 'ReplaceText':{'Replacement Strategy':'Always Replace','Replacement Value':'${sqltext}','Evaluation Mode':'Entire text'},
 'PutSQL':{'JDBC Connection Pool':ids['services']['MO DBCP'],'Support Fragmented Transactions':'false','Batch Size':'1'}}
autos={'SplitRecord':['original','failure'],'EvaluateJsonPath':['unmatched','failure'],'ReplaceText':['failure'],'PutSQL':['success','failure','retry']}
for name,pr in props.items():
 id=ids['processors'][name];e=api('GET','/processors/'+id);e=api('PUT','/processors/'+id,{'revision':e['revision'],'component':{'id':id,'config':{'properties':pr,'autoTerminatedRelationships':autos[name],'schedulingPeriod':'1 sec'}}});print(name,e['component'].get('validationErrors'),flush=True)
connid=ids['connections']['outbox'];e=api('GET','/connections/'+connid)
e=api('PUT','/connections/'+connid,{'revision':e['revision'],'component':{'id':connid,'destination':{'id':ids['processors']['SplitRecord'],'groupId':g,'type':'PROCESSOR'}}});print('rewired',flush=True)
names=['SplitRecord','EvaluateJsonPath','ReplaceText','PutSQL'];relationships=['splits','matched','success']
for src,dst,rel in zip(names,names[1:],relationships):
 e=api('POST','/process-groups/'+g+'/connections',{'revision':{'version':0},'component':{'source':{'id':ids['processors'][src],'groupId':g,'type':'PROCESSOR'},'destination':{'id':ids['processors'][dst],'groupId':g,'type':'PROCESSOR'},'selectedRelationships':[rel]}});ids['connections'][src+'-'+dst]=e['id']
for name in ['QueryDatabaseTableRecord']+list(reversed(names)):
 id=ids['processors'][name];e=api('GET','/processors/'+id);print(name,e['component']['validationStatus'],e['component'].get('validationErrors'),flush=True);api('PUT','/processors/'+id+'/run-status',{'revision':e['revision'],'state':'RUNNING'})
(B/'nifi-ids.json').write_text(json.dumps(ids,indent=2))
