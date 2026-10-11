"""Refine the fixed captured log window; do not silently extend its endpoint."""
import collections,json
from data import ROOT
def main():
 state=json.loads((ROOT/'final-state.json').read_text());groups=collections.Counter();samples=collections.defaultdict(list)
 for l in (ROOT/'server-canonical.log').open():
  r=json.loads(l)
  if r.get('level')!='ERROR':continue
  text=json.dumps(r);msg=r.get('msg','')
  if 'Src length' in text and 'Dest length 65535' in text:k='statement_info_text_overflow_context'
  elif msg=='upload files success' and r.get('table')=='system.statement_info' and r.get('success')==0:k='statement_info_zero_success_batch_summary'
  elif 'txn need retry in rc mode, def changed' in text:k='internal_rc_definition_retry'
  elif msg=='failed to poll tn schedule commands':k='tn_schedule_poll_error'
  elif 'cannot process request as routine is closed or busy' in msg:k='frontend_routine_closed_or_busy_context'
  elif msg in ['frontend session handling failed','frontend session read failed']:k='frontend_session_failure_context'
  elif msg=='error: query interrupted' and r.get('caller','').startswith('message/joinMapDependency.go:'):k='join_dependency_interrupted_context'
  elif msg=='mo.table.stats.task':k='table_stats_task_context'
  else:k='unclassified'
  groups[k]+=1
  if len(samples[k])<3:samples[k].append(r)
 assert sum(groups.values())==state['error_entries'];state['error_taxonomy']=dict(groups);state['unclassified_error_entries']=groups['unclassified'];state['notes']+=' Frontend busy/closed and join-dependency interruption messages retained separately. No failed business result, request attribution, normal-cleanup conclusion or automatic recovery inferred from these contexts.';(ROOT/'final-state.json').write_text(json.dumps(state,indent=2));(ROOT/'error-samples.json').write_text(json.dumps(dict(samples),indent=2));print(dict(groups))
if __name__=='__main__':main()
