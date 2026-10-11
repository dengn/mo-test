import os,sys,json,ssl,time,threading,concurrent.futures,collections,argparse,re,hashlib
from pathlib import Path
import pymysql,socket
sys.path.insert(0,'/workspace/mo-cases-50000');import runner as base
CERT=Path('/workspace/mo-corners-50000/certs');profiles={};tlslocal=threading.local()
class WrongHostname(ssl.SSLContext):
 def wrap_socket(self,*a,**k):a[0].settimeout(5);k['server_hostname']='wrong.mo.invalid';return super().wrap_socket(*a,**k)
class BoundedContext(ssl.SSLContext):
 def wrap_socket(self,*a,**k):a[0].settimeout(5);return super().wrap_socket(*a,**k)
def context(mode):
 if mode=='plain':return None
 cache=getattr(tlslocal,'cache',{});tlslocal.cache=cache
 if mode in cache:return cache[mode]
 if mode=='badhost':
  ctx=WrongHostname(ssl.PROTOCOL_TLS_CLIENT);ctx.load_verify_locations(str(CERT/'ca.crt'))
 else:
  ctx=BoundedContext(ssl.PROTOCOL_TLS_CLIENT);ctx.load_verify_locations(str(CERT/('badca.crt' if mode=='badca' else 'ca.crt')))
 if mode=='tls12':ctx.minimum_version=ctx.maximum_version=ssl.TLSVersion.TLSv1_2
 if mode=='tls13':ctx.minimum_version=ctx.maximum_version=ssl.TLSVersion.TLSv1_3
 if mode in ['client','badclient','expiredclient']:
  name={'client':'client','badclient':'badclient','expiredclient':'expiredclient'}[mode];ctx.load_cert_chain(str(CERT/(name+'.crt')),str(CERT/(name+'.key')))
 cache[mode]=ctx;return ctx
def connect(actor='root',db=None,tls='plain',password=None):
 p=profiles[actor];kwargs=dict(host='127.0.0.1',port=6001,user=p['user'],password=password or p.get('password','111'),database=db if db is not None else p.get('db'),autocommit=True,connect_timeout=5,read_timeout=30,write_timeout=30,ssl=context(tls),local_infile=True)
 kwargs['ssl_disabled']=tls=='plain';c=pymysql.connect(**kwargs);return c
def query(c,s):
 with c.cursor() as q:
  q.execute(s['sql'],s.get('params') or None);sets=[]
  while True:
   if q.description:sets.append(q.fetchall())
   if not q.nextset():break
 return sets[-1] if sets else ()
