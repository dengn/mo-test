from runtime import *
import statistics
x=json.loads((B/'soak-result.json').read_text());lat=json.loads((B/'soak-latency-samples.json').read_text());minutes=x['minutes'];summary={'runtime_ref':REF,'soak':{k:v for k,v in x.items() if k!='minutes'},'recovery_observations':[]}
progress=json.loads((B/'soak-progress.json').read_text())
actual_inserts={r:v['source_rows']+v['intentional_source_deletes'] for r,v in x['final'].items()}
assert progress['status']==x['status'] and progress['generated']==actual_inserts
summary['soak']['raw_receipt_generated_snapshot']=x['generated']
summary['soak']['generated']=actual_inserts
summary['soak']['count_reconciliation_note']='raw soak-result copied last 30s generated snapshot before terminal producer tick; final soak-progress and final source rows plus deletes agree; preserve raw receipts and report reconciled actual counts'
for f in x['faults']:
 affected=['kafka'] if f['name']=='connect' else ['nifi'] if f['name']=='nifi' else ['kafka','nifi']
 for route in affected:
  # Normal small lag is <= two seconds of inserts. This is a 30s-sampled upper bound, not exact recovery time.
  rate=10 if route=='kafka' else 5
  after=[m for m in minutes if m['elapsed_s']>f['elapsed_s']]
  degraded=next((m for m in after if m['routes'][route]['unobserved_inserts']>2*rate),None)
  caught=next((m for m in after if degraded and m['elapsed_s']>degraded['elapsed_s'] and m['routes'][route]['unobserved_inserts']<=2*rate),None)
  summary['recovery_observations'].append({'fault':f['name'],'route':route,'fault_elapsed_s':f['elapsed_s'],'first_sample_back_at_small_lag_elapsed_s':caught['elapsed_s'] if caught else None,'sampled_recovery_upper_bound_s':caught['elapsed_s']-f['elapsed_s'] if caught else None,'interpretation':'<=2s insert backlog; 30s polling bound; not proof of exact RTO'})
summary['resource_observations']={'cpu_quota_utilization_mean_percent':statistics.mean(m['cpu_quota_utilization_percent'] for m in minutes),'cpu_quota_utilization_max_percent':max(m['cpu_quota_utilization_percent'] for m in minutes),'rss_MB_first':minutes[0]['rss_MB'],'rss_MB_last':minutes[-1]['rss_MB'],'rss_MB_peak':{n:max(m['rss_MB'].get(n) or 0 for m in minutes) for n in ['mo','kafka','connect','nifi']},'free_disk_MB_first':minutes[0]['free_disk_MB'],'free_disk_MB_last':minutes[-1]['free_disk_MB'],'max_sampled_unobserved_inserts':{r:max(m['routes'][r]['unobserved_inserts'] for m in minutes) for r in ['kafka','nifi']}}
summary['latency_excluding_sampled_recovery_windows']={}
for route in ['kafka','nifi']:
 intervals=[(r['fault_elapsed_s'],r['first_sample_back_at_small_lag_elapsed_s']) for r in summary['recovery_observations'] if r['route']==route and r['first_sample_back_at_small_lag_elapsed_s'] is not None]
 values=[v['ms'] for v in lat[route] if not any(a<=v['elapsed_s']<=b for a,b in intervals)]
 summary['latency_excluding_sampled_recovery_windows'][route]={'samples':len(values),'p50':percentile(values,.5),'p95':percentile(values,.95),'p99':percentile(values,.99),'max':max(values,default=None),'excluded_first_visibility_elapsed_intervals_s':intervals,'interpretation':'visibility-time based exclusion of planned fault+recovery windows; includes rate stairs and 60s direct pressure; not a baseline or production SLO'}
summary['throughput_short']=json.loads((B/'throughput-result.json').read_text());summary['throughput_60s']=json.loads((B/'throughput-sustained-result.json').read_text());summary['staircase']=json.loads((B/'staircase-result.json').read_text());summary['typed_fidelity']=json.loads((B/'typed-fidelity-result.json').read_text());summary['exactly_once']={n:json.loads((B/n).read_text()) for n in ['exactly-once-native-result.json','nifi-exactly-once-result.json','exactly-once-effects-result.json','exactly-once-MO-crash-result.json']}
dump(B/'certification-summary.json',summary);print(json.dumps({'soak_status':x['status'],'load_s':x['load_end_elapsed_s'],'final':x['final'],'latency':x['latency'],'recovery':summary['recovery_observations'],'resource':summary['resource_observations']},ensure_ascii=False,indent=2),flush=True)
