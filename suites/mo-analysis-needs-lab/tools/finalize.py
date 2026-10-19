"""Post-run checks, only after the complete main summary and stopped workers exist."""
import time,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'results/finalize';out.mkdir(exist_ok=False);journal=[];env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
while not (ROOT/'results/main-001/summary.json').exists():
 if (ROOT/'results/main-001/health-processes/guard-stop.json').exists():raise RuntimeError('Main resource guard stopped execution')
 time.sleep(5)
for _ in range(6):
 if (ROOT/'results/main-001/health-processes/health-after.json').exists():break
 time.sleep(5)
for name in ['retest','performance','report','check_browser']:
 start=time.time()
 with (out/f'{name}.log').open('w') as f:r=subprocess.run([sys.executable,str(ROOT/f'tools/{name}.py')],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
 journal.append(dict(step=name,exit_code=r.returncode,elapsed_seconds=time.time()-start));(out/'journal.json').write_text(json.dumps(journal,indent=2));print('FINALIZE',journal[-1],flush=True)
 if r.returncode:raise RuntimeError('Post-run check failed: '+name)
print('POST-RUN CHECKS COMPLETE',flush=True)
