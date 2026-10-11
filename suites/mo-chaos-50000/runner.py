import sys,json,time,threading,concurrent.futures,collections,argparse,subprocess,os,signal,shutil,math,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent;B=Path('/workspace/mo-cases-50000');sys.path.insert(0,str(B));import runner as base
DB=base.DB

def setup():
 c=base.connect('mo',timeout=180)
 for s in ['create table if not exists chaos_ledger(id bigint primary key,n bigint,body text,j json)','create table if not exists chaos_hot(id int primary key,n bigint)','create table if not exists chaos_aborted(id bigint primary key,n bigint)','create table if not exists chaos_durable(id bigint primary key,n bigint)']:base.query(c,s)
 if base.query(c,'select count(*) from chaos_hot')[0][0]==0:
  with c.cursor() as q:q.executemany('insert into chaos_hot values(%s,0)',[(i,) for i in range(17)])
 c.close()
def special(case):
 policy=case['oracle_policy'];t=time.monotonic();details={};err=None
 if policy=='robustness':
  a,err=base.execute('mo',case);status='boundary_rejected' if err else 'boundary_accepted'
  if err and ('panic' in err['message'].lower() or err['code'] in [2006,2013]):status='candidate_crash_or_connection'
 elif policy=='cancel':
  c=base.connect('mo',timeout=20);cid=int(base.query(c,'select connection_id()')[0][0]);result=[]
  def query():
   try:result.append({'rows':base.norm(base.query(c,case['statements'][0]['sql'],case['statements'][0]['params']))})
   except Exception as e:result.append({'error':str(e),'code':e.args[0] if e.args else None})
  th=threading.Thread(target=query);th.start();time.sleep(case['meta']['delay_ms']/1000)
  ctrl=base.connect('mo');killerror=None
  try:base.query(ctrl,f'kill query {cid}')
  except Exception as e:killerror=str(e)
  ctrl.close();th.join(25);status='pass_cancel' if not th.is_alive() else 'candidate_cancel_hang';details={'query':result,'kill_error':killerror,'connection_id':cid};c.close()
 elif policy=='disconnect':
  c=base.connect('mo');base.query(c,'begin');st=case['statements'][0];base.query(c,st['sql'],st['params']);c.close();ctrl=base.connect('mo');a=base.query(ctrl,'select count(*) from chaos_aborted where id=%s',[case['meta']['ledger_id']]);ctrl.close();status='pass_disconnect_rollback' if a==((0,),) else 'candidate_wrong_result';details={'actual':base.norm(a)}
 elif policy=='restart':return restart(case)
 else:return base.runone(case)
 return {'id':case['id'],'module':case['module'],'family':case['family'],'status':status,'seconds':round(time.monotonic()-t,6),'mo_error':err,**details}
def normal(case):
 if case['oracle_policy']!='normal':return special(case)
 if case['module']!='chaos_mixed':return base.runone(case)
 t=time.monotonic();a=None;err=None;retries=0
 while retries<12:
  a,err=base.execute('mo',case)
  if not err:break
  cs=getattr(base.local,'connections',{});c=cs.get('mo')
  if c:
   try:base.query(c,'rollback')
   except:pass
  if err['code'] not in [20706,20618,20619,20101,1213]:break
  retries+=1;time.sleep(min(0.02*retries,0.15))
 status='pass' if not err and base.equal(a,case['expected'],1e-6) else ('transaction_conflict' if err and err['code'] in [20706,20618,20619,20101,1213] else ('mo_execution_error' if err else 'candidate_wrong_result'))
 return {'id':case['id'],'module':case['module'],'family':case['family'],'status':status,'seconds':time.monotonic()-t,'mo_error':err,'retries':retries,'actual':base.norm(a),'expected':case['expected'],'meta':case['meta']}
