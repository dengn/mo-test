from protocol import *
out={'runtime_ref':REF,'scope':'five-event atomic microbatch with actual SQL duplicate-key failure, plus ledger/checkpoint split-transaction counterexamples; independent MySQL controls','cases':[]}
def add(name,ok,details,bad=False):
 r={'case':name,'status':'observed_expected_EOS_failure' if ok and bad else ('passed_scoped' if ok else 'failed_unexpected'),'details':details};out['cases'].append(r);dump(B/'batches-result.json',out);print(name,r['status'],flush=True);assert ok
for port in [6001,13306]:
 scope='batch_'+str(port);init(scope,port=port)
 def batch(inject):
  with db(port,autocommit=False) as d,d.cursor() as c:
   try:
    for i in range(5):
     e={'event_id':i+1,'delta':3,'payload':'microbatch'}
     c.execute('INSERT INTO ledger VALUES(%s,%s,%s,%s,0,%s)',(scope,e['event_id'],digest(e),e['delta'],i));c.execute('UPDATE totals SET n=n+3 WHERE scope=%s',(scope,))
     if inject and i==2:c.execute('INSERT INTO ledger VALUES(%s,%s,%s,%s,0,%s)',(scope,e['event_id'],digest(e),e['delta'],i))
    c.execute('UPDATE checkpoints SET last_offset=4 WHERE scope=%s',(scope,));d.commit()
   except Exception:d.rollback();raise
 try:batch(True);raise AssertionError('duplicate-key failure missed')
 except pymysql.MySQLError as e:assert e.args[0]==1062,e;error=str(e)
 before=state(scope,port);batch(False);after=state(scope,port)
 add(scope,before['total']==0 and not before['ledger'] and before['checkpoints'][0][1]==-1 and after['total']==15 and len(after['ledger'])==5 and after['checkpoints'][0][1]==4,{'SQL_error':error,'after_batch_rollback':before,'after_full_retry':after})
 scope='split_ledger_'+str(port);init(scope,port=port);e={'event_id':1,'delta':7}
 sql('INSERT INTO ledger VALUES(%s,1,%s,7,0,0)',(scope,digest(e)),port=port)
 # Crash/error after separately committed ledger, before business transaction begins.
 retry=apply(scope,0,0,e,port=port);s=state(scope,port)
 add(scope,s['total']==0 and len(s['ledger'])==1 and s['checkpoints'][0][1]==0,{'expected_business_total':7,'state':s,'retry':retry,'window':'ledger committed in separate transaction; effect never committed'},True)
 scope='split_checkpoint_'+str(port);init(scope,port=port)
 sql('UPDATE checkpoints SET last_offset=0 WHERE scope=%s',(scope,),port=port)
 # Crash/error after separately committed checkpoint, before ledger/effect.
 retry=apply(scope,0,0,e,port=port);s=state(scope,port)
 add(scope,s['total']==0 and not s['ledger'] and s['checkpoints'][0][1]==0,{'expected_business_total':7,'state':s,'retry':retry,'window':'checkpoint committed separately before effect'},True)
out['status']='completed_with_expected_counterexamples';dump(B/'batches-result.json',out)
