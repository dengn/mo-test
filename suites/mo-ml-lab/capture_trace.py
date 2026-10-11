"""Identify current ML database records, not merely old trace retry filenames."""
import csv,datetime,hashlib,json,re,shutil
from pathlib import Path
from data import ROOT,DB
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 schema=ROOT/'statement-info-columns.json'
 if not schema.exists():shutil.copy2('/workspace/mo-crosslab/statement-info-columns.json',schema)
 columns=json.loads(schema.read_text());uploads=json.loads((ROOT/'trace-upload-failures.json').read_text());state=json.loads((ROOT/'final-state.json').read_text());csv.field_size_limit(64*1024*1024);seen=set();sample=None;checked=0
 for u in uploads:
  if u['predates_current_batch'] or u['path'] in seen:continue
  seen.add(u['path']);p=Path('/workspace/mo-ds-lab/mo-data/etl')/u['path']
  if not p.exists():continue
  checked+=1
  with p.open(newline='',errors='replace') as f:
   for row in csv.reader(f):
    if len(row)!=len(columns):continue
    record=dict(zip(columns,row));plan=record.get('exec_plan','');request=record.get('request_at','')
    if record.get('database')!=DB or record.get('status')!='Success' or len(plan.encode())<=65535:continue
    try:epoch=datetime.datetime.fromisoformat(request).replace(tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:continue
    if not state['start_utc_epoch']<=epoch<=state['end_utc_epoch']:continue
    try:json.loads(plan);valid=True
    except ValueError:valid=False
    match=re.search(r'Src length (\d+)',u['error']);src=int(match[1]) if match else None;(ROOT/'telemetry').mkdir(exist_ok=True);(ROOT/'telemetry/current-ml-oversized-record.json').write_text(json.dumps(record,indent=2));sample=dict(file=str(p),file_sha256=digest(p),database=DB,statement_id=record.get('statement_id'),request_at=request,user_status='Success',exec_plan_bytes=len(plan.encode()),exec_plan_json_valid=valid,etl_upload_error=u['error'],plan_size_matches_upload_error=src==len(plan.encode()));break
  if sample:break
 result=dict(new_files_checked=checked,current_ml_batch_sample=sample,scope='Matches the ML synthetic database, Success status and request timestamp inside the canonical window. One sample does not attribute all background errors to this batch or prove permanent trace loss.');(ROOT/'telemetry-analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
