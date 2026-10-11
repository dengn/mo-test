"""Bound only optional test-client resources, never the MO service or main runner."""
import argparse,json,subprocess,sys,time
from pathlib import Path
import psutil
p=argparse.ArgumentParser();p.add_argument('script');p.add_argument('--max-seconds',type=float,default=600);p.add_argument('--max-rss-mib',type=float,default=4096);a=p.parse_args()
root=Path(__file__).resolve().parent;started=time.time();proc=subprocess.Popen([sys.executable,str(root/a.script)]);peak=0;reason=None
try:
 while proc.poll() is None:
  time.sleep(2)
  try:tree=[psutil.Process(proc.pid)]+psutil.Process(proc.pid).children(recursive=True)
  except psutil.NoSuchProcess:continue
  rss=0
  for x in tree:
   try:rss+=x.memory_info().rss
   except psutil.NoSuchProcess:pass
  peak=max(peak,rss/2**20)
  if time.time()-started>a.max_seconds:reason='client wall-time limit'
  if rss/2**20>a.max_rss_mib:reason='client process-tree RSS limit'
  if reason:
   for x in reversed(tree):
    try:x.terminate()
    except psutil.NoSuchProcess:pass
   _,alive=psutil.wait_procs(tree,timeout=5)
   for x in alive:
    try:x.kill()
    except psutil.NoSuchProcess:pass
   break
finally:
 code=proc.wait();result={'script':a.script,'returncode':code,'resource_stop_reason':reason,'seconds':time.time()-started,'peak_tree_rss_mib':peak,'limits':{'seconds':a.max_seconds,'tree_rss_mib':a.max_rss_mib}}
 (root/(a.script.replace('.py','')+'-guard.json')).write_text(json.dumps(result,indent=2));print('GUARD',json.dumps(result),flush=True)
if code or reason:sys.exit(1)
