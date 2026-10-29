from runtime import *
import uuid,traceback
from kafka import KafkaConsumer,TopicPartition
out={'runtime_ref':REF,'tool':'PostgreSQL16.14 Debezium3.1.2.Final Kafka3.9.1 JDBC3.1.2.Final','scope':'real pgoutput CDC to precreated MO sink; snapshot, keyed deletes, PK move, rolled-back transactions, explicit schema adaptation, logical slot restart','cases':[]}
psql('CREATE TABLE public.eco4_cdc(id BIGINT PRIMARY KEY,s BIGINT,d NUMERIC(38,18),payload BYTEA,name TEXT,ts TIMESTAMP(6),doc JSONB,uuid_col UUID)')
initial=[(1,9007199254740993,'12345678901234567890.123456789012345678',b'\x00\xff\x80','PG中文😀','2026-10-11 12:00:00.123456','{"big":9007199254740993}','550e8400-e29b-41d4-a716-446655440000'),(2,-9223372036854775808,'-0.000000000000000001',b'','','2026-10-11 00:00:00','[]','550e8400-e29b-41d4-a716-446655440001'),(3,None,None,None,None,None,None,None)]
for row in initial:psql('INSERT INTO eco4_cdc VALUES('+','.join(['%s']*8)+')',row)
sql(6001,'eco4','CREATE TABLE pg_cdc(id BIGINT PRIMARY KEY,s BIGINT,d DECIMAL(38,18),payload VARBINARY(100),name VARCHAR(300),ts DATETIME(6),doc JSON,uuid_col VARCHAR(36))')
source={'connector.class':'io.debezium.connector.postgresql.PostgresConnector','tasks.max':'1','database.hostname':'127.0.0.1','database.port':'15432','database.user':'postgres','database.password':'compat4-local','database.dbname':'postgres','topic.prefix':'eco4pg','plugin.name':'pgoutput','slot.name':'eco4_slot','publication.name':'eco4_publication','publication.autocreate.mode':'filtered','table.include.list':'public.eco4_cdc','snapshot.mode':'initial','decimal.handling.mode':'precise','time.precision.mode':'adaptive_time_microseconds','poll.interval.ms':'250','tombstones.on.delete':'true'}
sink={'connector.class':'io.debezium.connector.jdbc.JdbcSinkConnector','tasks.max':'1','connection.url':'jdbc:mysql://127.0.0.1:6001/eco4?useSSL=false&serverTimezone=UTC','connection.username':'root','connection.password':'111','topics':'eco4pg.public.eco4_cdc','collection.name.format':'pg_cdc','insert.mode':'upsert','primary.key.mode':'record_key','primary.key.fields':'id','delete.enabled':'true','schema.evolution':'none','use.time.zone':'UTC','batch.size':'50'}
dump(B/'pg-source-config.json',source);dump(B/'pg-sink-config.json',sink);api('PUT','/connectors/eco4-pg-source/config',source);api('PUT','/connectors/eco4-pg-sink/config',sink)
def compare():
 extra=',added_tag' if out.get('added_tag_active') else ''
 src=psql("SELECT id,s,d,encode(payload,'hex'),name,to_char(ts,'YYYY-MM-DD HH24:MI:SS.US'),doc,uuid_col::text"+extra+" FROM eco4_cdc ORDER BY id")
 dst=sql(6001,'eco4','SELECT id,s,d,LOWER(HEX(payload)),name,CAST(ts AS CHAR),doc,uuid_col'+extra+' FROM pg_cdc ORDER BY id')
 def norm(rr):
  normalized=[]
  for row in rr:
   r=list(row);r[6]=json.loads(r[6]) if isinstance(r[6],str) else r[6]
   if r[5] and r[5].endswith('.000000'):r[5]=r[5][:-7]
   normalized.append(r)
  return normalized
 return {'source_rows':norm(src),'target_rows':norm(dst),'all_fields_equal':norm(src)==norm(dst)}
def check(name,mut=None):
 r={'case':name}
 try:
  if mut:mut()
  poll(lambda:compare()['all_fields_equal'],90);r.update(compare());r['status']='passed'
 except Exception as e:r.update(compare());r['status']='failed';r['error']=str(e);r['task_status']={n:api('GET','/connectors/'+n+'/status') for n in ['eco4-pg-source','eco4-pg-sink']}
 out['cases'].append(r);dump(B/'pg-cdc-result.json',out);print('PG CDC',name,r['status'],r.get('error',''),flush=True);return r['status']=='passed'
if not check('initial_snapshot_all_native_types'):raise SystemExit(1)
check('update_signed_decimal_binary_json_microseconds',lambda:psql("UPDATE eco4_cdc SET s=-9007199254740993,d=0.000000000000000123,payload=decode('','hex'),name='PG更新😀',ts='2026-10-11 12:34:56.987654',doc=%s WHERE id=1",(json.dumps({'array':[None,True,''],'big':9007199254740993}),)))
check('delete_keyed_event_and_tombstone',lambda:psql('DELETE FROM eco4_cdc WHERE id=2'))
check('primary_key_move_delete_old_create_new',lambda:psql('UPDATE eco4_cdc SET id=30 WHERE id=3'))
with pg(False) as d:
 d.execute("INSERT INTO eco4_cdc(id,name) VALUES(99,'ROLLBACK不可见')");d.rollback()
time.sleep(3);check('source_rolled_back_transaction_not_propagated')
sql(6001,'eco4','ALTER TABLE pg_cdc ADD COLUMN added_tag VARCHAR(100)')
psql('ALTER TABLE eco4_cdc ADD COLUMN added_tag TEXT');out['added_tag_active']=True;psql("UPDATE eco4_cdc SET added_tag='版本化字段😀' WHERE id=1")
poll(lambda:sql(6001,'eco4','SELECT added_tag FROM pg_cdc WHERE id=1')[0][0]=='版本化字段😀',60);out['cases'].append({'case':'explicit_coordinated_add_column','status':'passed','source_and_target':[(1,'版本化字段😀')]});dump(B/'pg-cdc-result.json',out)
out['logical_slot_before_restart']=psql('SELECT slot_name,confirmed_flush_lsn::text,active FROM pg_replication_slots');out['connect_worker_fault']=kill('connect','org.apache.kafka.connect.cli.ConnectDistributed');dump(B/'pg-cdc-result.json',out)
psql("INSERT INTO eco4_cdc(id,s,name,added_tag) VALUES(50,9007199254740995,'离线期间新增😀','新增')");psql("UPDATE eco4_cdc SET name='离线期间更新😀' WHERE id=1");psql('DELETE FROM eco4_cdc WHERE id=30');start('connect');poll(lambda:api('GET','/connectors/eco4-pg-source/status'),90);check('worker_SIGKILL_restart_and_slot_resume')
out['logical_slot_after_restart']=psql('SELECT slot_name,confirmed_flush_lsn::text,active FROM pg_replication_slots');out['final_pk_counts']=sql(6001,'eco4','SELECT COUNT(*),COUNT(DISTINCT id) FROM pg_cdc');dump(B/'pg-cdc-result.json',out)
