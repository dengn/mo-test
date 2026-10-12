"""Classify log contexts, not requests; capability probes overlap canonical time."""
import collections,json,re
from data import ROOT
def main():
 meta=json.loads((ROOT/'results/canonical/meta.json').read_text());counts=collections.Counter();samples={};paths=[];rows=[]
 for line in (ROOT/'server-canonical.log').open():
  r=json.loads(line);serialized=line.lower();msg=r.get('msg','');error=r.get('error','');statement=r.get('statement','');caller=r.get('caller','')
  if '65535' in line and ('Src length' in line or 'TEXT type' in line):kind='statement_info_text_overflow_context'
  elif msg=='failed to upload file to MO':kind='etl_upload_failure_context'
  elif msg=='upload files success' and r.get('success')==0:kind='zero_success_upload_summary'
  elif 'panic' in serialized and ('propagateUniformStringSource' in line or 'index out of range' in line):kind='capability_null_default_recovered_panic_context'
  elif 'SQL parser error' in line or 'You have an error in your SQL syntax' in line:kind='parser_rejection_context'
  elif 'not yet implemented' in line or 'not supported: function or operator' in line:kind='unsupported_semantics_context'
  elif 'Error:' in msg or 'error:' in msg or r.get('status')=='fail':kind='other_query_failure_context'
  else:kind='other_error_context'
  counts[kind]+=1;samples.setdefault(kind,r)
  if 'failed to upload file' in msg:
   path=r.get('path','');match=re.search(r'/([0-9]{10})_',path)
   if match:paths.append(dict(path=path,file_epoch=int(match.group(1)),predates_main=int(match.group(1))<meta['started_at']))
  if kind=='capability_null_default_recovered_panic_context':rows.append(r)
 result=dict(window=dict(started_at=meta['started_at'],ended_at=meta['ended_at']),total_contexts=sum(counts.values()),classification=dict(counts),structured_panic_levels=sum(r.get('level') in ['PANIC','FATAL'] for r in [*samples.values(),*rows]),etl_failure_path_contexts=len(paths),distinct_failed_files=len({r['path'] for r in paths}),failed_file_epochs_predating_main=sum(r['predates_main'] for r in paths),failed_file_epochs_within_or_after_main=sum(not r['predates_main'] for r in paths),samples=samples,notes=['Counts are structured log contexts; repeated caller/session error logs are not separate failed case requests.','Reference-only or SQL parser setup attempts and explicit capability-study failures share this service; main failure count comes only from cases.jsonl.','Recovered vector panic contexts correspond to the explicitly recorded LAG/LEAD NULL-default capability probes; source-health checks and PID survival are separate evidence.','Old ETL file retries cannot establish that this batch created their payload, that data loss is permanent, or that upload eventually recovered.'],known_issues=['https://github.com/matrixorigin/matrixone/issues/29809','https://github.com/matrixorigin/matrixone/issues/29797'])
 (ROOT/'server-log-review.json').write_text(json.dumps(result,indent=2));(ROOT/'capability-panic-log-contexts.json').write_text(json.dumps(rows,indent=2));print({k:v for k,v in result.items() if k not in ['samples','notes']})
if __name__=='__main__':main()
