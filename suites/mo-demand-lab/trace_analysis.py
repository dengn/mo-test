"""Do not attribute background telemetry retries to successful user workflows."""
import csv,datetime,hashlib,json,re
from pathlib import Path
from data import ROOT,DB
state=json.loads((ROOT/'final-state.json').read_text());events=state['internal_trace_events_sample'];start=state['log_capture_start'];length=int(re.search(r'Src length (\d+)',events[0]['error'])[1]) if events else None
columns=list(json.loads(Path('/workspace/mo-long-lab/telemetry/failed-statement-record.json').read_text()));csv.field_size_limit(64*1024*1024);sample=None
for file in sorted(Path('/workspace/mo-ds-lab/mo-data/etl/sys/logs/2026/10/11/statement_info').glob('*.csv')):
 if not length or int(file.name.split('_')[0])>=start:continue
 with file.open(newline='') as handle:
  for row in csv.reader(handle):
   if len(row)!=len(columns):continue
   r=dict(zip(columns,row));plan=r['exec_plan']
   if len(plan.encode())!=length:continue
   sample={'file':str(file),'file_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'statement_id':r['statement_id'],'source_database':r['database'],'request_at':r['request_at'],'stored_user_status':r['status'],'exec_plan_bytes':len(plan.encode()),'statement_bytes':len(r['statement'].encode()),'file_predates_this_batch':int(file.name.split('_')[0])<start,'exec_plan_valid_json':False}
   try:json.loads(plan);sample['exec_plan_valid_json']=True
   except ValueError:pass
   out=ROOT/'telemetry';out.mkdir(exist_ok=True);(out/'historical-overflow-record.json').write_text(json.dumps(r,indent=2));break
 if sample:break
result={'user_case_outcomes':{'pass':10000},'internal_trace_failed_load_events':state['internal_trace_failed_loads'],'error_class':'Internal statement_info TEXT capacity 65535 exceeded','related_existing_issues':[{'number':29797,'url':'https://github.com/matrixorigin/matrixone/issues/29797'},{'number':29809,'url':'https://github.com/matrixorigin/matrixone/issues/29809'}],'sample_historical_record':sample,'attribution_limit':'The retained historical record predates this demand batch and matches the first failure source length. Internal LOAD payloads are abbreviated; exact event-to-file identity and attribution of every event have not been established. No newly failed business case, permanent loss, or new defect is inferred.','new_issue_submitted':False};(ROOT/'failure-analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'events':state['internal_trace_failed_loads'],'historical_sample':sample},indent=2))
