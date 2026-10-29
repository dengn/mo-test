import requests,json,pymysql
from pathlib import Path
B=Path(__file__).parent;API='http://127.0.0.1:10088/nifi-api';ids=json.loads((B/'nifi-ids.json').read_text());g=ids['group']
def api(m,p,d=None):
 r=requests.request(m,API+p,json=d,timeout=20);r.raise_for_status();return r.json()
def db(port):return pymysql.connect(host='127.0.0.1',port=port,user='root',password='111' if port==6001 else 'types-local',database='runtime_ecosystem',autocommit=True)
cols=['id','s','u','d','payload','name','ts','doc','updated']
def expr(prefix='NEW',cols=cols):
 args=[]
 for col in cols:
  x=prefix+'.'+col
  part=(f"IF({x} IS NULL,'NULL',CONCAT(\"X'\",HEX({x}),\"'\"))" if col=='payload' else f"IF({x} IS NULL,'NULL',QUOTE(CAST({x} AS CHAR)))")
  if args:args.append("','")
  args.append(part)
 head="'INSERT INTO nifi_outbox_target("+','.join(cols)+") VALUES('"
 tail="') ON DUPLICATE KEY UPDATE "+','.join(x+'=VALUES('+x+')' for x in cols if x!='id')+"'"
 return 'CONCAT('+','.join([head]+args+[tail])+')'
with db(13306) as d,d.cursor() as c:
 for t in ['nifi_source','nifi_outbox']:c.execute('DROP TABLE IF EXISTS '+t)
 c.execute('CREATE TABLE nifi_source(id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(100),name VARCHAR(100),ts DATETIME(6),doc JSON,updated BIGINT)')
 c.execute('CREATE TABLE nifi_outbox(seq BIGINT AUTO_INCREMENT PRIMARY KEY,sqltext TEXT NOT NULL)')
 for op in ['INSERT','UPDATE']:
  c.execute(f'CREATE TRIGGER nifi_{op.lower()} AFTER {op} ON nifi_source FOR EACH ROW INSERT INTO nifi_outbox(sqltext) VALUES({expr()})')
 c.execute("CREATE TRIGGER nifi_delete AFTER DELETE ON nifi_source FOR EACH ROW INSERT INTO nifi_outbox(sqltext) VALUES(CONCAT('DELETE FROM nifi_outbox_target WHERE id=',CAST(OLD.id AS CHAR)))")
 c.execute('INSERT INTO nifi_source SELECT '+','.join(cols)+' FROM records')
 c.execute('SELECT * FROM nifi_outbox ORDER BY seq');(B/'nifi-outbox-initial.json').write_text(json.dumps(c.fetchall(),ensure_ascii=False,indent=2))
with db(6001) as d,d.cursor() as c:
 c.execute('DROP TABLE IF EXISTS nifi_outbox_target')
 c.execute('CREATE TABLE nifi_outbox_target(id BIGINT PRIMARY KEY,s BIGINT,u BIGINT UNSIGNED,d DECIMAL(38,18),payload VARBINARY(100),name VARCHAR(100),ts DATETIME(6),doc JSON,updated BIGINT)')
q=ids['processors']['QueryDatabaseTableRecord'];w=ids['processors']['PutDatabaseRecord']
for id,props in [(q,{'Database Connection Pooling Service':ids['services']['DBCPConnectionPool'],'db-fetch-db-type':'MySQL','Table Name':'nifi_outbox','Columns to Return':'seq,sqltext','Maximum-value Columns':'seq','qdbtr-record-writer':ids['services']['AvroRecordSetWriter']}),(w,{'put-db-record-statement-type':'SQL','put-db-record-field-containing-sql':'sqltext'})]:
 e=api('GET','/processors/'+id);e=api('PUT','/processors/'+id,{'revision':e['revision'],'component':{'id':id,'config':{'properties':props,'schedulingPeriod':'1 sec'}}});print(e['component']['name'],e['component'].get('validationErrors'),flush=True)
e=api('POST','/process-groups/'+g+'/connections',{'revision':{'version':0},'component':{'source':{'id':q,'groupId':g,'type':'PROCESSOR'},'destination':{'id':w,'groupId':g,'type':'PROCESSOR'},'selectedRelationships':['success']}});ids['connections']['outbox']=e['id'];(B/'nifi-ids.json').write_text(json.dumps(ids,indent=2))
for id in [q,w]:
 e=api('GET','/processors/'+id);r=api('PUT','/processors/'+id+'/run-status',{'revision':e['revision'],'state':'RUNNING'});print('started',id,flush=True)