def restart(case):
 evidence=P/os.environ['MO_SUITE_DATABASE'] if os.environ.get('MO_SUITE_DATABASE') else P
 evidence.mkdir(parents=True,exist_ok=True)
 t=time.monotonic();round=case['meta']['round'];concurrency=case['meta']['concurrency'];stop=threading.Event();ack=[];ambiguous=[];errors=[];mutex=threading.Lock();counter=iter(range(round*1000000,round*1000000+1000000));server=Path('/workspace/mo-stress');pid=int((server/'server.pid').read_text());details={}
 if Path(f'/proc/{pid}/comm').read_text().strip()!='mo-service':raise RuntimeError('wrong restart PID')
 def load(worker):
  c=None
  try:
   c=base.connect('mo',timeout=8)
   while not stop.is_set():
    if worker%4==0:
     with mutex:i=next(counter)
     try:
      base.query(c,'insert into chaos_durable values(%s,%s)',[i,i*3]);
      with mutex:ack.append(i)
     except Exception as e:
      with mutex:ambiguous.append(i);errors.append(str(e))
      break
    elif worker%4==1:base.query(c,'select sum(a.val+b.val) from seed a join seed b on a.grp=b.grp')
    elif worker%4==2:base.query(c,"select id from ft2 where match(body) against('alpha' in boolean mode) order by id limit 20")
    else:base.query(c,"select id from vh order by l2_distance(v,'[0.2,0.5,0.7]') limit 10")
  except Exception as e:
   with mutex:errors.append(str(e))
  finally:
   if c:c.close()
 with concurrent.futures.ThreadPoolExecutor(concurrency) as ex:
  futures=[ex.submit(load,w) for w in range(concurrency)];time.sleep(3);os.kill(pid,signal.SIGKILL);stop.set()
  for f in futures:f.result()
 shutil.copy2(server/'server.log',evidence/f'server-before-restart-{round}.log')
 subprocess.run([str(server/'start.sh')],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 ready=False
 for _ in range(120):
  try:c=base.connect('mo',timeout=10);base.query(c,'select 1');ready=True;break
  except Exception:time.sleep(0.5)
 if not ready:raise RuntimeError('restart recovery timeout')
 rows=base.query(c,'select id,n from chaos_durable where id between %s and %s order by id',[round*1000000,round*1000000+999999]);stored={int(i):int(n) for i,n in rows};missing=[i for i in ack if i not in stored];bad=[i for i,n in stored.items() if n!=i*3];ambiguity=[i for i in ambiguous if i in stored];c.close()
 details={'planned_signal':'SIGKILL','old_pid':pid,'new_pid':int((server/'server.pid').read_text()),'concurrency':concurrency,'acknowledged_writes':len(ack),'stored_rows':len(stored),'acknowledged_missing':missing,'corrupt_rows':bad,'ambiguous_committed':ambiguity,'disconnects':len(errors),'errors_sample':errors[:3]}
 (evidence/f'crash-ledger-{round}.json').write_text(json.dumps({'acknowledged':ack,'ambiguous':ambiguous,'stored':stored},indent=2))
 return dict(id=case['id'],module=case['module'],family=case['family'],status='pass_restart_recovery' if not missing and not bad else 'candidate_data_loss',seconds=time.monotonic()-t,**details)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--calibrate',type=int,default=0);ap.add_argument('--output',default='results.jsonl');ap.add_argument('--ids');ap.add_argument('--workers',type=int,default=32);a=ap.parse_args();setup();cases=[json.loads(l) for l in (P/'cases.jsonl').open()]
 if a.ids:
  wanted=set(Path(a.ids).read_text().split());cases=[c for c in cases if c['id'] in wanted]
 if a.calibrate:
  cc=collections.Counter();z=[]
  for c in cases:
   if cc[c['family']]<a.calibrate and c['module']!='chaos_restart':z.append(c);cc[c['family']]+=1
  cases=z
 out=P/a.output;done={json.loads(l)['id'] for l in out.open()} if out.exists() else set();cases=[c for c in cases if c['id'] not in done];counts=collections.Counter();t=time.time();last=t
 with out.open('a') as f:
  for module in dict.fromkeys(c['module'] for c in cases):
   batch=[c for c in cases if c['module']==module];workers=1 if module=='chaos_restart' else (min(a.workers,16) if module=='chaos_faults' else a.workers);print('module',module,len(batch),'workers',workers,flush=True)
   with concurrent.futures.ThreadPoolExecutor(workers) as ex:
    for r in ex.map(normal,batch):
     f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n');counts[r['status']]+=1
     if sum(counts.values())%500==0 or time.time()-last>15:
      f.flush();last=time.time();print(json.dumps({'completed':sum(counts.values()),'counts':counts,'elapsed':round(time.time()-t,2)}),flush=True)
   f.flush();print('module done',module,dict(counts),flush=True)
 print('DONE',len(done)+sum(counts.values()),dict(counts),time.time()-t,flush=True)
if __name__=='__main__':main()
