import requests,json,shutil
from pathlib import Path
B=Path(__file__).parent;API='http://127.0.0.1:10088/nifi-api'
def api(method,path,body=None):
 r=requests.request(method,API+path,json=body,timeout=30);r.raise_for_status();return r.json()
root=api('GET','/flow/process-groups/root')['processGroupFlow']['id']
types=api('GET','/flow/processor-types')['processorTypes'];services=api('GET','/flow/controller-service-types')['controllerServiceTypes']
def find(items,name):return next(x for x in items if x['type'].endswith('.'+name))
group=api('POST','/process-groups/'+root+'/process-groups',{'revision':{'version':0},'component':{'name':'MO runtime qualification','position':{'x':0,'y':0}}})['id']
ids={'group':group,'services':{},'processors':{}}
for name in ['DBCPConnectionPool','AvroRecordSetWriter','AvroReader','JsonTreeReader','JsonRecordSetWriter']:
 t=find(services,name);e=api('POST','/process-groups/'+group+'/controller-services',{'revision':{'version':0},'component':{'name':name,'type':t['type'],'bundle':t['bundle']}});ids['services'][name]=e['id'];(B/('nifi-service-'+name+'.json')).write_text(json.dumps(e,indent=2))
for i,name in enumerate(['ExecuteSQLRecord','QueryDatabaseTableRecord','PutDatabaseRecord','GenerateFlowFile']):
 t=find(types,name);e=api('POST','/process-groups/'+group+'/processors',{'revision':{'version':0},'component':{'name':name,'type':t['type'],'bundle':t['bundle'],'position':{'x':i*400,'y':100}}});ids['processors'][name]=e['id'];(B/('nifi-processor-'+name+'.json')).write_text(json.dumps(e,indent=2))
(B/'nifi-ids.json').write_text(json.dumps(ids,indent=2))
for name,id in ids['processors'].items():
 e=api('GET','/processors/'+id);cfg=e['component']['config'];print(name,'properties',cfg['properties'],'allowed', {k:v.get('allowableValues') for k,v in cfg['descriptors'].items() if v.get('allowableValues')},flush=True)
for name,id in ids['services'].items():
 e=api('GET','/controller-services/'+id);print(name,'properties',e['component']['properties'],flush=True)
