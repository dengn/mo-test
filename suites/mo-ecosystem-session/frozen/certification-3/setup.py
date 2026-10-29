from runtime import *
from hashlib import sha256
for p in [6001,13306]:sql(p,None,'CREATE DATABASE cert3')
ddl='id BIGINT PRIMARY KEY,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(80),name VARCHAR(200),ts DATETIME(6),doc JSON,produced_ms BIGINT'
for p in [6001,13306]:sql(p,'cert3','CREATE TABLE records('+ddl+')')
sql(6001,'cert3','CREATE TABLE direct_bench(id BIGINT PRIMARY KEY,v BIGINT,payload VARBINARY(128))')
sql(13306,'cert3','CREATE TABLE eos_events(event_id BIGINT PRIMARY KEY,delta BIGINT,payload VARCHAR(100))')
sql(6001,'cert3','CREATE TABLE eos_native_append(event_id BIGINT,delta BIGINT,payload VARCHAR(100))')
sql(6001,'cert3','CREATE TABLE eos_ledger(event_id BIGINT PRIMARY KEY,topic VARCHAR(150),partition_id INT,offset_id BIGINT,delta BIGINT)')
sql(6001,'cert3','CREATE TABLE eos_totals(id INT PRIMARY KEY,n BIGINT)');sql(6001,'cert3','INSERT INTO eos_totals VALUES(1,0)')
sql(6001,'cert3','CREATE TABLE eos_checkpoint(topic VARCHAR(150),partition_id INT,last_offset BIGINT,PRIMARY KEY(topic,partition_id))')
source=json.loads((B.parent/'runtime-expanded-2/source-config.json').read_text());source.update({'database.server.id':'7733','topic.prefix':'cert3cdc','database.include.list':'cert3','table.include.list':'cert3.*','schema.history.internal.kafka.topic':'cert3-schema','max.batch.size':'1024','max.queue.size':'8192','poll.interval.ms':'250'})
sink=json.loads((B.parent/'runtime-expanded-2/wide-sink-config.json').read_text());sink.update({'topics':'cert3cdc.cert3.records','connection.url':'jdbc:mysql://127.0.0.1:6001/cert3?useSSL=false','collection.name.format':'records','batch.size':'500'})
api('PUT','/connectors/cert3-source/config',source);api('PUT','/connectors/cert3-sink/config',sink);dump(B/'source-config.json',source);dump(B/'sink-config.json',sink)
ids=json.loads((B.parent/'runtime-expanded-2/nifi-ids.json').read_text());base='http://127.0.0.1:10088/nifi-api'
for name in ['PutSQL','ReplaceText','EvaluateJsonPath','SplitRecord']:
 id=ids['processors'][name];e=api('GET','/processors/'+id,port=10088) if False else requests.get(base+'/processors/'+id).json()
 r=requests.put(base+'/processors/'+id+'/run-status',json={'revision':e['revision'],'state':'STOPPED'},timeout=15);r.raise_for_status()
 poll(lambda:requests.get(base+'/processors/'+id).json()['component']['state']=='STOPPED',20)
 e=requests.get(base+'/processors/'+id).json();config={'schedulingPeriod':'0 sec'}
 if name=='PutSQL':config['properties']={'Batch Size':'100'}
 r=requests.put(base+'/processors/'+id,json={'revision':e['revision'],'component':{'id':id,'config':config}},timeout=15);r.raise_for_status()
 e=requests.get(base+'/processors/'+id).json();r=requests.put(base+'/processors/'+id+'/run-status',json={'revision':e['revision'],'state':'RUNNING'},timeout=15);r.raise_for_status()
dump(B/'nifi-ids.json',ids)
poll(lambda:all(t['state']=='RUNNING' for t in api('GET','/connectors/cert3-source/status')['tasks']) and bool(api('GET','/connectors/cert3-source/status')['tasks']),90)
hardware={'runtime_ref':REF,'cpu_quota':Path('/sys/fs/cgroup/cpu.max').read_text().strip(),'memory_limit':Path('/sys/fs/cgroup/memory.max').read_text().strip(),'versions':{'Kafka':'3.9.1','Debezium':'3.1.2.Final','NiFi':'2.4.0','PyMySQL':pymysql.__version__},'nifi_tuning':'QDB polling remains 1 sec; Split/Evaluate/Replace/PutSQL period=0 sec; PutSQL batch=100; failures/retries retained','worker_configuration':(B/'connect.properties').read_text(),'source_version':sql(13306,None,'SELECT VERSION()'),'mo_version':sql(6001,None,'SELECT VERSION()'),'certification_scope':'single-node shared 4 CPU quota; no external capacity or HA certification'}
dump(B/'conditions.json',hardware);print('SETUP COMPLETE',flush=True)
