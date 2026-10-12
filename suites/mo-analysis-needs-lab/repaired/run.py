"""Full-result differential runner. No synthetic success counts or sampled equality."""
import argparse,concurrent.futures,threading,json,time,hashlib,traceback,os,sys,resource
from pathlib import Path
import pandas as pd,numpy as np
from sqlalchemy import text
from data import ROOT,tables,oracle,connect,engine,read,compare,plain,values,audit
from scenarios import DOMAINS,TITLES,TEMPLATES,params,sql_for,complexity
from native import Native
from analytics import analyze
from stages import Stages
LOCAL=threading.local();WORKERS=[];LOCK=threading.Lock();DATA=None;STATES={}
def digest(df):return hashlib.sha256(json.dumps(dict(columns=list(df),values=values(df)),separators=(',',':'),allow_nan=False).encode()).hexdigest()
def worker():
 if not hasattr(LOCAL,'w'):
  n=Native(DATA);d=oracle(DATA);c=connect();e=engine();LOCAL.w=(n,d,c,e)
  with LOCK:WORKERS.append(LOCAL.w)
 return LOCAL.w
def execute(task):
 domain,j,i=task;p=params(domain,j,i);sql=sql_for(domain,j,i);ident=domain*10000+j*1000+i;start=time.perf_counter();rec=dict(case_id=ident,domain=DOMAINS[domain],template=j,workflow=TEMPLATES[domain][j],parameters=p,sql=sql,complexity=complexity(sql),client='pandas_sqlalchemy' if ident%2 else 'numpy_pymysql',status='fail');phase='oracle';gold=None;got=None
 try:
  native,d,c,e=worker()
  if domain in [1,2]:
   cp=p['checkpoint']
   if cp not in native.states:
    inc,accepted=STATES[cp];native.set_state(cp,inc,accepted)
   inc,accepted=STATES[cp]
   if getattr(LOCAL,'stage_checkpoint',None)!=cp:
    LOCAL.stage_checkpoint=cp
    for name,df in [('inc_state',inc),('stream_accepted',accepted)]:
     d.register('stage_source',df);d.execute(f'CREATE OR REPLACE TABLE {name} AS SELECT * FROM stage_source');d.unregister('stage_source')
    daily=inc.groupby(['uid','day']).v.agg(total='sum',n='count').reset_index();d.register('stage_source',daily);d.execute('CREATE OR REPLACE TABLE inc_daily AS SELECT * FROM stage_source');d.unregister('stage_source')
  t=time.perf_counter();gold=native.expected(domain,j,i);sqlgold=d.execute(sql).df();compare(gold,sqlgold,1e-7);rec['oracle_seconds']=time.perf_counter()-t
  phase='mo_sql';t=time.perf_counter()
  if ident%2:
   with e.connect() as con:got=pd.read_sql_query(text(sql),con)
  else:got=read(c,sql)
  rec['mo_query_seconds']=time.perf_counter()-t;phase='sql_values';compare(gold,got,1e-7)
  rec['input']=dict(rows=len(gold),columns=list(gold),expected_sha256=digest(gold),actual_sha256=digest(got),full_values_compared=True)
  phase='math';t=time.perf_counter();expected=analyze(domain,j,i,gold,True,DATA);actual=analyze(domain,j,i,got,False,DATA);compare(expected,actual,1e-6);rec['math_seconds']=time.perf_counter()-t
  rec['output']=dict(columns=list(expected),expected=values(expected),actual=values(actual),full_values_compared=True);rec['status']='pass'
 except Exception as ex:
  rec['failure_phase']=phase;rec['error']=str(ex)[:4000];rec['traceback']=traceback.format_exc()[-6000:]
  if gold is not None:rec['expected_input']=dict(columns=list(gold),values=values(gold))
  if got is not None:rec['actual_input']=dict(columns=list(got),values=values(got))
 rec['elapsed_seconds']=time.perf_counter()-start;return rec

def main():
 global DATA
 ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['pilot','main'],default='pilot');ap.add_argument('--indices',default='0');ap.add_argument('--workers',type=int,default=4);ap.add_argument('--tag',required=True);ap.add_argument('--domains',default='0,1,2,3,4,5,6,7,8,9');args=ap.parse_args();out=ROOT/'results'/args.tag;out.mkdir(parents=True,exist_ok=False)
 DATA=tables();domains=[int(x) for x in args.domains.split(',')];indices=list(range(1000)) if args.mode=='main' else [int(x) for x in args.indices.split(',')]
 freeze={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in ROOT.glob('*.py')};(out/'run-config.json').write_text(json.dumps(dict(mode=args.mode,indices=indices,domains=domains,workers=args.workers,code_sha256=freeze,start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())),indent=2))
 counts={DOMAINS[d]:dict(total=0,passed=0,failed=0,failures={}) for d in domains};stage=Stages(DATA,out) if any(d in [1,2] for d in domains) else None;started=time.perf_counter();done=0
 handles={d:(out/f'{DOMAINS[d]}.jsonl').open('w') for d in domains}
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
   batches=[[(d,j,i) for j in range(10) for i in indices] for d in domains if d not in [1,2]]
   if stage:
    # Read queries for a checkpoint finish before its state can change.
    for cp in range(10):
     STATES[cp]=stage.advance(cp)
     jobs=[(d,j,i) for d in domains if d in [1,2] for j in range(10) for i in indices if i%10==cp]
     batches_before=[jobs]
     for rec in pool.map(execute,jobs):
      d=rec['parameters']['domain'];handles[d].write(json.dumps(plain(rec),ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n');co=counts[DOMAINS[d]];co['total']+=1;co['passed']+=rec['status']=='pass';co['failed']+=rec['status']!='pass';done+=1
      if rec['status']!='pass':co['failures'][rec['failure_phase']]=co['failures'].get(rec['failure_phase'],0)+1;print('FAIL',rec['case_id'],rec['failure_phase'],rec['error'][:250],flush=True)
     for h in handles.values():h.flush()
     (out/'progress.json').write_text(json.dumps(dict(done=done,counts=counts,elapsed_seconds=time.perf_counter()-started),indent=2))
   for jobs in batches:
    for rec in pool.map(execute,jobs):
     d=rec['parameters']['domain'];handles[d].write(json.dumps(plain(rec),ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n');co=counts[DOMAINS[d]];co['total']+=1;co['passed']+=rec['status']=='pass';co['failed']+=rec['status']!='pass';done+=1
     if rec['status']!='pass':co['failures'][rec['failure_phase']]=co['failures'].get(rec['failure_phase'],0)+1;print('FAIL',rec['case_id'],rec['failure_phase'],rec['error'][:250],flush=True)
     if done%100==0:
      for h in handles.values():h.flush()
      snapshot=dict(done=done,counts=counts,elapsed_seconds=time.perf_counter()-started);(out/'progress.json').write_text(json.dumps(snapshot,indent=2));print('PROGRESS',done,round(snapshot['elapsed_seconds'],1),flush=True)
 finally:
  for h in handles.values():h.close()
  if stage:stage.close()
  for n,d,c,e in WORKERS:d.close();c.close();e.dispose()
 result=dict(counts=counts,total=done,passed=sum(x['passed'] for x in counts.values()),failed=sum(x['failed'] for x in counts.values()),elapsed_seconds=time.perf_counter()-started,source_audit=audit(DATA,args.tag),code_sha256=freeze)
 assert freeze=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in ROOT.glob('*.py')},'Code mutated during run'
 (out/'summary.json').write_text(json.dumps(result,indent=2));print('SUMMARY',json.dumps(result),flush=True)
if __name__=='__main__':main()
