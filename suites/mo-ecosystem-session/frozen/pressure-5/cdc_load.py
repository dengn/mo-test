from runtime import *
from kafka.admin import KafkaAdminClient,NewTopic
from kafka import KafkaConsumer,TopicPartition
from psycopg.types.json import Jsonb
import itertools
N=200000;topic='stress5pg.stress5.wide';out={'runtime_ref':REF,'scope':'4-partition PG CDC -> Debezium3.1.2/JDBC4tasks per target -> MO and MySQL, composite record key. Shared 4CPU with local generator/broker/targets; functional soak/load, not EOS.','initial_source_rows':N,'cases':[]}
schema='tenant VARCHAR(32),id BIGINT,rev BIGINT,s BIGINT,u NUMERIC(20,0),d NUMERIC(38,18),payload BYTEA,name TEXT,ts TIMESTAMP(6),doc JSONB,PRIMARY KEY(tenant,id)'
def seed(i):
 return (f't{i%16:02}',i//16,0,(-1 if i%2 else 1)*(9007199254740993+i),2**64-1-i%1000,decimal.Decimal(f'12345678901234567890.{i:018d}'),None if i%11==0 else (b'' if i%7==0 else b'\x00\xff\x80'+bytes([i%256])*192+i.to_bytes(8,'big')),None if i%13==0 else ('' if i%17==0 else 'CDC中文😀'+str(i)+'x'*64),datetime.datetime(2026,10,11,12,0,0)+datetime.timedelta(microseconds=i),Jsonb({'big':9007199254740993+i,'array':[None,True,''], 'text':'文😀'}))
def insert_source(lo,hi):
 with pg(False) as d,d.cursor() as c:
  with c.copy('COPY stress5.wide FROM STDIN') as cp:
   for i in range(lo,hi):cp.write_row(seed(i))
  d.commit()
def prepare():
 psql('CREATE SCHEMA stress5');psql('CREATE TABLE stress5.wide('+schema+')');t=time.monotonic();insert_source(1,N+1)
 target=schema.replace('NUMERIC(20,0)','BIGINT UNSIGNED').replace('NUMERIC(38,18)','DECIMAL(38,18)').replace('BYTEA','VARBINARY(512)').replace('name TEXT','name VARCHAR(300)').replace('TIMESTAMP(6)','DATETIME(6)').replace('JSONB','JSON')
 for port in [6001,13306]:sql('CREATE TABLE cdc_wide('+target+')',port=port)
 a=KafkaAdminClient(bootstrap_servers='127.0.0.1:19092');a.create_topics([NewTopic(topic,4,1)]);a.close();dump(B/'cdc-seed.json',{'N':N,'prepare_seconds':time.monotonic()-t,'ports':[6001,13306],'topic':topic,'partitions':4});print('CDC SEED',N,time.monotonic()-t,flush=True)
source={'connector.class':'io.debezium.connector.postgresql.PostgresConnector','tasks.max':'1','database.hostname':'127.0.0.1','database.port':'15432','database.user':'postgres','database.password':'compat4-local','database.dbname':'postgres','topic.prefix':'stress5pg','plugin.name':'pgoutput','slot.name':'stress5_slot','publication.name':'stress5_pub','publication.autocreate.mode':'filtered','table.include.list':'stress5.wide','snapshot.mode':'initial','decimal.handling.mode':'precise','time.precision.mode':'adaptive_time_microseconds','poll.interval.ms':'100','tombstones.on.delete':'true','max.batch.size':'1024','max.queue.size':'8192'}
def sink(port):return {'connector.class':'io.debezium.connector.jdbc.JdbcSinkConnector','tasks.max':'4','connection.url':f'jdbc:mysql://127.0.0.1:{port}/stress5?useSSL=false&serverTimezone=UTC','connection.username':'root','connection.password':'111' if port==6001 else 'types-local','topics':topic,'collection.name.format':'cdc_wide','insert.mode':'upsert','primary.key.mode':'record_key','primary.key.fields':'tenant,id','delete.enabled':'true','schema.evolution':'none','use.time.zone':'UTC','batch.size':'500','consumer.override.max.poll.records':'1000'}
def progress():
 return {'MO_count':sql('SELECT COUNT(*) FROM cdc_wide')[0][0],'MySQL_count':sql('SELECT COUNT(*) FROM cdc_wide',port=13306)[0][0],'states':{n:api('GET','/connectors/'+n+'/status') for n in ['stress5-pg','stress5-mo','stress5-mysql']},'resources':resources()}
def observe(name,condition,timeout=240):
 t=time.monotonic();last=None;sampled=[]
 while time.monotonic()-t<timeout:
  guard();last=progress();sampled.append({'elapsed_s':time.monotonic()-t,'MO_count':last['MO_count'],'MySQL_count':last['MySQL_count']});dump(B/'cdc-progress.json',{'phase':name,'last':last,'samples':sampled})
  if condition(last):return time.monotonic()-t,last,sampled
  if any(v['state']=='FAILED' for s in last['states'].values() for v in s['tasks']):raise RuntimeError(json.dumps(last['states']))
  time.sleep(1)
 raise TimeoutError(json.dumps(last,default=str)[:1500])
def oracle(name):
 extra=',tag' if out.get('tag_added') else '';select='tenant,id,rev,s,u,d,payload,name,ts,doc'+extra;hashes=[hashlib.sha256() for _ in range(3)];counts=[0,0,0];bad={6001:0,13306:0};first=[];t=time.monotonic();seed_bad=0;seed_hash=hashlib.sha256()
 def canon(r):
  if r is None:return None
  v=list(r);v[4]=int(v[4]) if v[4] is not None else None;v[5]=format(v[5],'.18f') if v[5] is not None else None;v[6]=bytes(v[6]).hex() if v[6] is not None else None;v[8]=v[8].isoformat(timespec='microseconds') if v[8] else None;v[9]=json.loads(v[9]) if isinstance(v[9],str) else (v[9].obj if isinstance(v[9],Jsonb) else v[9]);return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()+b'\n'
 with pg(False) as p,db() as m,db(port=13306) as y,p.cursor(name='stress5_oracle') as pc,m.cursor(pymysql.cursors.SSCursor) as mc,y.cursor(pymysql.cursors.SSCursor) as yc:
  pc.itersize=2000;pc.execute('SELECT '+select+' FROM stress5.wide ORDER BY tenant,id');mc.execute('SELECT '+select+' FROM cdc_wide ORDER BY tenant,id');yc.execute('SELECT '+select+' FROM cdc_wide ORDER BY tenant,id')
  for rr in itertools.zip_longest(pc,mc,yc):
   b=[canon(r) for r in rr]
   if name.startswith('snapshot'):
    expected_seed=canon(seed(rr[0][1]*16+int(rr[0][0][1:])));seed_hash.update(expected_seed);seed_bad+=b[0]!=expected_seed
   for k,v in enumerate(b):
    if v is not None:hashes[k].update(v);counts[k]+=1
   for k,port in [(1,6001),(2,13306)]:
    if b[0]!=b[k]:
     bad[port]+=1
     if len(first)<5:first.append({'port':port,'source':b[0].decode() if b[0] else None,'target':b[k].decode() if b[k] else None})
 r={'phase':name,'rows_source_MO_MySQL':counts,'SHA256_source_MO_MySQL':[h.hexdigest() for h in hashes],'mismatch_counts':bad,'first_mismatches':first,'oracle_seconds':time.monotonic()-t,'seed_model_mismatches':seed_bad if name.startswith('snapshot') else None,'seed_model_sha256':seed_hash.hexdigest() if name.startswith('snapshot') else None,'status':'passed' if seed_bad==0 and all(v==0 for v in bad.values()) and counts[0]==counts[1]==counts[2] else 'failed'};out['cases'].append(r);dump(B/'cdc-load-result.json',out);print('CDC ORACLE',name,counts,bad,r['oracle_seconds'],flush=True);return r['status']=='passed'
def phase(name,mutation,revision_expected):
 t=time.monotonic();mutation();committed=time.monotonic();n=psql('SELECT COUNT(*) FROM stress5.wide')[0][0];r={'phase':name,'mutation_seconds':committed-t,'expected_source_rows':n}
 def ready(v):return v['MO_count']==v['MySQL_count']==n and all(sql('SELECT COUNT(*) FROM cdc_wide WHERE rev=%s',(revision_expected[0],),port=p)[0][0]==revision_expected[1] for p in [6001,13306])
 elapsed,last,samples=observe(name,ready,240);r.update({'source_commit_to_sampled_catchup_s':elapsed,'progress':samples});out.setdefault('arrival_phases',[]).append(r);dump(B/'cdc-load-result.json',out);return oracle(name)
def run():
 if '--resume' not in sys.argv:
  for n,c in [('stress5-pg',source),('stress5-mo',sink(6001)),('stress5-mysql',sink(13306))]:dump(B/(n+'-config.json'),c);api('PUT','/connectors/'+n+'/config',c)
 else:out['resume_profile']={'reason':'original 300s snapshot deadline not achieved; preserves original failure receipt; ongoing same group/table/offsets','MO_config':api('GET','/connectors/stress5-mo/config')}
 before=progress()
 t=time.monotonic();elapsed,last,samples=observe('snapshot_200k',lambda v:v['MO_count']==v['MySQL_count']==N,600);out['snapshot']={'sampled_seconds':time.monotonic()-t,'source_rows':N,'MO_rows_at_observation_start':before['MO_count'],'sampled_additional_MO_rows_s':(N-before['MO_count'])/(time.monotonic()-t),'progress':samples,'before_oracle':last}
 if not oracle('snapshot_200k_composite_keys_all_types'):return
 def mutate():
  psql("UPDATE stress5.wide SET rev=1,name='批量更新😀',d=0.000000000000000123 WHERE id BETWEEN 1 AND 3125")
  psql('DELETE FROM stress5.wide WHERE id BETWEEN 3126 AND 4687')
  insert_source(N+1,N+100001)
  psql("UPDATE stress5.wide SET tenant='m01',rev=2 WHERE tenant='t01' AND id BETWEEN 1 AND 4000")
 rev1=psql('SELECT 1')[0][0]
 # Formula: 3125*16 update rows, minus 3125 migrated t01 rows.
 if not phase('bulk_update_delete_insert_PK_migration',mutate,(1,3125*15)):return
 for p in [6001,13306]:sql('ALTER TABLE cdc_wide ADD COLUMN tag VARCHAR(80)',port=p)
 psql('ALTER TABLE stress5.wide ADD COLUMN tag TEXT');out['tag_added']=True
 if not phase('coordinated_schema_add_5k_updates',lambda:psql("UPDATE stress5.wide SET rev=3,tag='演进😀' WHERE id BETWEEN 5000 AND 5312"),(3,313*16)):return
 fault=kill('connect','org.apache.kafka.connect.cli.ConnectDistributed');out['worker_fault']=fault;t=time.monotonic();psql("UPDATE stress5.wide SET rev=4,name='离线积压😀' WHERE id BETWEEN 6000 AND 7562");start('connect');poll(lambda:api('GET','/connectors/stress5-pg/status'),90)
 rev4=1563*16;elapsed,last,samples=observe('worker_SIGKILL_25k_offline_updates',lambda v:all(sql('SELECT COUNT(*) FROM cdc_wide WHERE rev=4',port=p)[0][0]==rev4 for p in [6001,13306]),240);out['worker_recovery']={'inclusive_fault_to_reconcile_s':time.monotonic()-t,'progress':samples,'changed_rows':rev4};oracle('worker_SIGKILL_offline_25k_resume');out['final_source_counts']=psql('SELECT COUNT(*),COUNT(DISTINCT (tenant,id)) FROM stress5.wide');dump(B/'cdc-load-result.json',out)
if __name__=="__main__":
 if '--prepare' in sys.argv:prepare()
 else:
  try:run()
  except Exception as e:out['failed_phase_error']=str(e);out['last_progress']=progress();dump(B/'cdc-load-result.json',out);print('CDC FAILED',str(e)[:2000],flush=True);raise
