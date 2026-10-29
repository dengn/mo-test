import json,requests,pymysql
from pathlib import Path
B=Path(__file__).parent
api='http://127.0.0.1:18083'
with pymysql.connect(host='127.0.0.1',port=6001,user='root',password='111',database='runtime_ecosystem',autocommit=True) as d,d.cursor() as c:
 c.execute('DROP TABLE IF EXISTS kc_records')
 c.execute('CREATE TABLE kc_records(id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(100),name VARCHAR(100),ts DATETIME(6),doc JSON,updated BIGINT)')
source={'connector.class':'io.debezium.connector.mysql.MySqlConnector','tasks.max':'1','database.hostname':'127.0.0.1','database.port':'13306','database.user':'root','database.password':'types-local','database.server.id':'7711','topic.prefix':'mo_cdc','database.include.list':'runtime_ecosystem','table.include.list':'runtime_ecosystem.records','schema.history.internal.kafka.bootstrap.servers':'127.0.0.1:19092','schema.history.internal.kafka.topic':'mo-cdc-schema','snapshot.mode':'initial','decimal.handling.mode':'precise','bigint.unsigned.handling.mode':'precise','time.precision.mode':'connect','include.schema.changes':'false','database.ssl.mode':'disabled'}
sink={'connector.class':'io.confluent.connect.jdbc.JdbcSinkConnector','tasks.max':'1','topics':'mo_cdc.runtime_ecosystem.records','connection.url':'jdbc:mysql://127.0.0.1:6001/runtime_ecosystem?useSSL=false&useUnicode=true&characterEncoding=UTF-8','connection.user':'root','connection.password':'111','table.name.format':'kc_records','insert.mode':'upsert','pk.mode':'record_key','pk.fields':'id','delete.enabled':'true','auto.create':'false','auto.evolve':'false','batch.size':'20','transforms':'unwrap','transforms.unwrap.type':'io.debezium.transforms.ExtractNewRecordState','transforms.unwrap.delete.tombstone.handling.mode':'tombstone','errors.tolerance':'none'}
out=[]
for name,cfg in [('mo-mysql-cdc',source),('mo-jdbc-sink',sink)]:
 (B/(name+'.json')).write_text(json.dumps({'name':name,'config':cfg},indent=2))
 r=requests.put(api+'/connectors/'+name+'/config',json=cfg,timeout=30)
 out.append({'name':name,'status_code':r.status_code,'response':r.json()})
 print(name,r.status_code,r.text[:700],flush=True)
(B/'connect-setup-result.json').write_text(json.dumps(out,indent=2))
