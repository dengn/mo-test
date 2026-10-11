import sys,json,time,collections,concurrent.futures,argparse,threading,importlib.util
from pathlib import Path
P=Path(__file__).resolve().parent;sys.path.insert(0,'/workspace/mo-cases-50000');import runner as base
spec=importlib.util.spec_from_file_location('chaos_tools','/workspace/mo-chaos-50000/runner.py');chaos=importlib.util.module_from_spec(spec);spec.loader.exec_module(chaos)
def setup():
 c=base.connect('mo');base.query(c,'create table if not exists gap_atomic(id bigint primary key,n bigint)');base.query(c,'create table if not exists gap_aborted(id bigint primary key,n bigint)');c.close()
def conexecute(eng,case):
 cs=getattr(base.local,'connections',None)
 if cs is None:cs={};base.local.connections=cs
 if eng not in cs:cs[eng]=base.connect(eng,timeout=60)
 c=cs[eng];table='constraint_'+case['id'].lower();out=None;error=None;missing=[];rejects=[]
 try:
  for i,st in enumerate(case['statements']):
   try:
    out=base.query(c,st['sql'].replace('{table}',table),st.get('params'))
    if st.get('must_reject'):missing.append(i)
   except Exception as e:
    er={'code':e.args[0] if e.args else None,'message':str(e),'step':i}
    if st.get('must_reject'):rejects.append(er);continue
    error=er;break
 finally:
  try:
   base.query(c,'rollback');base.query(c,f'drop view if exists {table}_v');base.query(c,f'drop table if exists {table}');base.query(c,f'drop table if exists {table}_p')
  except Exception as e:error=error or {'code':'cleanup','message':str(e)}
 return out,error,missing,rejects
def constraints(case):
 t=time.monotonic();a,ae,am,ar=conexecute('mo',case);b,be,bm,br=conexecute('mysql',case);w=case['expected']
 if ae:status='both_rejected' if be else 'mo_execution_error'
 elif be:status='reference_rejected'
 elif am and not bm:status='candidate_constraint_violation'
 elif base.equal(a,b,case['tolerance']) and (w is None or base.equal(a,w,case['tolerance'])):status='pass_expected_rejection' if ar else 'pass'
 elif base.equal(a,b,case['tolerance']):status='oracle_issue'
 else:status='candidate_wrong_result'
 r=dict(id=case['id'],module=case['module'],family=case['family'],status=status,seconds=time.monotonic()-t,mo_error=ae,mysql_error=be,mo_missing_rejections=am,mysql_missing_rejections=bm,mo_expected_rejections=ar)
 if not status.startswith('pass'):r.update(actual=base.norm(a),reference=base.norm(b),expected=w)
 return r
def atomic(case):
 t=time.monotonic();i=case['meta']['row_id'];initial=case['meta']['initial'];c=base.connect('mo');base.query(c,'insert into gap_atomic values(%s,%s) on duplicate key update n=values(n)',[i,initial]);c.close();errors=[];retries=[]
 def inc(_):
  c=base.connect('mo');retry=0
  try:
   for retry in range(20):
    try:base.query(c,'update gap_atomic set n=n+1 where id=%s',[i]);return True
    except Exception as e:
     if e.args[0] not in [20706,20618,20619,1213]:errors.append(str(e));return False
     time.sleep(0.005*(retry+1))
   errors.append('retry exhaustion');return False
  finally:retries.append(retry);c.close()
 with concurrent.futures.ThreadPoolExecutor(4) as ex:success=sum(ex.map(inc,range(4)))
 c=base.connect('mo');actual=base.query(c,'select n from gap_atomic where id=%s',[i])[0][0];c.close();status='pass_atomic' if success==4 and actual==initial+4 else ('candidate_lost_update' if actual!=initial+success else 'transaction_conflict')
 return dict(id=case['id'],module=case['module'],family=case['family'],status=status,seconds=time.monotonic()-t,acknowledged_updates=success,actual=actual,expected=initial+4,retries=retries,errors=errors)
def runone(case):
 policy=case['oracle_policy']
 if policy=='normal':return base.runone(case)
 if policy=='constraint':return constraints(case)
 if policy=='atomic':return atomic(case)
 if policy in ['cancel','robustness']:return chaos.special(case)
 if policy=='disconnect':
  t=time.monotonic();c=base.connect('mo');base.query(c,'begin');st=case['statements'][0];base.query(c,st['sql'],st['params']);c.close();c=base.connect('mo');out=base.query(c,'select count(*) from gap_aborted where id=%s',[case['meta']['row_id']]);c.close();return dict(id=case['id'],module=case['module'],family=case['family'],status='pass_disconnect_rollback' if out==((0,),) else 'candidate_wrong_result',seconds=time.monotonic()-t,actual=base.norm(out))
 raise ValueError(policy)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--calibrate',type=int,default=0);ap.add_argument('--output',default='results.jsonl');ap.add_argument('--workers',type=int,default=32);ap.add_argument('--ids');a=ap.parse_args();setup();cases=list(map(json.loads,(P/'cases.jsonl').open()))
 if a.ids:
  ids=set(Path(a.ids).read_text().split());cases=[c for c in cases if c['id'] in ids]
 if a.calibrate:
  z=[];cc=collections.Counter()
  for c in cases:
   if cc[c['family']]<a.calibrate:z.append(c);cc[c['family']]+=1
  cases=z
 dest=P/a.output;done={json.loads(l)['id'] for l in dest.open()} if dest.exists() else set();cases=[c for c in cases if c['id'] not in done];cc=collections.Counter();t=time.time();last=t
 with dest.open('a') as f:
  for mod in dict.fromkeys(c['module'] for c in cases):
   batch=[c for c in cases if c['module']==mod];workers=4 if mod=='constraints' else 16 if mod=='concurrency' else a.workers;print('module',mod,len(batch),'workers',workers,flush=True)
   with concurrent.futures.ThreadPoolExecutor(workers) as ex:
    for r in ex.map(runone,batch):
     f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n');cc[r['status']]+=1
     if sum(cc.values())%1000==0 or time.time()-last>15:
      f.flush();last=time.time();print(json.dumps({'completed':sum(cc.values()),'counts':cc,'elapsed':round(time.time()-t,2)}),flush=True)
   f.flush();print('module done',mod,dict(cc),flush=True)
 print('DONE',len(done)+sum(cc.values()),dict(cc),time.time()-t,flush=True)
if __name__=='__main__':main()
