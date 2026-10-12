import json,collections,hashlib,re,time
from pathlib import Path
ROOT=Path('/workspace');OUT=ROOT/'mo-stability-500000';PACKS=[('mo-cases-50000',50000),('mo-chaos-50000',50000),('mo-crossdb-100000',100000),('mo-etl-100000',100000),('mo-gap-200000',200000)]
summary={'target':500000,'generated':0,'executed':0,'packs':{},'families':set(),'classifications':collections.Counter(),'sources':[],'planned_crash_rounds':[]};groups=collections.defaultdict(lambda:{'count':0,'ids':[],'sample':None});seen=set();sourceids=set();overrides={}
p=ROOT/'mo-chaos-50000'
if (p/'recheck.jsonl').exists():
 for r in map(json.loads,(p/'recheck.jsonl').open()):overrides[r['id']]=(r,'Calibration residue removed and original case re-executed')
if (p/'tie-recheck.json').exists():
 r=json.loads((p/'tie-recheck.json').read_text())
 if r['status'].startswith('pass'):overrides[r['id']]=({'status':r['status']},r['reason'])
p=ROOT/'mo-crossdb-100000'
if (p/'float32-recheck.json').exists():
 for r in json.loads((p/'float32-recheck.json').read_text()):
  if r['result']['status']=='pass':overrides[r['case_id']]=(r['result'],r['reason'])
def classification(c,r):
 status=r['status'];f=c['family'];module=c['module'];error=(r.get('mo_error') or {}).get('code')
 if status.startswith('pass'):return 'pass'
 if status in ['boundary_rejected','boundary_accepted','both_rejected']:return 'handled_boundary_or_both_rejected'
 if status=='reference_rejected':return 'reference_rejected_or_mysql_difference'
 if f in ['mixed_types.boolean_arithmetic','mixed_types.time_clip','mixed_types.string_binary_compare','mixed_types.unicode_collate']:return 'documented_behavior_difference'
 if f in ['mixed_types.date_numeric_mysql','mixed_types.time_numeric_mysql']:return 'temporal_numeric_compatibility_issue'
 if f=='mixed_types.concat_literal':return 'literal_concatenation_compatibility_issue'
 if f=='mixed_types.round_precision_unsigned':return 'unsigned_precision_compatibility_issue'
 if f=='number.divide':return 'division_precision_difference'
 if f=='ddl.truncate' and error==20706:return 'concurrent_ddl_lock_conflict'
 if f=='mysql.public_scalar':
  sql=c['statements'][0]['sql'].lower()
  if '\ufffd' in sql:return 'source_literal_encoding_issue'
  if status=='candidate_wrong_result' and 'union' in sql and 'order by' not in sql:
   a=r.get('actual');b=r.get('reference')
   if sorted(a,key=lambda row:json.dumps(row,ensure_ascii=False))==sorted(b,key=lambda row:json.dumps(row,ensure_ascii=False)):return 'pass_unordered_result'
  if any(s in sql for s in ['dayofmonth(19970323)','second(230322)','yearweek(20001231','week(199','week(200']):return 'temporal_numeric_compatibility_issue'
  if 'sounds like' in sql or '_latin' in sql or '_utf8' in sql or '_utf16' in sql or '_gb18030' in sql or re.search(r'_[a-z0-9]+\s+0x',sql) or 'sql_tsi_' in sql:return 'unsupported_syntax_charset_or_alias'
  if "last_day('2005-01-00')" in sql:return 'invalid_zero_date_compatibility_issue'
  if any(s in sql for s in ['collate',' like ','maketime(']):return 'documented_behavior_difference'
  if "'hello' 'monty'" in sql:return 'literal_concatenation_compatibility_issue'
  if any(s in sql for s in ['round(','truncate(']) and error==1690:return 'unsigned_precision_compatibility_issue'
  if error in [1690,20203,20301]:return 'type_conversion_or_range_boundary'
 return 'needs_review'
