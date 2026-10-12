"""Retain current-database Success trace evidence, not just old retry filenames."""
import csv,datetime,hashlib,json,re
from pathlib import Path
from data import ROOT,DB,connect
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 c=connect()
 with c.cursor() as q:q.execute('SHOW COLUMNS FROM system.statement_info');columns=[r[0] for r in q.fetchall()]
 c.close();(ROOT/'statement-info-columns.json').write_text(json.dumps(columns));meta=json.loads((ROOT/'results/canonical/meta.json').read_text());csv.field_size_limit(64*1024*1024);sample=None;checked=0;loads=0
 for line in (ROOT/'server-canonical.log').open():
  r=json.loads(line)
  if r.get('msg')=='query trace status' and r.get('status')=='fail' and r.get('statement','').lstrip().lower().startswith('load data'):loads+=1
  if r.get('msg')!='failed to upload file to MO':continue
  match=re.search(r'/([0-9]{10})_',r.get('path',''))
  if not match or int(match.group(1))<meta['started_at']:continue
  path=Path('/workspace/mo-ds-lab/mo-data/etl')/r['path']
  if not path.exists():continue
  checked+=1
  with path.open(newline='',errors='replace') as f:
   for row in csv.reader(f):
    if len(row)!=len(columns):continue
    record=dict(zip(columns,row));plan=record.get('exec_plan','')
    if record.get('database')!=DB or record.get('status')!='Success' or len(plan.encode())<=65535:continue
    when=datetime.datetime.fromisoformat(record['request_at']).replace(tzinfo=datetime.timezone.utc).timestamp()
    if not meta['started_at']<=when<=meta['ended_at']:continue
    json.loads(plan);m=re.search(r'Src length (\d+)',r.get('error',''));(ROOT/'telemetry').mkdir(exist_ok=True);(ROOT/'telemetry/current-timeseries-oversized-record.json').write_text(json.dumps(record,indent=2));sample=dict(file=str(path),file_sha256=digest(path),database=DB,statement_id=record.get('statement_id'),request_at=record['request_at'],user_status='Success',exec_plan_bytes=len(plan.encode()),exec_plan_valid_json=True,stored_statement_bytes=len(record.get('statement','').encode()),etl_error=r.get('error'),plan_size_matches_upload_error=bool(m and int(m.group(1))==len(plan.encode())));break
  if sample:break
 result=dict(new_epoch_files_checked=checked,current_database_sample=sample,failed_internal_load_trace_contexts=loads,scope='Current synthetic database, Success user status and request timestamp inside the canonical window. Does not assign a unique canonical case from a truncated statement, attribute all retries to this batch, or prove permanent trace loss/recovery.')
 (ROOT/'telemetry-analysis.json').write_text(json.dumps(result,indent=2));print(result)
if __name__=='__main__':main()
