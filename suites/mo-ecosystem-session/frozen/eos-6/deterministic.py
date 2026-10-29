from protocol import *
out=json.loads((B/'deterministic-result.json').read_text()) if '--mysql-only' in sys.argv else {'runtime_ref':REF,'scope':'explicit test adapter, not native connector; deterministic failure windows and independent MySQL controls','cases':[]}
def record(name,passed,details,expected_failure=False):
 r={'case':name,'status':'observed_expected_EOS_failure' if expected_failure and passed else ('passed_scoped' if passed else 'failed_unexpected'),'details':details};out['cases'].append(r);dump(B/'deterministic-result.json',out);print(name,r['status'],flush=True);assert passed,r
def raw(scope,event,port=6001):
 with db(port,autocommit=False) as d,d.cursor() as c:
  c.execute('INSERT INTO raw_effects VALUES(%s,%s,%s)',(scope,event['event_id'],event['delta']));c.execute('UPDATE totals SET n=n+%s WHERE scope=%s',(event['delta'],scope));d.commit()
for protected in ([] if '--mysql-only' in sys.argv else [False,True]):
 scope='ack_protected' if protected else 'ack_naive';init(scope);e={'event_id':1,'delta':7,'payload':'提交确认😀'};dump(B/'proxy-arm.json',{'scope':scope,'stage':'successful COMMIT OK suppression'})
 try:
  if protected:apply(scope,0,0,e,port=16001)
  else:raw(scope,e,16001)
  raise AssertionError('ACK fault was not hit')
 except pymysql.MySQLError as error:
  assert error.args[0] in [2013,2006],error
  ambiguity=str(error)
 evidence=json.loads((B/'proxy-commit-ack-dropped.json').read_text());dump(B/(scope+'-ACK-evidence.json'),evidence);before=state(scope)
 retry=apply(scope,0,0,e) if protected else raw(scope,e)
 after=state(scope);record(scope,before['total']==7 and after['total']==(7 if protected else 14),{'event':e,'client_error':ambiguity,'server_OK_suppressed':evidence,'committed_state_before_retry':before,'after_retry':after,'retry':retry},expected_failure=not protected)
for port in ([13306] if '--mysql-only' in sys.argv else [6001,13306]):
 for kind in ['rollback','gap','fencing','conflict','event_identity']:
  scope=f'{kind}_{port}';init(scope,port=port);e={'event_id':1,'delta':7,'payload':'精确事件😀'}
  if kind=='rollback':
   try:apply(scope,0,0,e,port=port,after_ledger_error=True);raise AssertionError('injection missed')
   except RuntimeError as error:assert 'injected error' in str(error)
   before=state(scope,port);apply(scope,0,0,e,port=port);after=state(scope,port);record(scope,before['total']==0 and not before['ledger'] and before['checkpoints'][0][1]==-1 and after['total']==7,{'after_error_before_retry':before,'after_retry':after})
  elif kind=='gap':
   unsafe=scope+'_unsafe';init(unsafe,port=port)
   # Parallel handler offset 1 completes before offset 0; GREATEST is not a contiguous prefix.
   with db(port,autocommit=False) as d,d.cursor() as c:
    c.execute('INSERT INTO ledger VALUES(%s,2,%s,7,0,1)',(unsafe,digest({'event_id':2,'delta':7})));c.execute('UPDATE totals SET n=7 WHERE scope=%s',(unsafe,));c.execute('UPDATE checkpoints SET last_offset=GREATEST(last_offset,1) WHERE scope=%s',(unsafe,));d.commit()
   # A restarted consumer trusting last_offset+1 seeks offset 2 and skips unfinished offset 0.
   apply(unsafe,0,2,{'event_id':3,'delta':7},port=port);bad=state(unsafe,port)
   record(unsafe,bad['total']==14 and [r[0] for r in bad['ledger']]==[2,3],{'expected_three_events_sum':21,'actual':bad,'recovery_seek':2},True)
   try:apply(scope,0,1,{'event_id':2,'delta':7},port=port);raise AssertionError('gap accepted')
   except OffsetGap:pass
   rejected=state(scope,port)
   for i in range(3):apply(scope,0,i,{'event_id':i+1,'delta':7},port=port)
   after=state(scope,port);record(scope,rejected['total']==0 and not rejected['ledger'] and after['total']==21 and after['checkpoints'][0][1]==2,{'rejected_noncontiguous':rejected,'recovered_in_order':after})
  elif kind=='fencing':
   _,old=claim(scope,0,port);_,new=claim(scope,0,port)
   try:apply(scope,0,0,e,epoch=old,port=port);raise AssertionError('stale epoch accepted')
   except StaleEpoch:pass
   rejected=state(scope,port);apply(scope,0,0,e,epoch=new,port=port);after=state(scope,port);record(scope,rejected['total']==0 and after['total']==7,{'old_epoch':old,'current_epoch':new,'after_stale_attempt':rejected,'current_owner_result':after})
  elif kind=='conflict':
   apply(scope,0,0,e,port=port);different=dict(e,delta=999,payload='冲突载荷')
   try:apply(scope,0,1,different,port=port);raise AssertionError('different payload accepted')
   except PayloadConflict:pass
   rejected=state(scope,port);q=apply(scope,0,1,different,port=port,quarantine_conflict=True);apply(scope,0,2,{'event_id':2,'delta':3,'payload':'合法后续'},port=port);after=state(scope,port)
   record(scope,rejected['total']==7 and rejected['checkpoints'][0][1]==0 and after['total']==10 and after['checkpoints'][0][1]==2 and len(after['quarantine'])==1,{'rejected_before_checkpoint_advance':rejected,'quarantine_transaction':q,'continued_state':after,'semantics':'contract-violating payload isolated with checkpoint in same transaction; does not apply the conflicting effect'})
  else:
   e1={'event_id':101,'delta':7,'operation_id':'one-business-operation'};e2=dict(e1,event_id=102)
   apply(scope,0,0,e1,port=port);apply(scope,0,1,e2,port=port);bad=state(scope,port)
   record(scope,bad['total']==14 and len(bad['ledger'])==2,{'deliveries':[e1,e2],'state':bad,'expected_one_business_operation_sum':7,'reason':'transport ID regenerated on producer retry defeats dedup key'},True)
   good=scope+'_stable';init(good,port=port);apply(good,0,0,e1,port=port);apply(good,0,1,e1,port=port);after=state(good,port)
   record(good,after['total']==7 and len(after['ledger'])==1 and after['checkpoints'][0][1]==1,{'state':after,'business_operation_id_stable':True})
out['status']='completed_with_expected_counterexamples';dump(B/'deterministic-result.json',out)
