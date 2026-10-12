"""Resume the exact frozen case evaluator with independent CPU workers; preserve every completed record."""
import sys,json,time,hashlib,os,concurrent.futures,multiprocessing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import run
from data import tables,plain,audit
from scenarios import DOMAINS

def init():run.DATA=tables()
def evaluate(task):return run.execute(task)
def hashfile(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=ROOT/'results/main-001';config=json.loads((out/'run-config.json').read_text());freeze=config['code_sha256'];assert freeze=={p.name:hashfile(p) for p in ROOT.glob('*.py')};counts={d:dict(total=0,passed=0,failed=0,failures={}) for d in DOMAINS};ids=set();prefix=[];started=time.time()
 for d in DOMAINS:
  path=out/f'{d}.jsonl';raw=path.read_bytes();valid=0;co=counts[d]
  for line in raw.splitlines(keepends=True):
   try:r=json.loads(line)
   except json.JSONDecodeError:break
   assert r['domain']==d and r['case_id'] not in ids;ids.add(r['case_id']);valid+=len(line);co=counts[d];co['total']+=1;co['passed']+=r['status']=='pass';co['failed']+=r['status']!='pass'
   if r['status']!='pass':co['failures'][r['failure_phase']]=co['failures'].get(r['failure_phase'],0)+1
  if valid!=len(raw):
   (out/f'{d}-interrupted-tail.bin').write_bytes(raw[valid:]);path.write_bytes(raw[:valid])
  prefix.append(dict(member=str(path.relative_to(ROOT)),bytes=valid,sha256=hashlib.sha256(raw[:valid]).hexdigest(),records=co['total']))
 assert all(counts[d]['total']==10000 for d in ['incremental','streaming','point_in_time']),counts
 continuation=dict(start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),pid=os.getpid(),completed_prefix_cases=len(ids),process_workers=3,code_sha256=freeze,prefix=prefix,scope='Driver continuation using unchanged frozen run.execute. Initial evaluator was stopped to replace GIL-bound threads with three independent Python processes. Completed bytes are preserved, IDs resumed without duplicate counts; no MO restart or source mutation.')
 (out/'continuation.json').write_text(json.dumps(continuation,indent=2));tasks=[(d,j,i) for d in range(10) for j in range(10) for i in range(1000) if d*10000+j*1000+i not in ids];assert all(d not in [1,2] for d,j,i in tasks)
 handles={d:(out/f'{d}.jsonl').open('a') for d in DOMAINS};fail=0
 try:
  with concurrent.futures.ProcessPoolExecutor(max_workers=3,mp_context=multiprocessing.get_context('fork'),initializer=init) as pool:
   for r in pool.map(evaluate,tasks,chunksize=8):
    d=r['domain'];ident=r['case_id'];assert ident not in ids;ids.add(ident);handles[d].write(json.dumps(plain(r),ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n');co=counts[d];co['total']+=1;co['passed']+=r['status']=='pass';co['failed']+=r['status']!='pass'
    if r['status']!='pass':co['failures'][r['failure_phase']]=co['failures'].get(r['failure_phase'],0)+1;print('FAIL',ident,r['failure_phase'],r['error'][:250],flush=True)
    if len(ids)%100==0:
     for h in handles.values():h.flush()
     snapshot=dict(done=len(ids),counts=counts,continuation_seconds=time.time()-started);(out/'progress.json').write_text(json.dumps(snapshot,indent=2));print('PROGRESS',len(ids),round(snapshot['continuation_seconds'],1),flush=True)
 finally:
  for h in handles.values():h.close()
 assert ids==set(range(100000));assert all(c['total']==10000 for c in counts.values())
 for r in prefix:
  p=ROOT/r['member'];assert hashlib.sha256(p.read_bytes()[:r['bytes']]).hexdigest()==r['sha256']
 assert freeze=={p.name:hashfile(p) for p in ROOT.glob('*.py')},'Frozen evaluator changed'
 started_main=time.mktime(time.strptime(config['start_utc'],'%Y-%m-%dT%H:%M:%SZ'))
 result=dict(counts=counts,total=len(ids),passed=sum(c['passed'] for c in counts.values()),failed=sum(c['failed'] for c in counts.values()),elapsed_seconds=time.time()-started_main,source_audit=audit(tables(),'main-001'),code_sha256=freeze,continuation=continuation,continuation_seconds=time.time()-started)
 (out/'summary.json').write_text(json.dumps(result,indent=2));print('SUMMARY',json.dumps(result),flush=True)
if __name__=='__main__':main()
