"""Classify every ERROR entry without equating logging contexts to business cases."""
import collections,csv,hashlib,json,re
from pathlib import Path
from data import ROOT
state=json.loads((ROOT/'final-state.json').read_text());groups=collections.Counter();samples=collections.defaultdict(list);uploads=[]
for line in (ROOT/'server-canonical.log').open():
    try:r=json.loads(line)
    except ValueError:continue
    if r.get('level')!='ERROR':continue
    text=json.dumps(r)
    if 'Src length' in text and 'Dest length 65535' in text:kind='statement_info_text_overflow_context'
    elif r.get('msg')=='upload files success' and r.get('table')=='system.statement_info' and r.get('success')==0:kind='statement_info_zero_success_batch_summary'
    elif 'txn need retry in rc mode, def changed' in text:kind='internal_rc_definition_retry'
    elif r.get('msg')=='failed to poll tn schedule commands':kind='tn_schedule_poll_error'
    elif r.get('msg')=='mo.table.stats.task':kind='table_stats_task_context'
    else:kind='unclassified'
    groups[kind]+=1
    if len(samples[kind])<3:samples[kind].append(r)
    if r.get('msg')=='failed to upload file to MO' and r.get('table')=='system.statement_info':
        path=r.get('path','')
        try:epoch=int(Path(path).name.split('_')[0])
        except ValueError:epoch=None
        uploads.append({'path':path,'file_epoch':epoch,'predates_current_batch':bool(epoch and epoch<state['log_capture_start']),'error':r.get('error')})
result={'error_entries':sum(groups.values()),'categories':dict(groups),'samples':dict(samples),'internal_trace_failed_load_calls':state['internal_trace_failed_loads'],
        'etl_failed_upload_entries':len(uploads),'failed_upload_entries_predating_current_batch':sum(r['predates_current_batch'] for r in uploads),'distinct_failed_upload_files':len({r['path'] for r in uploads}),'failed_upload_files_predating_current_batch':len({r['path'] for r in uploads if r['predates_current_batch']}),'failed_upload_records':uploads,
        'interpretation':'Counts are ERROR log entries and may include several records for one failed internal LOAD/ETL operation; they are not additional failed business cases. RC metadata-retry and TN scheduling-poll messages are recorded separately; no successful recovery or new defect inferred solely from these logs. All recorded business results and health checks are independently evaluated.'}
state['error_taxonomy']=dict(groups);state['unclassified_error_count']=groups['unclassified'];(ROOT/'final-state.json').write_text(json.dumps(state,indent=2))
(ROOT/'error-taxonomy.json').write_text(json.dumps(result,indent=2))
print({'error_entries':sum(groups.values()),'categories':dict(groups),'failed_upload_files_predating_current_batch':result['failed_upload_files_predating_current_batch']})
for x in samples['tn_schedule_poll_error']:print({k:v for k,v in x.items() if k in ['time','msg','error','cause','err','caller']})
