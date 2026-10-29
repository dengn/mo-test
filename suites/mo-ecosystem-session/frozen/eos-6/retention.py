from protocol import *
out={'runtime_ref':REF,'scope':'explicit synthetic ledger expiration, no real elapsed TTL; late producer duplicate at a NEW Kafka-like offset, not offset rewind; same MySQL control','cases':[]}
for port in [6001,13306]:
 scope='retention_'+str(port);init(scope,port=port);e={'event_id':1,'delta':7,'payload':'迟到重试'};apply(scope,0,0,e,port=port);before=state(scope,port)
 sql('DELETE FROM ledger WHERE scope=%s AND event_id=1',(scope,),port=port);expired=state(scope,port);retry=apply(scope,0,1,e,port=port);after=state(scope,port)
 ok=before['total']==7 and expired['total']==7 and not expired['ledger'] and after['total']==14 and after['checkpoints'][0][1]==1
 out['cases'].append({'case':scope,'status':'observed_expected_EOS_failure' if ok else 'failed_unexpected','before_expiration':before,'expired':expired,'late_retry':retry,'after_retry':after,'expected_single_business_effect':7});assert ok
out['status']='completed_with_expected_counterexamples';dump(B/'retention-result.json',out);print(out['status'],flush=True)
