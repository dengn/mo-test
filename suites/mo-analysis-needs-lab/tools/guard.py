"""Process-tree RSS/deadline guard; terminates only its own framework job, never MO."""
import subprocess,sys,time,json,os
from pathlib import Path
import psutil
script=Path(__file__).resolve().parents[1]/'tools/frameworks.py';name=sys.argv[1];root=script.parents[1];out=root/'results'/('guard-'+name);out.mkdir(exist_ok=False);env=dict(os.environ,JAVA_HOME='/workspace/cache/jre17',PATH='/workspace/cache/jre17/bin:'+os.environ['PATH'],SPARK_LOCAL_IP='127.0.0.1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1');start=time.time();limit=4*1024**3;deadline=900
with (out/'job.log').open('w') as log,(out/'resources.jsonl').open('w') as records:
 proc=subprocess.Popen([sys.executable,str(script),name],cwd=root,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True);p=psutil.Process(proc.pid);peak=0;reason=None
 while proc.poll() is None:
  try:
   family=[p]+p.children(recursive=True);rss=sum(x.memory_info().rss for x in family if x.is_running());peak=max(peak,rss);r=dict(elapsed=time.time()-start,rss=rss,processes=len(family));records.write(json.dumps(r)+'\n');records.flush()
   if rss>limit or time.time()-start>deadline:
    reason='rss_limit' if rss>limit else 'deadline';os.killpg(proc.pid,15);break
  except psutil.NoSuchProcess:break
  time.sleep(2)
 try:code=proc.wait(15)
 except subprocess.TimeoutExpired:os.killpg(proc.pid,9);code=proc.wait()
 result=dict(name=name,exit_code=code,guard_reason=reason,peak_rss=peak,rss_limit=limit,deadline=deadline,elapsed=time.time()-start);(out/'summary.json').write_text(json.dumps(result,indent=2));print(result,flush=True);sys.exit(0 if code==0 and reason is None else 1)
