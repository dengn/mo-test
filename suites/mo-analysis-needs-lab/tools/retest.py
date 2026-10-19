"""Retain initial frozen results and independently rerun failures after a documented client NULL repair."""
import sys,json,time,hashlib,concurrent.futures,argparse
from pathlib import Path
ORIGINAL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ORIGINAL/'repaired'))
import run
from data import tables,plain,audit
from scenarios import DOMAINS

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pilot',action='store_true');args=ap.parse_args();tag='retest-pilot' if args.pilot else 'retest';out=ORIGINAL/'results'/tag;out.mkdir(exist_ok=False);main=ORIGINAL/'results/main-001';initial=[]
 if not args.pilot:assert (main/'summary.json').exists(),'Primary run must finish before final repair retest'
 for domain in DOMAINS:
  for lineno,line in enumerate((main/f'{domain}.jsonl').open(),1):
   try:r=json.loads(line)
   except json.JSONDecodeError:
    if args.pilot:continue
    raise
   if r['status']!='pass':initial.append((r,lineno))
 if args.pilot:initial=initial[:10]
 run.DATA=tables();started=time.time();freeze={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ORIGINAL/'repaired').glob('*.py')};counts=dict(cases=0,passed=0,failed=0);tasks=[]
 for r,line in initial:
  # Only the point-in-time math None handling has been changed. Other failures retain their interpretation.
  p=r['parameters'];tasks.append((p['domain'],p['template'],p['parameter']))
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool,(out/'cases.jsonl').open('w') as f:
  for (old,line),r in zip(initial,pool.map(run.execute,tasks)):
   r['code_sha256']=freeze;r['initial_attempt']=dict(member=f'results/main-001/{old["domain"]}.jsonl',line=line,status=old['status'],phase=old['failure_phase'],error=old['error']);r['repair']='Use pandas.isna for nullable scalar fields before point-in-time feature math; no SQL or numeric tolerance changed.';counts['cases']+=1;counts['passed']+=r['status']=='pass';counts['failed']+=r['status']!='pass';f.write(json.dumps(plain(r),ensure_ascii=False,separators=(',',':'))+'\n');print('RETEST',r['case_id'],r['status'],r.get('error','')[:200],flush=True)
 for n,d,c,e in run.WORKERS:d.close();c.close();e.dispose()
 counts.update(elapsed_seconds=time.time()-started,code_sha256=freeze,initial_failures=len(initial),scope='Final logical-case outcome overlay after client-only NULL handling repair. Initial frozen 100000 records are preserved unchanged, extra execution attempts are not additional logical cases.',source_audit=audit(run.DATA,tag));(out/'summary.json').write_text(json.dumps(counts,indent=2));print('SUMMARY',counts,flush=True)
if __name__=='__main__':main()
