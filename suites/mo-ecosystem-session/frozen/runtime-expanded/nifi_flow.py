import requests,json,pymysql
from pathlib import Path
B=Path(__file__).parent;API='http://127.0.0.1:10088/nifi-api'
ids=json.loads((B/'nifi-ids.json').read_text());group=ids['group']
def api(method,path,body=None):
 r=requests.request(method,API+path,json=body,timeout=20);r.raise_for_status();return r.json()
def svc(id,props):
 e=api('GET','/controller-services/'+id);e=api('PUT','/controller-services/'+id,{'revision':e['revision'],'component':{'id':id,'properties':props}})
 return api('PUT','/controller-services/'+id+'/run-status',{'revision':e['revision'],'state':'ENABLED'})
def proc(id,props,auto=[]):
 e=api('GET','/processors/'+id);return api('PUT','/processors/'+id,{'revision':e['revision'],'component':{'id':id,'config':{'properties':props,'autoTerminatedRelationships':auto,'schedulingPeriod':'1 sec'}}})
src=ids['services']['DBCPConnectionPool'];t=api('GET','/controller-services/'+src)['component']
e=api('POST','/process-groups/'+group+'/controller-services',{'revision':{'version':0},'component':{'name':'MO DBCP','type':t['type'],'bundle':t['bundle']}});sink=e['id'];ids['services']['MO DBCP']=sink
for id,port,pw in [(src,13306,'types-local'),(sink,6001,'111')]:
 svc(id,{'Database Connection URL':f'jdbc:mysql://127.0.0.1:{port}/runtime_ecosystem?useSSL=false&useUnicode=true&characterEncoding=UTF-8','Database Driver Class Name':'com.mysql.cj.jdbc.Driver','database-driver-locations':'/workspace/work/path-verification/jars/mysql-jdbc.jar','Database User':'root','Password':pw})
for name in ['AvroRecordSetWriter','AvroReader','JsonTreeReader','JsonRecordSetWriter']:svc(ids['services'][name],{})
with pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='runtime_ecosystem',autocommit=True) as d,d.cursor() as c:
 c.execute('DROP TABLE IF EXISTS nifi_records')
 c.execute('CREATE TABLE nifi_records(id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(100),name VARCHAR(100),ts DATETIME(6),doc JSON,updated BIGINT)')
read=ids['processors']['ExecuteSQLRecord'];write=ids['processors']['PutDatabaseRecord']
proc(read,{'Database Connection Pooling Service':src,'esqlrecord-record-writer':ids['services']['AvroRecordSetWriter'],'SQL Query':'SELECT * FROM records ORDER BY id','dbf-user-logical-types':'true'},['failure'])
proc(write,{'put-db-record-record-reader':ids['services']['AvroReader'],'put-db-record-dcbp-service':sink,'put-db-record-table-name':'nifi_records','put-db-record-statement-type':'UPSERT','db-type':'MySQL','put-db-record-update-keys':'id'},['success','failure','retry'])
e=api('POST','/process-groups/'+group+'/connections',{'revision':{'version':0},'component':{'source':{'id':read,'groupId':group,'type':'PROCESSOR'},'destination':{'id':write,'groupId':group,'type':'PROCESSOR'},'selectedRelationships':['success']}});ids['connections']={'native':e['id']}
(B/'nifi-ids.json').write_text(json.dumps(ids,indent=2))
for id in [read,write]:
 e=api('GET','/processors/'+id);print(e['component']['name'],e['component']['validationStatus'],e['component'].get('validationErrors'),flush=True)
 e=api('PUT','/processors/'+id+'/run-status',{'revision':e['revision'],'state':'RUN_ONCE'});print('run once',id,flush=True)
