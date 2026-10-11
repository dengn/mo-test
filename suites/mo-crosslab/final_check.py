import datetime,json,time
from pathlib import Path
from data import ROOT,connect
meta=json.loads((ROOT/'results/canonical/meta.json').read_text());c=connect();counts={}
with c.cursor() as q:
    q.execute('SELECT VERSION()');version=q.fetchone()[0]
    tables=[f'cross_decisions_{w}' for w in range(meta['workers'])]+['holistic_decisions_0','holistic_decisions_1','spark_cross_decisions','joined_decisions_0','joined_decisions_1']
    for table in tables:q.execute('SELECT COUNT(*) FROM '+table);counts[table]=q.fetchone()[0];assert counts[table]==0,table
c.close();start=meta['started_at'];end=time.time();path=Path('/workspace/mo-ds-lab/server.log');events=[];first=last=None
with path.open('rb') as file:
    file.seek(meta['log_start_offset'])
    while True:
        offset=file.tell();line=file.readline()
        if not line:break
        try:r=json.loads(line);ts=datetime.datetime.strptime(r['time'],'%Y/%m/%d %H:%M:%S.%f %z').timestamp()
        except (ValueError,KeyError):continue
        if start<=ts<=end:
            if first is None:first=offset
            last=file.tell();events.append(r)
if first is not None:
    with path.open('rb') as file:file.seek(first);raw=file.read(last-first)
else:raw=b''
(ROOT/'server-canonical.log').write_bytes(raw)
trace=[r for r in events if r.get('msg')=='query trace status' and r.get('status')=='fail' and 'INTO TABLE system.statement_info' in r.get('statement','')]
panic=[r for r in events if r.get('level') in ['PANIC','FATAL']]
other=[r for r in events if r.get('level')=='ERROR' and r not in trace]
result={'all_private_decisions_empty':True,'decision_counts':counts,'server_pid':Path('/workspace/mo-ds-lab/server.pid').read_text().strip(),'server_version':version,
        'memory_events':Path('/sys/fs/cgroup/memory.events').read_text(),'panic_fatal':panic,'internal_trace_failed_loads':len(trace),'internal_trace_events_sample':trace[:3],
        'other_errors':other[:20],'other_error_count':len(other),'log_capture_start':start,'log_capture_end':end,'log_bytes':len(raw),
        'attribution_limit':'Internal logging failures are separate from recorded business outcomes. Abbreviated LOAD payloads do not prove exact source-file or case attribution; no permanent loss inferred.',
        'existing_related_issues':['https://github.com/matrixorigin/matrixone/issues/29809','https://github.com/matrixorigin/matrixone/issues/29797']}
(ROOT/'final-state.json').write_text(json.dumps(result,indent=2));print({k:result[k] for k in ['all_private_decisions_empty','server_pid','memory_events','internal_trace_failed_loads','other_error_count']})
