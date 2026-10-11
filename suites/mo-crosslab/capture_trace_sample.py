"""Retain a successful current-batch statement with an oversized trace plan, if present."""
import csv,hashlib,json,re
from pathlib import Path
from data import ROOT,DB
taxonomy=json.loads((ROOT/'error-taxonomy.json').read_text());old=Path('/workspace/mo-long-lab/telemetry/failed-statement-record.json')
schema=ROOT/'statement-info-columns.json';columns=json.loads(schema.read_text()) if schema.exists() else list(json.loads(old.read_text()));schema.write_text(json.dumps(columns,indent=2));csv.field_size_limit(64*1024*1024)
sample=None;checked=0
for upload in taxonomy['failed_upload_records']:
    if upload['predates_current_batch']:continue
    path=Path('/workspace/mo-ds-lab/mo-data/etl')/upload['path']
    if not path.exists():continue
    checked+=1;match=re.search(r'Src length (\d+)',upload.get('error',''));length=int(match[1]) if match else None
    with path.open(newline='') as file:
        for row in csv.reader(file):
            if len(row)!=len(columns):continue
            record=dict(zip(columns,row));plan=record.get('exec_plan','')
            if record.get('database')!=DB or record.get('status')!='Success' or len(plan.encode())<=65535:continue
            valid=True
            try:json.loads(plan)
            except ValueError:valid=False
            out=ROOT/'telemetry';out.mkdir(exist_ok=True);(out/'current-batch-oversized-record.json').write_text(json.dumps(record,indent=2))
            sample={'file':str(path),'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'database':record['database'],'statement_id':record.get('statement_id'),'request_at':record.get('request_at'),'stored_user_status':record.get('status'),'exec_plan_bytes':len(plan.encode()),'statement_bytes':len(record.get('statement','').encode()),'exec_plan_valid_json':valid,'etl_upload_error':upload['error'],'plan_size_matches_upload_error':len(plan.encode())==length}
            break
    if sample:break
result={'checked_new_epoch_files':checked,'current_batch_sample':sample,'scope':'Sample directly identifies the current synthetic database and a trace plan over TEXT capacity in a failed ETL upload file. Not every 403 LOAD failure is attributed to this sample; several earlier files predate the batch. Business outcomes are evaluated independently; no permanent data loss inferred.'}
(ROOT/'telemetry-analysis.json').write_text(json.dumps(result,indent=2));print(result)
