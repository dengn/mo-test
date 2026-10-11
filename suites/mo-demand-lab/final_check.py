import datetime,json
from pathlib import Path
from data import ROOT,connect
meta=json.loads((ROOT/'results/canonical/meta.json').read_text());c=connect();counts={}
with c.cursor() as q:
 q.execute('SELECT VERSION()');version=q.fetchone()[0]
 for w in range(meta['workers']):q.execute(f'SELECT COUNT(*) FROM decisions_{w}');counts[str(w)]=q.fetchone()[0];assert counts[str(w)]==0
c.close();start=meta['checkpoint']['started_at'] if meta.get('checkpoint') else meta['started_at'];events=[];first_offset=None;last_offset=None;path=Path('/workspace/mo-ds-lab/server.log')
with path.open('rb') as file:
 while True:
  offset=file.tell();line=file.readline()
  if not line:break
  try:r=json.loads(line);timestamp=datetime.datetime.strptime(r['time'],'%Y/%m/%d %H:%M:%S.%f %z').timestamp()
  except (ValueError,KeyError):continue
  if start<=timestamp<=meta['ended_at']:
   if first_offset is None:first_offset=offset
   last_offset=file.tell();events.append(r)
if first_offset is not None:
 with path.open('rb') as file:file.seek(first_offset);raw=file.read(last_offset-first_offset)
else:raw=b''
(ROOT/'server-canonical.log').write_bytes(raw);trace=[r for r in events if r.get('msg')=='query trace status' and r.get('status')=='fail' and 'INTO TABLE system.statement_info' in r.get('statement','')];panic=[r for r in events if r.get('level') in ['PANIC','FATAL']]
result={'all_decision_tables_empty':True,'decision_counts':counts,'server_pid':Path('/workspace/mo-ds-lab/server.pid').read_text().strip(),'server_version':version,'memory_events':Path('/sys/fs/cgroup/memory.events').read_text(),'panic_fatal':panic,'internal_trace_failed_loads':len(trace),'internal_trace_events_sample':trace[:3],'log_capture_start':start,'log_capture_end':meta['ended_at'],'log_capture_includes_checkpoint_gap':bool(meta.get('checkpoint')),'log_bytes':len(raw)};(ROOT/'final-state.json').write_text(json.dumps(result,indent=2));print({k:result[k] for k in ['all_decision_tables_empty','server_pid','memory_events','internal_trace_failed_loads']})
