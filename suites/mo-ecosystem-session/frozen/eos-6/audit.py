from protocol import *
import collections
receipts=['deterministic-result.json','batches-result.json','isolation-result.json','rebalance-result.json','zombie-result.json','ack-first-result.json','retention-result.json','producer-fence-result.json']
counts=collections.Counter();summary={'runtime_ref':REF,'scope':'scoped exactly-once effects in explicit test adapter, with intentionally unsafe controls; not native connector or full distributed EOS certification','receipts':{},'positive_full_event_oracles':[]}
for name in receipts:
 d=json.loads((B/name).read_text());cases=d.get('cases',[d]);assert all(c['status'].startswith(('passed_','observed_expected_')) for c in cases),(name,d)
 counts.update(c['status'] for c in cases);summary['receipts'][name]={'status':d['status'],'checks':len(cases),'sha256':hashlib.sha256((B/name).read_bytes()).hexdigest()}
expected={}
e={'event_id':1,'delta':7,'payload':'精确事件😀'}
for port in [6001,13306]:
 for k in ['rollback','fencing']:expected[(port,f'{k}_{port}')]=[e]
 expected[(port,f'gap_{port}')]=[{'event_id':i+1,'delta':7} for i in range(3)]
 expected[(port,f'conflict_{port}')]=[e,{'event_id':2,'delta':3,'payload':'合法后续'}]
 expected[(port,f'event_identity_{port}_stable')]=[{'event_id':101,'delta':7,'operation_id':'one-business-operation'}]
 expected[(port,f'batch_{port}')]=[{'event_id':i+1,'delta':3,'payload':'microbatch'} for i in range(5)]
expected[(6001,'ack_protected')]=[{'event_id':1,'delta':7,'payload':'提交确认😀'}]
expected[(6001,'rebalance')]=[{'event_id':i+1,'delta':i%7-3,'payload':'重分配😀'+str(i)} for i in range(250)]
expected[(6001,'zombie')]=[{'event_id':i+1,'delta':1,'payload':'旧消费者😀'} for i in range(120)]
expected[(6001,'safe_committed')]=[{'event_id':100+i,'delta':2,'phase':'commit'} for i in range(10)]
expected[(6001,'producer_fence')]=[{'event_id':101+i,'delta':1,'producer':'current'} for i in range(5)]
for (port,scope),events in expected.items():
 s=state(scope,port);gold=[(x['event_id'],digest(x),x['delta']) for x in events];actual=[r[:3] for r in s['ledger']];assert actual==gold,(port,scope,actual,gold);assert s['total']==sum(x['delta'] for x in events),(port,scope,s)
 if scope=='rebalance':assert all(0<=r[3]<4 and r[4]==r[0]-1 for r in s['ledger'])
 if scope=='zombie':assert all(r[3]==0 and r[4]==r[0]-1 for r in s['ledger'])
 canonical=lambda v:json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()
 summary['positive_full_event_oracles'].append({'port':port,'scope':scope,'events':len(events),'expected_sum':sum(x['delta'] for x in events),'ledger_digest_delta_all_match':True,'expected_sha256':hashlib.sha256(canonical(gold)).hexdigest(),'actual_sha256':hashlib.sha256(canonical(actual)).hexdigest(),'checkpoints':s['checkpoints'],'quarantine_records':s['quarantine']})
summary['check_counts']=dict(counts);summary['total_checks']=sum(counts.values());summary['negative_counterexamples']=counts['observed_expected_EOS_failure'];summary['positive_checks']=summary['total_checks']-summary['negative_counterexamples'];summary['case_count_note']='includes separate MySQL controls; not 30 independent production certifications; numeric Kafka control-offset guard observation is additional and not counted'
summary['new_independent_MO_kernel_bug_confirmed']=False
summary['git_tracked_changes']=subprocess.run(['git','-C','/workspace/matrixone','diff','--name-only','HEAD'],capture_output=True,text=True,check=True).stdout;assert not summary['git_tracked_changes']
summary['end_resources']=resources();summary['status']='verified_scoped_effects_and_counterexamples';dump(B/'round-summary.json',summary);print(json.dumps({k:summary[k] for k in ['status','total_checks','positive_checks','negative_counterexamples']},ensure_ascii=False),flush=True)
