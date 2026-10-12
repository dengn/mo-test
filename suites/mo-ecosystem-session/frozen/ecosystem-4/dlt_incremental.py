from runtime import *
import dlt,sys,datetime as dt,traceback
from dlt.destinations import sqlalchemy
from dlt.sources.sql_database import sql_table
DS='eco4_dlt_incremental';SOURCE='postgresql+psycopg://postgres:compat4-local@127.0.0.1:15432/postgres'
def pipeline():return dlt.pipeline(pipeline_name=DS,pipelines_dir=str(B/'dlt-state'),destination=sqlalchemy(credentials='mysql+pymysql://root:111@127.0.0.1:6001/eco4'),dataset_name=DS)
def resource():
 r=sql_table(SOURCE,table='eco4_dlt_view',schema='public',incremental=dlt.sources.incremental('cursor',initial_value=0),detect_precision_hints=True,reflection_level='full_with_precision',primary_key='id',write_disposition='merge')
 r.apply_hints(table_name='records',columns={'id':{'dedup_sort':'asc'},'amount':{'data_type':'decimal','precision':38,'scale':18},'ts':{'data_type':'timestamp','precision':6,'timezone':False},'doc':{'data_type':'json'},'deleted':{'data_type':'bool','hard_delete':True}})
 return r
if len(sys.argv)>1:
 p=pipeline()
 if sys.argv[1]=='pause':
  p.extract(resource());p.normalize();dump(B/'dlt-before-load-marker.json',{'pid':os.getpid(),'pending_load_ids':p.list_normalized_load_packages(),'UTC':datetime.datetime.now(datetime.timezone.utc).isoformat()})
  while True:time.sleep(.2)
 elif sys.argv[1]=='resume':print(p.load(),flush=True)
 raise SystemExit(0)
psql('CREATE TABLE eco4_dlt_source(id BIGINT PRIMARY KEY,s BIGINT,amount NUMERIC(38,18),payload BYTEA,name TEXT,ts TIMESTAMP(6),doc JSONB,cursor BIGINT,deleted BOOLEAN DEFAULT FALSE,new_tag TEXT)')
for row in [(1,9007199254740993,'12345678901234567890.123456789012345678',b'\x00\xff\x80','抽取😀','2026-10-11 12:00:00.123456','{"big":9007199254740993}',1),(2,-2**63,'-0.000000000000000001',b'','','2026-10-11 00:00:00','[]',2),(3,None,None,None,None,None,None,3)]:psql('INSERT INTO eco4_dlt_source(id,s,amount,payload,name,ts,doc,cursor) VALUES('+','.join(['%s']*8)+')',row)
psql("CREATE VIEW eco4_dlt_view AS SELECT id,s,amount,encode(payload,'hex') AS payload_hex,name,ts,doc,cursor,deleted FROM eco4_dlt_source")
out={'runtime_ref':REF,'tool':'dlt1.31.0 official sql_database source + sqlalchemy destination','scope':'PostgreSQL full/incremental extract to MO, explicit dedup-sort and bytea hex envelope; actual state and package crash recovery; not native EOS','cases':[]}
def compare():
 extra=',new_tag' if out.get('schema_added') else ''
 s=psql("SELECT id,s,amount,upper(encode(payload,'hex')),name,ts,doc,cursor"+extra+' FROM eco4_dlt_source WHERE NOT deleted ORDER BY id');t=sql(6001,DS,'SELECT id,s,amount,HEX(UNHEX(payload_hex)),name,ts,doc,cursor'+extra+' FROM records ORDER BY id')
 def norm(rr):return [list(row[:6])+[json.loads(row[6]) if isinstance(row[6],str) else row[6]]+list(row[7:]) for row in rr]
 return {'source_rows':norm(s),'target_rows':norm(t),'all_fields_equal':norm(s)==norm(t)}
def run(name,mutation=None):
 r={'case':name}
 try:
  if mutation:mutation()
  p=pipeline();info=p.run(resource());r['load_ids']=info.loads_ids;r.update(compare());r['status']='passed' if r['all_fields_equal'] else 'failed_fidelity';r['pipeline_state']=p.state
 except Exception as e:r['status']='failed';r['error']=str(e);r['traceback']=traceback.format_exc()
 out['cases'].append(r);dump(B/'dlt-incremental-result.json',out);print('DLT INCR',name,r['status'],flush=True);return r['status']=='passed'
if not run('initial_snapshot_typed_and_empty_binary_envelope'):raise SystemExit(1)
if not run('no_changes_no_new_load_package'):raise SystemExit(1)
def updates():
 psql("UPDATE eco4_dlt_source SET name='增量更新😀',amount=0.000000000000000123,cursor=4 WHERE id=1")
 psql("INSERT INTO eco4_dlt_source(id,s,name,cursor) VALUES(4,9007199254740995,'增量新增😀',5)")
if not run('incremental_update_and_insert',updates):raise SystemExit(1)
if not run('incremental_hard_delete_tombstone',lambda:psql('UPDATE eco4_dlt_source SET deleted=TRUE,cursor=6 WHERE id=2')):raise SystemExit(1)
psql("CREATE OR REPLACE VIEW eco4_dlt_view AS SELECT id,s,amount,encode(payload,'hex') AS payload_hex,name,ts,doc,cursor,deleted,new_tag FROM eco4_dlt_source");out['schema_added']=True
if not run('incremental_schema_add',lambda:psql("UPDATE eco4_dlt_source SET new_tag='演进😀',cursor=7 WHERE id=4")):raise SystemExit(1)
psql("UPDATE eco4_dlt_source SET name='包恢复😀',cursor=8 WHERE id=1")
child=subprocess.Popen([sys.executable,__file__,'pause'],stdout=(B/'dlt-paused.log').open('wb'),stderr=subprocess.STDOUT);poll(lambda:(B/'dlt-before-load-marker.json').exists(),60);marker=json.loads((B/'dlt-before-load-marker.json').read_text());assert marker['pid']==child.pid;os.kill(child.pid,signal.SIGKILL);child.wait(timeout=5)
proc=subprocess.run([sys.executable,__file__,'resume'],stdout=(B/'dlt-resumed.log').open('wb'),stderr=subprocess.STDOUT,timeout=60);r={'case':'SIGKILL_after_normalize_before_load_then_resume_pending_package','fault_marker':marker,'child_exit':child.returncode,'resume_exit':proc.returncode};r.update(compare());r['status']='passed' if proc.returncode==0 and r['all_fields_equal'] else 'failed';out['cases'].append(r);dump(B/'dlt-incremental-result.json',out);print('DLT INCR',r['case'],r['status'],flush=True)
run('post_recovery_no_changes_no_duplicate')
