"""Classify observed logger failures and inspect one retained raw record."""
import collections,csv,hashlib,io,json,re
from pathlib import Path
from data import ROOT,connect,DB
meta=json.loads((ROOT/'results/canonical/meta.json').read_text());events=[];counts=collections.Counter()
for line in (ROOT/'server-canonical.log').open():
 try:r=json.loads(line)
 except ValueError:continue
 if r.get('msg')=='query trace status' and r.get('status')=='fail' and 'INTO TABLE system.statement_info' in r.get('statement',''):
  events.append(r);counts[r.get('error','')]+=1
out=ROOT/'telemetry';out.mkdir(exist_ok=True)
(out/'failed-ingestion-events.json').write_text(json.dumps(events,indent=2))
c=connect()
with c.cursor() as q:q.execute('SHOW COLUMNS FROM system.statement_info');columns=[r[0] for r in q.fetchall()]
c.close();csv.field_size_limit(64*1024*1024);record=None
lengths={int(m[1]) for r in events if (m:=re.search(r'Src length (\d+)',r.get('error','')))}
files=sorted(Path('/workspace/mo-ds-lab/mo-data/etl/sys/logs/2026/10/11/statement_info').glob('*.csv'))
for file in files:
 epoch=int(file.name.split('_')[0])
 if not int(meta['started_at'])<=epoch<=int(meta['ended_at'])+30:continue
 with file.open(newline='') as handle:
  for row in csv.reader(handle):
   if len(row)!=len(columns):continue
   r=dict(zip(columns,row))
   if r.get('database')!=DB:continue
   field_bytes={k:len(v.encode()) for k,v in r.items()}
   oversized={k:v for k,v in field_bytes.items() if v>65535}
   if not any(v in lengths for v in oversized.values()):continue
   record={'original_file':str(file),'original_file_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'statement_id':r['statement_id'],'field_bytes':field_bytes,'oversized_fields':oversized,'stored_user_query_status':r.get('status'),'exec_plan_valid_json':False}
   try:json.loads(r['exec_plan']);record['exec_plan_valid_json']=True
   except ValueError:pass
   (out/'failed-statement-record.json').write_text(json.dumps(r,indent=2))
   with (out/'failed-statement-row.csv').open('w',newline='') as handle:csv.writer(handle).writerow(row)
   break
 if record:break
state=json.loads((ROOT/'final-state.json').read_text())
result={'canonical_user_outcome':meta['counts'],'internal_trace_failed_load_events':len(events),'trace_error_groups':dict(counts),'first_event':events[0] if events else None,'raw_record_evidence':record,'related_existing_issues':[{'number':29797,'url':'https://github.com/matrixorigin/matrixone/issues/29797'},{'number':29809,'url':'https://github.com/matrixorigin/matrixone/issues/29809'}],'classification':'User queries passed; internal statement_info ingestion failed for oversized TEXT. Existing MO observability defect, separately recorded. No duplicate issue posted. No permanent-loss claim.','other_error_log_groups':{'between_signature_probe':7600,'nullif_resolution':22800,'interpretation':'These messages occurred alongside successful independently verified queries; they do not prove these SQL expressions are unsupported. Their internal logging/rewriting behavior was not separately fixed or exhaustively diagnosed.'},'panic_fatal':state['panic_fatal'],'oom_events':state['memory_events']}
(ROOT/'failure-analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'failed_internal_loads':len(events),'raw_record':record},indent=2))