for name,target in PACKS:
 p=ROOT/name;resultfile=p/'results.jsonl';results={}
 if resultfile.exists():
  for r in map(json.loads,resultfile.open()):
   if r['id'] in results:raise RuntimeError('duplicate result ID '+r['id'])
   results[r['id']]=r
 counts=collections.Counter();raw=collections.Counter();generated=0;families=collections.Counter();failures=[]
 with (p/'resolved-results.jsonl').open('w') as output:
  for c in map(json.loads,(p/'cases.jsonl').open()):
   generated+=1;families[c['family']]+=1;summary['families'].add(c['family']);st=[{'sql':x['sql'],'params':x.get('params',[])} for x in c['statements']];seen.add(hashlib.sha256(json.dumps(st,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
   if c['id'] not in results:continue
   r=results[c['id']];raw[r['status']]+=1;original=r
   if c['id'] in overrides:
    replacement,reason=overrides[c['id']];r={**r,**replacement,'initial_status':original['status'],'resolution':reason}
   cat=classification(c,r);counts[cat]+=1;summary['classifications'][cat]+=1;r={**r,'classification':cat};output.write(json.dumps(r,ensure_ascii=False,default=str)+'\n')
   if r['module']=='chaos_restart':summary['planned_crash_rounds'].append(r)
   if cat not in ['pass','pass_unordered_result','handled_boundary_or_both_rejected']:
    key=(cat,c['family'],str((r.get('mo_error') or {}).get('code')));g=groups[key];g['count']+=1
    if len(g['ids'])<12:g['ids'].append(c['id'])
    if g['sample'] is None:g['sample']={'case':c,'result':r}
 summary['generated']+=generated;summary['executed']+=len(results);summary['packs'][name]={'target':target,'generated':generated,'executed':len(results),'raw_statuses':raw,'resolved_classifications':counts,'family_count':len(families)}
 for s in json.loads((p/'source-manifest.json').read_text()):
  if s.get('status','downloaded')!='downloaded':continue
  key=s.get('source_id') or s.get('url')
  if key not in sourceids:sourceids.add(key);summary['sources'].append(s)
summary['family_count']=len(summary.pop('families'));summary['distinct_sql_and_parameters']=len(seen);summary['source_count']=len(summary['sources']);summary['server_commit']='2726fb419b3afa1db2686ae1b2aaca563d1ae214';summary['mysql_reference']='8.0.46';summary['database']=(ROOT/'mo-cases-50000/database.txt').read_text().strip();summary['created_epoch']=time.time()
logs=[ROOT/'mo-stress/server.log']+list((ROOT/'mo-chaos-50000').glob('server-before-restart-*.log'))+list((ROOT/'mo-corners-50000').glob('server-before-feature-restart.log'));events=[]
for log in logs:
 for line_no,line in enumerate(log.open(errors='replace'),1):
  if re.search(r'panic:|fatal error:|SIGSEGV|runtime error:',line):events.append({'path':str(log),'line':line_no,'text':line[:2000]})
summary['panic_or_fatal_log_events']=events
if (ROOT/'mo-cases-50000/resources-current.jsonl').exists():
 rr=list(map(json.loads,(ROOT/'mo-cases-50000/resources-current.jsonl').open()));summary['resource_observations']={'samples':len(rr),'peak_memory_bytes':max(r['memory_bytes'] for r in rr),'min_free_disk_bytes':min(r['disk_free'] for r in rr),'server_unavailable_samples':sum(not r['server_alive'] for r in rr),'memory_events_last':rr[-1]['memory_events']}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(OUT/'problem-groups.json').write_text(json.dumps([dict(category=k[0],family=k[1],error_code=k[2],**v) for k,v in groups.items()],ensure_ascii=False,indent=2));(OUT/'sources.json').write_text(json.dumps(summary['sources'],ensure_ascii=False,indent=2));print(json.dumps({k:summary[k] for k in ['generated','executed','family_count','distinct_sql_and_parameters','source_count','classifications']},ensure_ascii=False))