def error(e):return {'code':e.args[0] if e.args else None,'message':str(e),'type':type(e).__name__}
locks=collections.defaultdict(threading.Lock)
def one(case):
 start=time.monotonic();connections={};checks=[];issues=[];tlsinfo=None
 lock=locks[case['lock']] if case.get('lock') else None
 if lock:lock.acquire()
 try:
  if case.get('connection_rejection'):
   try:
    c=connect(case.get('actor','root'),tls=case['tls']);connections['tls']=c
    issues.append({'kind':'candidate_security_acceptance','reason':'negative TLS handshake accepted'})
   except Exception as e:
    if isinstance(e,(ssl.SSLError,ssl.CertificateError)) or 'SSL' in str(e) or 'certificate' in str(e) or 'TLS' in str(e):checks.append({'expected_tls_rejection':error(e)})
    else:issues.append({'kind':'environment_or_unexpected_error','error':error(e)})
  else:
   for step in case['steps']:
    if step.get('disconnect'):
     dc=connections.pop(step['disconnect']);dc._sock.shutdown(socket.SHUT_RDWR);dc._rfile.close();dc._sock.close();dc._sock=None;checks.append({'disconnect':step['disconnect'],'sent_quit':False});continue
    actor=step.get('actor',case.get('actor','root'));session=step.get('session',actor);mode=step.get('tls',case.get('tls','plain'))
    if step.get('authenticate'):
     try:
      ac=connect(actor,tls=mode,password=step.get('password'));ac.close()
      if step.get('reject'):issues.append({'kind':'candidate_authentication_acceptance','actor':actor})
      else:checks.append({'authentication':'accepted','actor':actor})
     except Exception as e:
      if step.get('reject') and re.search(step.get('error_pattern','password|user|role|account|denied|grant'),str(e),re.I):checks.append({'authentication':'expected_rejection','actor':actor,'expected_rejection':error(e)})
      else:issues.append({'kind':'authentication_error','actor':actor,'error':error(e)})
     continue
    if session not in connections:connections[session]=connect(actor,tls=mode)
    c=connections[session]
    if mode!='plain':
     if not isinstance(c._sock,ssl.SSLSocket):issues.append({'kind':'candidate_tls_downgrade'});break
     tlsinfo={'version':c._sock.version(),'cipher':c._sock.cipher()[0]}
    try:
     rawrows=query(c,step);rows=base.norm(rawrows);check={'sql':step['sql'],'rows':rows}
     if step.get('reject'):
      issues.append({'kind':'candidate_missing_rejection','sql':step['sql'],'actual':rows})
     elif 'expected' in step and not base.equal(rawrows,step['expected'],step.get('tolerance',1e-6)):
      issues.append({'kind':'candidate_wrong_result','sql':step['sql'],'actual':rows,'expected':step['expected']})
     checks.append(check)
    except Exception as e:
     er=error(e);valid=step.get('reject') and (not step.get('error_pattern') or re.search(step['error_pattern'],str(e),re.I))
     if valid:checks.append({'sql':step['sql'],'expected_rejection':er})
     elif step.get('boundary'):checks.append({'sql':step['sql'],'handled_boundary':er})
     else:issues.append({'kind':'execution_error','sql':step['sql'],'error':er});break
 except Exception as e:issues.append({'kind':'connection_or_runner_error','error':error(e)})
 finally:
  for c in connections.values():
   try:c.rollback();c.close()
   except Exception:pass
  for s in case.get('cleanup',[]):
   c=None
   try:c=connect(s.get('actor','root'));query(c,s)
   except Exception as e:issues.append({'kind':'cleanup_error','sql':s['sql'],'error':error(e)})
   finally:
    if c:c.close()
  if lock:lock.release()
 status=issues[0]['kind'] if issues else ('pass_expected_rejection' if any('expected_rejection' in x or 'expected_tls_rejection' in x for x in checks) else 'pass')
 return {'id':case['id'],'module':case['module'],'family':case['family'],'status':status,'seconds':time.monotonic()-start,'issues':issues,'checks':checks,'tls':tlsinfo}
def main(pack):
 global profiles
 p=Path(pack);profiles=json.loads((p/'profiles.json').read_text());ap=argparse.ArgumentParser();ap.add_argument('--calibrate',type=int,default=0);ap.add_argument('--workers',type=int,default=24);ap.add_argument('--output',default='results.jsonl');ap.add_argument('--ids');a=ap.parse_args()
 cases=list(map(json.loads,(p/'cases.jsonl').open()))
 if a.ids:
  ids=set(Path(a.ids).read_text().split());cases=[c for c in cases if c['id'] in ids]
 if a.calibrate:
  cnt=collections.Counter();selected=[]
  for c in cases:
   if cnt[c['family']]<a.calibrate:selected.append(c);cnt[c['family']]+=1
  cases=selected
 out=p/a.output;done={r['id'] for r in map(json.loads,out.open())} if out.exists() else set();cases=[c for c in cases if c['id'] not in done];cnt=collections.Counter();start=time.time();last=start;n=0
 with out.open('a') as f:
  for module in dict.fromkeys(c['module'] for c in cases):
   work=[c for c in cases if c['module']==module];workers=min(a.workers,4) if module in ['users_roles','git4data','iceberg_ddl'] else a.workers
   print('START',module,len(work),'workers',workers,flush=True)
   with concurrent.futures.ThreadPoolExecutor(workers) as ex:
    for r in ex.map(one,work):
     f.write(json.dumps(r,ensure_ascii=False,default=str)+'\n');cnt[r['status']]+=1;n+=1
     if n%1000==0 or time.time()-last>15:
      f.flush();print(json.dumps({'completed':n,'counts':cnt,'elapsed':round(time.time()-start,2)},ensure_ascii=False),flush=True);last=time.time()
 print('DONE',n,json.dumps(cnt),time.time()-start,flush=True)
