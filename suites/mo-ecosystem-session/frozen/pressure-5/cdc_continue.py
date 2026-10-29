from runtime import *
import cdc_load as m
old=json.loads((B/'cdc-load-result.json').read_text());m.out={'runtime_ref':REF,'scope':'Continue the same 200k snapshot/275008-row mutated source and consumer offsets; do not repeat mutations. Original 300s/240s deadline failures retained separately. Explicit JDBC rewrite profile.','tag_added':False,'cases':old['cases'],'prior_deadline_receipts':['cdc-initial-deadline-result.json','cdc-bulk-deadline-result.json']};out=m.out;dump0=m.dump
def save(path,value):
 if Path(path).name=='cdc-load-result.json':path=B/'cdc-expanded-result.json'
 return dump0(path,value)
m.dump=save
try:
 t=time.monotonic();elapsed,last,samples=m.observe('resume_bulk_update_delete_insert_PK_migration',lambda v:v['MO_count']==v['MySQL_count']==275008 and all(sql('SELECT COUNT(*) FROM cdc_wide WHERE rev=1',port=p)[0][0]==46875 for p in [6001,13306]),600);out['bulk_resume']={'observed_additional_catchup_s':elapsed,'progress':samples}
 assert m.oracle('bulk_update_delete_insert_PK_migration_final_full_fields')
 for p in [6001,13306]:sql('ALTER TABLE cdc_wide ADD COLUMN tag VARCHAR(80)',port=p)
 psql('ALTER TABLE stress5.wide ADD COLUMN tag TEXT');out['tag_added']=True
 assert m.phase('coordinated_schema_add_5008_updates',lambda:psql("UPDATE stress5.wide SET rev=3,tag='演进😀' WHERE id BETWEEN 5000 AND 5312"),(3,5008))
 out['worker_fault']=kill('connect','org.apache.kafka.connect.cli.ConnectDistributed');t=time.monotonic();psql("UPDATE stress5.wide SET rev=4,name='离线积压😀' WHERE id BETWEEN 6000 AND 7562");start('connect');poll(lambda:api('GET','/connectors/stress5-pg/status'),90)
 elapsed,last,samples=m.observe('worker_SIGKILL_25008_offline_updates',lambda v:all(sql('SELECT COUNT(*) FROM cdc_wide WHERE rev=4',port=p)[0][0]==25008 for p in [6001,13306]),300);out['worker_recovery']={'inclusive_fault_to_reconcile_s':time.monotonic()-t,'progress':samples,'changed_rows':25008};assert m.oracle('worker_SIGKILL_25008_offline_updates_full_fields')
 out['final_source_counts']=psql('SELECT COUNT(*),COUNT(DISTINCT (tenant,id)) FROM stress5.wide');dump(B/'cdc-expanded-result.json',out)
 # Completion marker consumed by later isolated A/B; retains original failed receipt separately.
 dump(B/'cdc-complete.json',{'source_counts':out['final_source_counts'],'receipt':'cdc-expanded-result.json','all_fullfield_checks_passed':all(r['status']=='passed' for r in out['cases'])});print('CDC EXPANDED COMPLETE',out['final_source_counts'],flush=True)
except Exception as e:out['continuation_error']=str(e);dump(B/'cdc-expanded-result.json',out);print('CDC CONTINUE FAILED',str(e)[:1500],flush=True);raise
