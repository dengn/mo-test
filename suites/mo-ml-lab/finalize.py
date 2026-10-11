"""Collect honest batch-scoped server health, immutability and log evidence."""
import collections,datetime,hashlib,json,re,time
from pathlib import Path
import psutil
from data import ROOT,connect,tables,audit
def main():
 start=json.loads((ROOT/'main-start.json').read_text())['start_utc_epoch'];end=time.time();log=Path('/workspace/mo-ds-lab/server.log');groups=collections.Counter();samples=collections.defaultdict(list);loads=uploads=panic=0;total=0;predating=set();newfiles=set();upload_records=[]
 with (ROOT/'server-canonical.log').open('w') as out:
  for line in log.open(errors='replace'):
   try:r=json.loads(line)
   except ValueError:continue
   ts=r.get('time','')
   try:epoch=datetime.datetime.strptime(ts,'%Y/%m/%d %H:%M:%S.%f %z').timestamp()
   except (TypeError,ValueError):
    try:epoch=datetime.datetime.fromisoformat(ts.replace('Z','+00:00')).timestamp()
    except (TypeError,ValueError):continue
   if not start<=epoch<=end:continue
   out.write(line);total+=1
   text=json.dumps(r);level=r.get('level','');panic+=bool(level in ['PANIC','FATAL'] or r.get('msg','').startswith('panic:'))
   if level!='ERROR':continue
   if 'Src length' in text and 'Dest length 65535' in text:kind='statement_info_text_overflow_context'
   elif r.get('msg')=='upload files success' and r.get('table')=='system.statement_info' and r.get('success')==0:kind='statement_info_zero_success_batch_summary'
   elif 'txn need retry in rc mode, def changed' in text:kind='internal_rc_definition_retry'
   elif r.get('msg')=='failed to poll tn schedule commands':kind='tn_schedule_poll_error'
   elif 'cannot process request as routine is closed or busy' in r.get('msg',''):kind='frontend_routine_closed_or_busy_context'
   elif r.get('msg') in ['frontend session handling failed','frontend session read failed']:kind='frontend_session_failure_context'
   elif r.get('msg')=='error: query interrupted' and r.get('caller','').startswith('message/joinMapDependency.go:'):kind='join_dependency_interrupted_context'
   elif r.get('msg')=='mo.table.stats.task':kind='table_stats_task_context'
   else:kind='unclassified'
   groups[kind]+=1
   if len(samples[kind])<3:samples[kind].append(r)
   loads+=bool(r.get('msg')=='query trace status' and r.get('status')=='fail' and r.get('statement','').upper().startswith('LOAD DATA') and 'Dest length 65535' in text)
   if r.get('msg')=='failed to upload file to MO' and r.get('table')=='system.statement_info':
    uploads+=1;p=r.get('path','')
    try:pe=int(Path(p).name.split('_')[0])
    except ValueError:pe=0
    (predating if pe<start else newfiles).add(p)
    upload_records.append(dict(path=p,file_epoch=pe,predates_current_batch=pe<start,error=r.get('error','')))
 c=connect();empty={}
 with c.cursor() as q:
  q.execute('SHOW TABLES');names=[r[0] for r in q.fetchall() if r[0].startswith('ml_')]
  for n in names:q.execute(f'SELECT COUNT(*) FROM `{n}`');empty[n]=q.fetchone()[0]
 c.close();assert not any(empty.values());finalaudit=audit(tables(),'final');before=json.loads((ROOT/'source-audit-main-before.json').read_text());assert before==finalaudit
 health=[json.loads(l) for l in (ROOT/'main-health.jsonl').open()];binary_sha=hashlib.sha256(Path('/workspace/matrixone/mo-service').read_bytes()).hexdigest();env=json.loads((ROOT/'environment.json').read_text());assert binary_sha==env['server_binary_sha256']
 summary=dict(start_utc_epoch=start,end_utc_epoch=end,server_pid=1384,same_server_alive=psutil.pid_exists(1384),source_content_unchanged=True,empty_private_tables=empty,health_samples=len(health),health_errors=sum(not r['healthy'] for r in health),server_peak_rss=max(r['rss'] for r in health),client_peak_rss=max(r['client_tree_rss'] for r in health),memory_events=Path('/sys/fs/cgroup/memory.events').read_text(),panic_fatal_entries=panic,log_entries=total,error_entries=sum(groups.values()),error_taxonomy=dict(groups),internal_trace_failed_load_calls=loads,etl_failed_upload_entries=uploads,distinct_upload_files_predating_main=len(predating),distinct_upload_files_created_in_main_window=len(newfiles),server_binary_sha256=binary_sha,notes='Server log context counts are not business case failures. Files predating this batch can be retried during its window. No permanent trace loss or automatic retry recovery inferred. External PyTorch/Spark train models; MO stores data, model binaries and serving predictions.')
 (ROOT/'final-state.json').write_text(json.dumps(summary,indent=2));(ROOT/'error-samples.json').write_text(json.dumps(dict(samples),indent=2));(ROOT/'trace-upload-failures.json').write_text(json.dumps(upload_records,indent=2));print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
