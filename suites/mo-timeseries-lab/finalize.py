"""Stream records and evidence; never hold the gigabyte-sized case corpus in RAM."""
import collections,hashlib,json,os,re,time
from pathlib import Path
import numpy as np,psutil
from data import ROOT,DB,connect,tables,audit
from scenarios import QUESTIONS
INTEGER_COLUMNS=set('eid day event_id minute civil_min previous_civil utc_gap civil_gap rn signal_rank dense_order bucket service_rank low_bucket_days first_day last_day island_id island_age right_censored recent_trigger_count recovery_day recovery_wait observations raw_count late_sum demand_sum n late rows_count range_count calendar_days phase0_count phase1_count flag stock future_demand inventory_gap shipped_sum backlog later_shipped final_rank representative observed_day age staleness null_count first_min last_min first_phase0 first_phase1 next_phase2 response_gap session_id session_rank'.split())

def main():
 meta=json.loads((ROOT/'results/canonical/meta.json').read_text());assert meta['expected']==meta['completed']==10000
 for name,sha in meta['code'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,(name,'execution source changed')
 positions={};index=[];statuses=collections.Counter();families={f:collections.Counter() for f in range(50)};seen_sql=set();rows=0;timings=[];transactions=[];max_case=None;max_windows=0;checks=collections.Counter()
 with (ROOT/'failures.jsonl').open('w') as fail:
  for path in sorted((ROOT/'results/canonical').glob('cases-*.jsonl')):
   with path.open('rb') as source:
    while True:
     offset=source.tell();line=source.readline()
     if not line:break
     r=json.loads(line);cid=r['case_id'];assert cid not in positions;positions[cid]=(path,offset,len(line));statuses[r['status']]+=1;families[r['family']][r['status']]+=1;seen_sql.add(r['complexity']['sha256']);rows+=r['expected_receipt']['rows']
     ix={k:r[k] for k in ['case_id','family','name','question','parameter','parameters','client','complexity','status','query_ms','oracle_ms','total_ms']};ix['rows']=r.get('actual_receipt',{}).get('rows',0);ix['error']=r.get('error');index.append(ix)
     if r['status']!='pass':fail.write(line.decode());assert r['family']==41 and 'EXCLUDE' in r['error'],(cid,r['error'])
     else:
      timings.append(r['query_ms']);integer_cols=[j for j,col in enumerate(r['columns']) if col in INTEGER_COLUMNS]
      if integer_cols:
       gold=np.asarray(r['expected'],float);actual=np.asarray(r['actual'],float)
       if gold.size:assert np.array_equal(gold[:,integer_cols],actual[:,integer_cols],equal_nan=True),(cid,'post-run exact discrete/time-column audit')
       checks['exact_integer_time_cases']+=1;checks['exact_integer_time_cells']+=len(gold)*len(integer_cols)
     if 'publication' in r:transactions.append({k:r['publication'][k] for k in ['commit','external_visibility','persisted_rows','server_window_rows','cleanup']})
     if r['complexity']['windows']>max_windows:max_windows=r['complexity']['windows'];max_case=cid
 assert set(positions)==set(range(10000));assert len(seen_sql)==10000;assert statuses=={'pass':9800,'sql_or_stage_error':200}
 with (ROOT/'cases.jsonl').open('wb') as target:
  for cid in range(10000):
   path,offset,size=positions[cid]
   with path.open('rb') as source:source.seek(offset);target.write(source.read(size))
 index.sort(key=lambda r:r['case_id']);(ROOT/'case-index.json').write_text(json.dumps(index,separators=(',',':'),ensure_ascii=False))
 path,offset,size=positions[max_case]
 with path.open('rb') as source:source.seek(offset);longest=json.loads(source.read(size))
 (ROOT/'examples/most-windows.sql').write_text(longest['sql']+';\n')
 health=[json.loads(l) for l in (ROOT/'results/canonical/health.jsonl').open()];events=lambda r:{v.split()[0]:int(v.split()[1]) for v in r['memory_events'].splitlines()};first=events(health[0]);last=events(health[-1]);pressure={k:last[k]-first.get(k,0) for k in last};pid=health[-1]['pid'];assert psutil.Process(pid).is_running()
 audit_result=audit(tables(),'final');initial=json.loads((ROOT/'source-audit-before.json').read_text());assert audit_result==initial
 c=connect();work={}
 with c.cursor() as q:
  q.execute('SHOW TABLES');names=[r[0] for r in q.fetchall()]
  for name in names:
   if name.startswith(('ts_stage_','ts_spark_sink','ts_edge_probe','ts_gap_')):q.execute(f'SELECT COUNT(*) FROM `{name}`');work[name]=q.fetchone()[0]
 c.close();assert all(v==0 for v in work.values()),work
 base=json.loads((ROOT/'results/canonical/base-checks.json').read_text());native=json.loads((ROOT/'results/canonical/native-checks.json').read_text());nw=[r for r in native if 'native_window_columns' in r or 'native_deep_feedback' in r];assert len(base)==200 and len(nw)==264
 canonical_log=Path(os.getenv('MO_SERVER_LOG','/workspace/mo-ds-lab/server.log'))
 with canonical_log.open('rb') as f:f.seek(meta['log_start_offset']);(ROOT/'server-canonical.log').write_bytes(f.read(meta['log_end_offset']-meta['log_start_offset']))
 summary=dict(canonical=meta,counts=dict(statuses),verified_unique_case_ids=10000,distinct_sql_hashes=10000,exact_discrete_time_audit=dict(checks),verified_output_rows=sum(r['rows'] for r in index if r['status']=='pass'),expected_output_rows=rows,native_fact_configs=len(base),native_daily_fact_rows=sum(r['daily_rows'] for r in base),native_event_fact_rows=sum(r['event_rows'] for r in base),native_window_profiles=len(nw),native_window_families=22,by_family=[dict(family=f,name=QUESTIONS[f][0],title=QUESTIONS[f][1],question=QUESTIONS[f][2],counts=dict(families[f])) for f in range(50)],complexity=dict(max_windows=max_windows,max_ctes=max(r['complexity']['ctes'] for r in index),max_joins=max(r['complexity']['joins'] for r in index),max_sql_bytes=max(r['complexity']['bytes'] for r in index),longest_window_case=max_case),observed_passed_query_latency_ms=dict(zip(['p50','p95','p99','max'],map(float,[*np.quantile(timings,[.5,.95,.99]),max(timings)]))),publication=dict(cases=len(transactions),commits=sum(r['commit'] for r in transactions),rollbacks=sum(not r['commit'] for r in transactions),rows=sum(r['persisted_rows'] for r in transactions),server_window_rows=sum(r['server_window_rows'] for r in transactions),all_external_visibility_checked=all(r['external_visibility'] for r in transactions)),stability=dict(pid=pid,pid_alive=True,health_samples=len(health),health_errors=sum(not r['healthy'] for r in health),mo_peak_rss_bytes=max(r['mo_rss'] for r in health),client_peak_rss_bytes=max(r['client_rss'] for r in health),cgroup_memory_event_delta=pressure,source_full_hashes_unchanged=True,private_tables=work,notes=['cgroup max events report memory-limit pressure/reclaim, not OOM; process cache and concurrent research work affect these observations.','Capability-study NULL-default probes returned recovered query-level panic while canonical cases and health probes continued; no service crash inferred.','Main-run timings include reference/native checks and overlap with small capability probes and CH CLI/download work; not isolated performance.']),scope=['50 time-series question templates times 200 unique configurations. 43 families use the 18-source dense-grid context; seven irregular event families use the entity/event/calendar context.','Fixed retrospective received-time snapshot; corrected historical readings can have arrived after their event day. Excluding current row in a baseline does not prove point-in-time training-feature availability.','Twenty prepended history days; longer frames near the first reported day can be partial. SQL default partial-frame semantics are deliberately checked.','Expected and actual full output arrays and SQL are retained. Numeric tolerance rtol=atol=1e-7; all declared discrete/time columns audited exactly after the run.','DuckDB materializes only deep-layer CTEs through optimizer hints; unchanged math independently checked with native NumPy.','No change to MO source/server binary; four CPU quota and 16GiB, one local instance; no distributed HA/long-term-production guarantee.'])
 for name in ['spark-summary','spark-guard','performance','boundary-probes']:
  file=ROOT/(name+'.json')
  if file.exists():summary[name]=json.loads(file.read_text())
 (ROOT/'report.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False));print({k:summary[k] for k in ['counts','complexity','publication','stability']},flush=True)
if __name__=='__main__':main()
